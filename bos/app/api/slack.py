"""
Slack adapter (Phase 1 inbound webhook).

Provides:
  POST /api/slack/event     - receives Slack Events API callbacks
  POST /api/slack/command   - receives Slack slash commands

Phase 1 supports two patterns:
  1. Slack App with Event Subscriptions → URL points here
  2. Slack incoming webhook from a custom workflow

The adapter translates Slack events into BOS ChatRequests so the rest of
the LangGraph topology runs unchanged. Responses are posted back to Slack
via SLACK_BOT_TOKEN + chat.postMessage (if configured).

If no token is configured, responses are returned in the HTTP body so the
caller (e.g. a Slack workflow that uses Webhooks) can deliver them.

Outbound notifications (e.g. approval-required cards) also go through this
module via `post_to_slack`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..audit import get_audit
from ..config import get_settings
from ..security import AuthContext
from .deps import require_api_key

log = logging.getLogger("bos.api.slack")
router = APIRouter(prefix="/api/slack", tags=["slack"])


def _slack_token() -> Optional[str]:
    return os.environ.get("SLACK_BOT_TOKEN")


def _resolve_channel(req_payload: Dict[str, Any]) -> Optional[str]:
    """Try to find a Slack channel id from the inbound payload."""
    if "event" in req_payload:
        return req_payload["event"].get("channel")
    return req_payload.get("channel_id")


async def post_to_slack(channel: str, text: str, blocks: Optional[list] = None) -> bool:
    """Send a message to Slack. Returns True on success.

    Requires SLACK_BOT_TOKEN env var. No-op (returns False) if not set.
    """
    token = _slack_token()
    if not token:
        log.info("SLACK_BOT_TOKEN not set; skipping outbound message to %s", channel)
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
