"""
LLM and embedding clients backed by Google Vertex AI.

Vertex AI authenticates via Application Default Credentials (ADC) — no API
key needed. To set up ADC:

    gcloud auth application-default login

The Google Cloud project and location are read from environment variables
GCP_PROJECT_ID / GCP_LOCATION (or GOOGLE_CLOUD_PROJECT /
GOOGLE_CLOUD_LOCATION as fallbacks).

Models (configurable via .env):
  * Chat:       gemini-2.5-flash (fast, cost-effective)
  * Embeddings: text-embedding-004 (768-dim)
"""
from __future__ import annotations

import functools
import logging
import os
from typing import Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from .config import Settings, get_settings

log = logging.getLogger("bos.llm")


def _resolve_project_location(settings: Settings) -> tuple[str, str]:
    """Resolve the GCP project + location from multiple env var fallbacks."""
    project = (
        settings.gcp_project_id
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT_ID")
        or ""
    )
    location = (
        settings.gcp_location
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("GCP_LOCATION")
        or "us-central1"
    )
    # Vertex AI SDKs read these env vars to set the quota project. Setting
    # them here means callers don't have to.
    if project:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", location)
        # Quota project is required when using user-account ADC.
        os.environ.setdefault("GOOGLE_CLOUD_QUOTA_PROJECT", project)
    return project, location


@functools.lru_cache()
def get_llm(temperature: float = 0.2, model: Optional[str] = None) -> BaseChatModel:
    """Return a cached ChatVertexAI instance."""
    from langchain_google_vertexai import ChatVertexAI

    settings = get_settings()
    project, location = _resolve_project_location(settings)
    if not project:
        raise RuntimeError(
            "GCP project not configured. Set GCP_PROJECT_ID in your .env, "
            "or run: gcloud config set project <PROJECT_ID>"
        )

    llm = ChatVertexAI(
        model=model or settings.gemini_llm_model,
        project=project,
        location=location,
        temperature=temperature,
        max_retries=3,
    )
    log.info("LLM ready (Vertex AI): model=%s project=%s location=%s temp=%.2f",
             llm.model_name, project, location, temperature)
    return llm


@functools.lru_cache()
def get_embeddings(model: Optional[str] = None) -> Embeddings:
    """Return a cached VertexAIEmbeddings instance."""
    from langchain_google_vertexai import VertexAIEmbeddings

    settings = get_settings()
    project, location = _resolve_project_location(settings)
    if not project:
        raise RuntimeError(
            "GCP project not configured. Set GCP_PROJECT_ID in your .env, "
            "or run: gcloud config set project <PROJECT_ID>"
        )

    emb = VertexAIEmbeddings(
        model=model or settings.gemini_embedding_model,
        project=project,
        location=location,
    )
    log.info("Embeddings ready (Vertex AI): model=%s project=%s",
             settings.gemini_embedding_model, project)
    return emb


def ping_llm() -> bool:
    """Verify the Vertex AI setup works. Returns True on success."""
    try:
        from langchain_core.messages import HumanMessage
        llm = get_llm()
        llm.invoke([HumanMessage(content="ping")])
        emb = get_embeddings()
        emb.embed_query("ping")
        return True
    except Exception as e:
        log.warning("Vertex AI ping failed: %s", e)
        return False


# Backwards-compat alias (older code referenced `ping_gemini`).
def ping_gemini() -> bool:
    return ping_llm()
