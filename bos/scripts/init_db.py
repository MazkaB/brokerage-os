"""
Initialize the BOS database and seed demo data.

Usage:
    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audit import get_audit
from app.config import get_settings
from app.logging_setup import configure_logging
from app.memory.long_term import get_long_term_memory
from app.tools.crm import crm_list_clients

configure_logging()


def main() -> None:
    s = get_settings()
    print(f"DB path:    {s.db_path}")
    print(f"Chroma dir: {s.chroma_path}")
    print(f"KB dir:     {s.kb_path}")

    # Initialize schemas (idempotent)
    audit = get_audit()
    ltm = get_long_term_memory()

    # Seed demo profiles
    seeds = [
        {
            "user_id": "u_advisor", "username": "advisor", "role": "advisor",
            "display_name": "Demo Advisor",
            "risk_tolerance": "moderate",
            "preferred_markets": ["US-EQ"],
            "kyc_status": "verified",
            "account_type": "Individual",
            "notes": "Phase 1 demo advisor profile",
        },
        {
            "user_id": "u_ops", "username": "ops", "role": "operations",
            "display_name": "Ops User",
            "risk_tolerance": "conservative",
            "preferred_markets": ["US-BOND"],
            "kyc_status": "verified",
            "account_type": "Individual",
            "notes": "Phase 1 demo ops profile",
        },
        {
            "user_id": "u_comp", "username": "compliance", "role": "compliance",
            "display_name": "Compliance Officer",
            "risk_tolerance": "conservative",
            "preferred_markets": [],
            "kyc_status": "verified",
            "account_type": "Individual",
            "notes": "Phase 1 demo compliance officer profile",
        },
    ]
    for profile in seeds:
        existing = ltm.get_profile(profile["user_id"])
        if not existing:
            ltm.upsert_profile(profile)
            print(f"  seeded profile: {profile['user_id']}")
        else:
            print(f"  profile exists: {profile['user_id']}")

    clients = crm_list_clients().data.get("clients", [])
    print(f"  CRM clients: {len(clients)}")
    print("\nDB initialized successfully.")


if __name__ == "__main__":
    main()
