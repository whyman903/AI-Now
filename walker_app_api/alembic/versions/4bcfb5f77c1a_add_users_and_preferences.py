"""Add users and source preference tables and extend content items."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "4bcfb5f77c1a"
down_revision = "b70393a23515"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("auth_provider", sa.String(length=50), nullable=False, server_default="local"),
        sa.Column("provider_user_id", sa.String(length=255), nullable=True),
        sa.Column("password_hash", sa.String(length=512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.create_unique_constraint("uq_users_provider_mapping", "users", ["auth_provider", "provider_user_id"])

    op.create_table(
        "user_refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_index("ix_user_refresh_tokens_user_id", "user_refresh_tokens", ["user_id"])
    op.create_index("ix_user_refresh_tokens_active", "user_refresh_tokens", ["user_id", "revoked_at"])

    op.create_table(
        "user_source_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_key", sa.String(length=100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_user_source_preferences_user_id", "user_source_preferences", ["user_id"])
    op.create_unique_constraint(
        "uq_user_source_preferences_user_source",
        "user_source_preferences",
        ["user_id", "source_key"],
    )

    op.add_column("content_items", sa.Column("source_key", sa.String(length=100), nullable=True))
    op.create_index("ix_content_items_source_key", "content_items", ["source_key"])


def downgrade() -> None:
    op.drop_index("ix_content_items_source_key", table_name="content_items")
    op.drop_column("content_items", "source_key")

    op.drop_constraint("uq_user_source_preferences_user_source", "user_source_preferences", type_="unique")
    op.drop_index("ix_user_source_preferences_user_id", table_name="user_source_preferences")
    op.drop_table("user_source_preferences")

    op.drop_index("ix_user_refresh_tokens_active", table_name="user_refresh_tokens")
    op.drop_index("ix_user_refresh_tokens_user_id", table_name="user_refresh_tokens")
    op.drop_table("user_refresh_tokens")

    op.drop_constraint("uq_users_provider_mapping", "users", type_="unique")
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_table("users")
