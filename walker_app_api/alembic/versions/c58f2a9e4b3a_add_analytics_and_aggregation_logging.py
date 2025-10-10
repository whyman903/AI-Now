"""add analytics and aggregation logging tables

Revision ID: c58f2a9e4b3a
Revises: b70393a23515
Create Date: 2025-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c58f2a9e4b3a"
down_revision: Union[str, None] = "b70393a23515"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # aggregation run summaries
    op.create_table(
        "aggregation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("total_new_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_items_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_with_thumbnails", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_aggregation_runs_started_at", "aggregation_runs", ["started_at"])
    op.create_index("ix_aggregation_runs_status", "aggregation_runs", ["status"])

    op.create_table(
        "aggregation_run_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("items_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_with_thumbnails", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["aggregation_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_aggregation_run_sources_run_id", "aggregation_run_sources", ["run_id"])
    op.create_index("ix_aggregation_run_sources_source_type", "aggregation_run_sources", ["source_type"])

    # user session tracking
    op.create_table(
        "user_sessions",
        sa.Column("session_id", sa.String(length=128), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("first_seen", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("page_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interactions", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_user_sessions_first_seen", "user_sessions", ["first_seen"])
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    # content interactions
    op.create_table(
        "content_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("interaction_type", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("source_page", sa.String(length=255), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.session_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_content_interactions_content_id", "content_interactions", ["content_id"])
    op.create_index("ix_content_interactions_session_id", "content_interactions", ["session_id"])
    op.create_index("ix_content_interactions_timestamp", "content_interactions", ["timestamp"])
    op.create_index("ix_content_interactions_type", "content_interactions", ["interaction_type"])

    # search queries
    op.create_table(
        "search_queries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("results_count", sa.Integer(), nullable=True),
        sa.Column("filters", postgresql.JSONB(), nullable=True),
        sa.Column("clicked_result_id", sa.String(length=128), nullable=True),
        sa.Column("clicked_position", sa.Integer(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.session_id"], ondelete="SET NULL"),
    )
    op.create_index("ix_search_queries_query", "search_queries", ["query"])
    op.create_index("ix_search_queries_timestamp", "search_queries", ["timestamp"])
    op.create_index("ix_search_queries_session_id", "search_queries", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_search_queries_session_id", table_name="search_queries")
    op.drop_index("ix_search_queries_timestamp", table_name="search_queries")
    op.drop_index("ix_search_queries_query", table_name="search_queries")
    op.drop_table("search_queries")

    op.drop_index("ix_content_interactions_type", table_name="content_interactions")
    op.drop_index("ix_content_interactions_timestamp", table_name="content_interactions")
    op.drop_index("ix_content_interactions_session_id", table_name="content_interactions")
    op.drop_index("ix_content_interactions_content_id", table_name="content_interactions")
    op.drop_table("content_interactions")

    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_index("ix_user_sessions_first_seen", table_name="user_sessions")
    op.drop_table("user_sessions")

    op.drop_index("ix_aggregation_run_sources_source_type", table_name="aggregation_run_sources")
    op.drop_index("ix_aggregation_run_sources_run_id", table_name="aggregation_run_sources")
    op.drop_table("aggregation_run_sources")

    op.drop_index("ix_aggregation_runs_status", table_name="aggregation_runs")
    op.drop_index("ix_aggregation_runs_started_at", table_name="aggregation_runs")
    op.drop_table("aggregation_runs")
