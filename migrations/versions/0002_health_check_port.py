"""health_check_port table: per-hostname TLS probe port overrides

Revision ID: 0002_health_check_port
Revises: 0001_initial
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_health_check_port"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Fresh databases get this table from 0001's metadata create_all; only add it when
    # upgrading a database that predates it.
    if not sa.inspect(op.get_bind()).has_table("health_check_port"):
        op.create_table(
            "health_check_port",
            sa.Column("domain", sa.String(), primary_key=True),
            sa.Column("port", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("health_check_port")
