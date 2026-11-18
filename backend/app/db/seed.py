"""Seed development data:  python -m app.db.seed

Safe to run repeatedly (existing rows are left alone). Creates:
  - policy version v1 (the default assessment policy from the brief)
  - a reviewer and a viewer demo account

Passwords come from SEED_*_PASSWORD settings (.env). If blank, a random password
is generated and printed ONCE - nothing secret is stored in the repository.
"""
import secrets

from sqlalchemy import select

from app.config import settings
from app.db.enums import Category, Role
from app.db.models import PolicyVersion, User
from app.db.session import SessionLocal
from app.security import hash_password

POLICY_V1 = {
    "version": "v1",
    "description": (
        "Default assessment policy: 7 categories. Accounting = Yes by explicit business rule "
        "(provenance 'rule', not site-derived). All other categories require website evidence."
    ),
    "rules": {
        "categories": [c.value for c in Category],
        "rule_based": {Category.ACCOUNTING.value: {"status": "yes", "reason": "Default assessment policy rule"}},
    },
}


def seed_policy(db) -> None:
    if db.get(PolicyVersion, POLICY_V1["version"]) is None:
        db.add(PolicyVersion(**POLICY_V1, is_active=True))
        print("policy v1 created")
    else:
        print("policy v1 already exists")


def seed_user(db, email: str, role: Role, configured_password: str) -> None:
    if db.scalar(select(User).where(User.email == email)):
        print(f"user {email} already exists")
        return
    password = configured_password or secrets.token_urlsafe(12)
    db.add(User(email=email, password_hash=hash_password(password), role=role))
    shown = "(from .env)" if configured_password else f"{password}  <- generated, save it now"
    print(f"user {email} [{role}] created, password: {shown}")


def main() -> None:
    with SessionLocal.begin() as db:
        seed_policy(db)
        seed_user(db, settings.seed_reviewer_email, Role.REVIEWER, settings.seed_reviewer_password)
        seed_user(db, settings.seed_viewer_email, Role.VIEWER, settings.seed_viewer_password)


if __name__ == "__main__":
    main()
