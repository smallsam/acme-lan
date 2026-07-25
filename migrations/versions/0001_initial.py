"""initial baseline schema

Creates the full current schema from the SQLModel metadata. This is the baseline; later
schema changes are added as new revisions and applied automatically on upgrade.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-25
"""
from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

import acme_lan.models  # noqa: F401  (populates SQLModel.metadata)

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst=True makes this safe on databases created by an earlier create_all().
    SQLModel.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    SQLModel.metadata.drop_all(bind=op.get_bind())
