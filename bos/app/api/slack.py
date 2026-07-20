"""
Slack adapter (Phase 1 inbound webhook + Phase 2 OAuth flow).

Provides:
  GET  /api/slack/oauth/callback  - OAuth v2 redirect target (Phase 2)
  POST /api/slack/event            - Slack Events API callback
  POST /api/slack/command          - Slack slash command

Phase 1 supports webhook pattern. Phase 2 adds the full OAuth v2 flow so
the BOS Slack app can be installed into any workspace without manual token
management. Tokens are persisted in the `slack_installations` table.

Setup:
  Set SLACK_CLIENT_ID, SLACK_CLIENT_SECRET, SLACK_REDIRECT_URL
  Add https://your-host/api/slack/oauth/callback to your Slack app's
  Redirect URLs in the Slack console.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..audit import get_audit
from ..config import get_settings
from ..db import raw_connection
from ..security import AuthContext
from .deps import require_api_key

log = logging.getLogger("bos.api.slack")
router = APIRouter(prefix="/api/slack", tags=["slack"])


# Schema for token storage
_SLACK_SCHEMA = """
CREATE TABLE IF NOT EXISTS slack_installations (
    team_id TEXT PRIMARY KEY,
    team_name TEXT,
    bot_user_id TEXT,
    bot_access_token TEXT,
    installed_at REAL,
    installed_by TEXT
);
"""


def _init_slack_schema():
    try:
        with raw_connection() as c:
            c.executescript(_SLACK_SCHEMA)
            c.commit()
    except Exception as e:
        log.warning("slack_installations schema init skipped: %s", e)


def _slack_client_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) from env vars."""
    return os.environ.get("SLACK_CLIENT_ID", ""), os.environ.get("SLACK_CLIENT_SECRET", "")


def _store_team_token(team_id: str, team_name: str, bot_user_id: str, token: str, installer: str):
    with raw_connection() as c:
        c.execute(
            """INSERT INTO slack_installations
               (team_id, team_name, bot_user_id, bot_access_token, installed_at, installed_by)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(team_id) DO UPDATE SET
                 team_name=excluded.team_name,
                 bot_user_id=excluded.bot_user_id,
                 bot_access_token=excluded.bot_access_token,
                 installed_at=excluded.installed_at,
                 installed_by=excluded.installed_by""",
            (team_id, team_name, bot_user_id, token, time.time(), installer),
        )
        c.commit()


def _get_team_token(team_id: str) -> Optional[str]:
    """Look up the bot token for a Slack team from DB."""
    try:
        with raw_connection() as c:
            cur = c.execute(
                "SELECT bot_access_token FROM slack_installations WHERE team_id = ?",
                (team_id,),
            )
            row = cur.fetchone()
        if row:
            # row could be sqlite3.Row or tuple
            if hasattr(row, "keys"):
                return row["bot_access_token"]
            return row[0] if row else None
        return None
    except Exception:
        return None


@router.get("/oauth/callback")
async def slack_oauth_callback(code: str, request: Request):
    """Phase 2 OAuth v2 redirect target.

    Slack redirects here after the user authorizes the app. We exchange
    the code for a bot token and store it keyed by team_id.
    """
    _init_slack_schema()
    client_id, client_secret = _slack_client_credentials()
    if not client_id or not client_secret:
        raise HTTPException(500, detail="SLACK_CLIENT_ID/SECRET not configured")

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://slack.com/api/oauth.v2.access", data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": os.environ.get("SLACK_REDIRECT_URL", ""),
            })
            data = r.json()
    except Exception as e:
        raise HTTPException(502, detail=f"oauth exchange failed: {e}")

    if not data.get("ok"):
        raise HTTPException(400, detail=f"slack denied: {data.get('error')}")

    team_id = data.get("team", {}).get("id", "")
    team_name = data.get("team", {}).get("name", "")
    bot_user_id = data.get("bot_user_id", "")
    bot_token = data.get("access_token", "")
    installer = data.get("authed_user", {}).get("id", "")

    _store_team_token(team_id, team_name, bot_user_id, bot_token, installer)
    log.info("Slack app installed: team=%s name=%s installer=%s", team_id, team_name, installer)

    return {
        "status": "ok",
        "team": team_name,
        "message": "Slack workspace connected. You can close this window.",
    }


def _slack_token(team_id: Optional[str] = None) -> Optional[str]:
    """Resolve the Slack bot token.

    Priority:
      1. If team_id given, look up team-scoped token from DB (OAuth flow)
      2. Fall back to global SLACK_BOT_TOKEN env var (single-workspace mode)
    """
    if team_id:
        t = _get_team_token(team_id)
        if t:
            return t
    return os.environ.get("SLACK_BOT_TOKEN")


def _resolve_channel(req_payload: Dict[str, Any]) -> Optional[str]:
    """Try to find a Slack channel id from the inbound payload."""
    if "event" in req_payload:
        return req_payload["event"].get("channel")
    return req_payload.get("channel_id")


async def post_to_slack(channel: str, text: str, blocks: Optional[list] = None,
                       team_id: Optional[str] = None) -> bool:
    """Send a message to Slack. Returns True on success.

    Token resolved per-team (via OAuth flow) or falls back to SLACK_BOT_TOKEN.
    No-op (returns False) if no token found.
    """
    token = _slack_token(team_id)
    if not token:
        log.info("No Slack token for team=%s; skipping message to %s", team_id, channel)
        return False
    payload: Dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            data = r.json()
            return bool(data.get("ok"))
    except Exception as e:
        log.warning("Slack post failed: %s", e)
        return False


class EventCallback(BaseModel):
    type: str
    challenge: Optional[str] = None
    event: Optional[Dict[str, Any]] = None
    team_id: Optional[str] = None


@router.post("/event")
async def slack_event(
    payload: EventCallback,
    request: Request,
    ctx: AuthContext = Depends(require_api_key),
):
    """Handle Slack Events API callbacks (url_verification + message events)."""
    # Slack URL verification handshake
    if payload.type == "url_verification" and payload.challenge:
        return {"challenge": payload.challenge}

    if payload.type != "event_callback":
        raise HTTPException(400, detail=f"unsupported event type: {payload.type}")

    ev = payload.event or {}
    if ev.get("type") != "message":
        return {"status": "ignored", "reason": "not a message event"}
    # Skip bot messages to avoid loops
    if ev.get("bot_id") or ev.get("subtype"):
        return {"status": "ignored", "reason": "bot message"}

    text = ev.get("text") or ""
    channel = ev.get("channel") or ""
    user = ev.get("user") or "unknown"

    if not text:
        return {"status": "ignored", "reason": "empty text"}

    get_audit().record_event(
        thread_id=f"slack-{channel}",
        agent="slack_adapter",
        event_type="inbound",
        reasoning=text[:200],
        input_summary=text[:120],
        output_summary=f"from user {user}",
        metadata={"channel": channel, "user": user},
    )

    # Translate to internal BOS turn
    from .chat import run_bos_turn, ChatRequest
    try:
        req = ChatRequest(message=text, username="advisor@bos.local")
        out = run_bos_turn(req, ctx)
    except Exception as e:
        log.exception("BOS turn failed for Slack message")
        await post_to_slack(channel, f"Sorry, an error occurred: {e}")
        return {"status": "error", "error": str(e)}

    # Post the response back to the originating Slack channel
    response_text = out.get("final_response") or "(no response)"
    sent = await post_to_slack(
        channel,
        response_text[:2900],  # Slack limit is 3000
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": response_text[:2900]}},
        ] if out.get("trace") else None,
    )
    return {"status": "ok", "sent_to_slack": sent, "thread_id": out.get("thread_id")}


class SlashCommand(BaseModel):
    token: str
    team_id: str
    channel_id: str
    user_id: str
    command: str
    text: str
    response_url: Optional[str] = None


@router.post("/command")
async def slack_command(
    cmd: SlashCommand,
    ctx: AuthContext = Depends(require_api_key),
):
    """Handle Slack slash commands like /bos summarize AAPL."""
    from .chat import run_bos_turn, ChatRequest
    req = ChatRequest(message=cmd.text, username="advisor@bos.local")
    out = run_bos_turn(req, ctx)
    response_text = out.get("final_response") or "(no response)"
    return {
        "response_type": "ephemeral",
        "text": response_text[:2900],
        "thread_id": out.get("thread_id"),
    }
