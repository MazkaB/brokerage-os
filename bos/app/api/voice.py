"""
Voice channel (Phase 2).

Provides:
  POST /api/voice/transcribe  - audio upload → text
  POST /api/voice/synthesize  - text → audio bytes
  WS   /api/voice/ws          - bidirectional voice chat

Uses Google Cloud Speech-to-Text and Text-to-Speech. Falls back to a
stub when BOS_VOICE_ENABLED is not set or credentials are missing.

Setup:
  1. gcloud services enable speech.googleapis.com texttospeech.googleapis.com
  2. Set BOS_VOICE_ENABLED=true in .env
  3. (ADC handles the rest)

UI: web/voice.html
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from ..security import AuthContext, authenticate_api_key
from .deps import require_api_key

log = logging.getLogger("bos.api.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])


def voice_enabled() -> bool:
    return os.environ.get("BOS_VOICE_ENABLED", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Speech-to-Text
# ---------------------------------------------------------------------------
async def transcribe_audio(audio_bytes: bytes, sample_rate: int = 16000,
                           language_code: str = "en-US") -> str:
    """Transcribe audio bytes to text via Google Speech-to-Text.

    Args:
        audio_bytes: raw LINEAR16 (PCM) audio bytes (no WAV header)
        sample_rate: sample rate in Hz (default 16000)
        language_code: BCP-47 language code
    """
    if not voice_enabled():
        return "[voice transcription disabled - set BOS_VOICE_ENABLED=true]"
    try:
        from google.cloud import speech
        client = speech.SpeechAsyncClient()
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate,
            language_code=language_code,
            enable_automatic_punctuation=True,
        )
        response = await client.recognize(config=config, audio=audio)
        results = response.results
        if not results:
            return ""
        return results[0].alternatives[0].transcript
    except ImportError:
        log.warning("google-cloud-speech not installed")
        return "[google-cloud-speech not installed]"
    except Exception as e:
        log.warning("transcribe failed: %s", e)
        return f"[transcription error: {e}]"


# ---------------------------------------------------------------------------
# Text-to-Speech (uses Vertex AI / Google Cloud TTS)
# ---------------------------------------------------------------------------
async def synthesize_speech(text: str, voice_name: str = "en-US-Standard-A",
                            language_code: str = "en-US") -> bytes:
    """Synthesize speech from text. Returns MP3 audio bytes."""
    if not voice_enabled():
        return b""
    try:
        from google.cloud import texttospeech
        client = texttospeech.TextToSpeechAsyncClient()
        synthesis_input = texttospeech.SynthesisInput(text=text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=language_code, name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.0, pitch=0.0,
        )
        response = await client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )
        return response.audio_content
    except ImportError:
        log.warning("google-cloud-texttospeech not installed")
        return b""
    except Exception as e:
        log.warning("synthesize failed: %s", e)
        return b""


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------
class TranscribeResponse(BaseModel):
    text: str


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(require_api_key),
):
    """Upload audio (LINEAR16 / WAV / MP3) and get text back."""
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "empty audio")
    # Strip WAV header if present (44 bytes)
    if audio[:4] == b"RIFF" and len(audio) > 44:
        audio = audio[44:]
    text = await transcribe_audio(audio)
    return TranscribeResponse(text=text)


@router.post("/synthesize")
async def synthesize_endpoint(
    text: str,
    ctx: AuthContext = Depends(require_api_key),
):
    """Convert text → MP3 audio bytes. Returns binary audio."""
    audio = await synthesize_speech(text)
    if not audio:
        raise HTTPException(503, "TTS disabled or failed")
    from fastapi.responses import Response
    return Response(content=audio, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# WebSocket: full-duplex voice chat
# ---------------------------------------------------------------------------
@router.websocket("/ws")
async def voice_ws(websocket: WebSocket):
    """Bidirectional voice chat.

    Client → Server: binary frames of audio
    Server → Client: text responses (after STT → BOS → TTS)
    """
    await websocket.accept()
    try:
        # Auth handshake
        hello = await websocket.receive_json()
        ctx = authenticate_api_key(hello.get("api_key", ""))
        if not ctx.is_authenticated:
            await websocket.send_json({"type": "error", "detail": "invalid api_key"})
            await websocket.close()
            return
        await websocket.send_json({"type": "ready"})

        while True:
            # Receive audio frame
            audio = await websocket.receive_bytes()
            if not audio:
                continue
            # Strip WAV header if present
            if audio[:4] == b"RIFF" and len(audio) > 44:
                audio = audio[44:]
            # STT
            text = await transcribe_audio(audio)
            if not text:
                continue
            await websocket.send_json({"type": "transcript", "text": text})

            # Run BOS turn
            from .chat import run_bos_turn, ChatRequest
            req = ChatRequest(message=text, username="advisor@bos.local")
            try:
                out = run_bos_turn(req, ctx)
            except Exception as e:
                await websocket.send_json({"type": "error", "detail": str(e)})
                continue
            response = out.get("final_response") or ""
            await websocket.send_json({"type": "response", "text": response})

            # TTS (send audio back as binary frame)
            audio_out = await synthesize_speech(response[:1000])
            if audio_out:
                await websocket.send_bytes(audio_out)

    except WebSocketDisconnect:
        log.info("voice ws client disconnected")
    except Exception as e:
        log.warning("voice ws error: %s", e)
