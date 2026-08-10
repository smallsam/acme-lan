"""app_user, user_session and oidc_state tables for dashboard login

Revision ID: 0003_users_and_sessions
Revises: 0002_health_check_port
Create Date: 2026-08-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_users_and_sessions"
down_revision = "0002_health_check_port"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("app_user"):
        op.create_table(
            "app_user",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("username", sa.String(), nullable=False, index=True),
            sa.Column("email", sa.String(), nullable=False, server_default=""),
            sa.Column("password_hash", sa.String(), nullable=False, server_default=""),
            sa.Column("provider", sa.String(), nullable=False, server_default="local"),
            sa.Column("oidc_subject", sa.String(), nullable=True, index=True),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not inspector.has_table("user_session"):
        op.create_table(
            "user_session",
            sa.Column("token", sa.String(), primary_key=True),
            sa.Column("user_id", sa.String(), nullable=False, index=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    if not inspector.has_table("oidc_state"):
        op.create_table(
            "oidc_state",
            sa.Column("state", sa.String(), primary_key=True),
            sa.Column("nonce", sa.String(), nullable=False, server_default=""),
            sa.Column("code_verifier", sa.String(), nullable=False, server_default=""),
            sa.Column("redirect_uri", sa.String(), nullable=False, server_default=""),
            sa.Column("next_url", sa.String(), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("oidc_state")
    op.drop_table("user_session")
    op.drop_table("app_user")
