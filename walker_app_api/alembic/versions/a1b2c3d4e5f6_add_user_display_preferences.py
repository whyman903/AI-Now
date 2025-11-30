"""add user display preferences table for tile colors

Revision ID: a1b2c3d4e5f6
Revises: b6d059d6a00c
Create Date: 2025-11-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "b6d059d6a00c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_display_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tile_color_palette", sa.String(length=50), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_display_preferences_user_id", "user_display_preferences", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_display_preferences_user_id", table_name="user_display_preferences")
    op.drop_table("user_display_preferences")

