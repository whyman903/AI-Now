"""add extraction_method and feed_url to aggregation_sources

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-01-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aggregation_sources",
        sa.Column("extraction_method", sa.String(20), nullable=False, server_default="css_selectors"),
    )
    op.add_column(
        "aggregation_sources",
        sa.Column("feed_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("aggregation_sources", "feed_url")
    op.drop_column("aggregation_sources", "extraction_method")
