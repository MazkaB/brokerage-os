"""
BOS configuration layer.

All settings are loaded from environment variables with sensible defaults
so the system can boot locally without external dependencies.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root (one level above /app)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOS_", env_file=".env", extra="ignore")

    # --- Vertex AI (LLM + embeddings, authenticated via ADC) ---
    gcp_project_id: str = Field(default="", alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="us-central1", alias="GCP_LOCATION")
    gemini_llm_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_LLM_MODEL")
    gemini_embedding_model: str = Field(default="text-embedding-004", alias="GEMINI_EMBEDDING_MODEL")

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # --- Storage ---
    db_path: str = str(_PROJECT_ROOT / "app" / "data" / "bos.db")
    chroma_path: str = str(_PROJECT_ROOT / "app" / "data" / "chroma")
    kb_path: str = str(_PROJECT_ROOT / "knowledge_base")

    # --- Security ---
    api_key: str = "bos-local-dev-key-CHANGE-ME"
    jwt_secret: str = "bos-local-jwt-secret-CHANGE-ME"
    encryption_key: str = "bos-local-encryption-key-32bytes"

    # --- HITL ---
    approval_timeout_seconds: int = 1800

    # --- LangSmith (disabled by default) ---
    langsmith_tracing: bool = False

    @property
    def project_root(self) -> Path:
        return _PROJECT_ROOT

    def ensure_dirs(self) -> None:
        for p in [
            Path(self.db_path).parent,
            Path(self.chroma_path),
            Path(self.kb_path),
        ]:
            p.mkdir(parents=True, exist_ok=True)


# Roles & permissions used by the RBAC layer.
ROLE_PERMISSIONS = {
    "advisor": ["client.read", "message.send", "workflow.view", "approval.request"],
    "operations": ["client.read", "client.write", "crm.update", "workflow.view"],
    "compliance": ["client.read", "approval.approve", "approval.reject", "audit.read"],
    "manager": [
        "client.read", "client.write", "crm.update",
        "approval.approve", "approval.reject",
        "workflow.view", "workflow.assign", "agent.override", "audit.read",
    ],
    "admin": ["*"],  # wildcard
}

# Approval-gate triggers (FR6). Any workflow tagged with these intents must HITL.
APPROVAL_INTENTS = [
    "investment_recommendation",
    "compliance_exception",
    "document_submission",
    "account_opening",
    "account_transfer",
    "trade_execution",
    "high_risk_operation",
]


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


def get_role_permissions(role: str) -> List[str]:
    return ROLE_PERMISSIONS.get(role, [])


# Tool Permission Matrix (PRD §12 + §14).
# Maps each worker to an allow-list of tool modules it may invoke. Any
# tool not in the allow-list is forbidden. Enforced by graph.fan_out_workers.
TOOL_POLICY: dict = {
    "crm_worker": {
        "allowed": ["crm.get_client", "crm.create_client", "crm.update_client",
                    "crm.record_conversation", "crm.list_clients"],
        "forbidden": [],
    },
    "document_worker": {
        "allowed": ["document.prepare_pdf", "document.fill_form",
                    "document.extract_info", "document.list"],
        "forbidden": ["crm.update_client", "calendar.schedule"],
    },
    "compliance_worker": {
        "allowed": ["compliance.run_kyc", "compliance.run_aml",
                    "compliance.validate_policy", "retrieval.search"],
        "forbidden": ["crm.update_client", "calendar.schedule", "research.security"],
    },
    "research_worker": {
        "allowed": ["research.market_news", "research.security",
                    "research.compare_funds"],
        "forbidden": ["crm.update_client", "calendar.schedule"],
    },
    "calendar_worker": {
        "allowed": ["calendar.schedule", "calendar.list_events", "calendar.reminder"],
        "forbidden": ["crm.update_client", "research.security"],
    },
    "retrieval_worker": {
        "allowed": ["retrieval.search"],
        "forbidden": ["crm.update_client", "calendar.schedule", "research.security"],
    },
}
