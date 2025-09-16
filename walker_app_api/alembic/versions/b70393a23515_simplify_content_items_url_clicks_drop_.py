"""simplify content_items: url+clicks, drop legacy fields

Revision ID: b70393a23515
Revises: e477fc9e389e
Create Date: 2025-09-16 12:51:31.354336

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b70393a23515'
down_revision: Union[str, None] = 'e477fc9e389e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add new columns
    op.add_column('content_items', sa.Column('url', sa.Text(), nullable=True))
    op.add_column('content_items', sa.Column('clicks', sa.Integer(), nullable=False, server_default='0'))

    # 2) Backfill url from legacy source_url if present
    op.execute("UPDATE content_items SET url = source_url WHERE url IS NULL AND source_url IS NOT NULL")

    # 3) Drop legacy unique/indexes on normalized_url (if they exist)
    op.execute("DO $$ BEGIN\n"
              "    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_content_items_normalized_url') THEN\n"
              "        ALTER TABLE content_items DROP CONSTRAINT uq_content_items_normalized_url;\n"
              "    END IF;\n"
              "END $$;")
    op.execute("DROP INDEX IF EXISTS ix_content_items_normalized_url;")
    op.execute("DROP INDEX IF EXISTS uq_content_items_normalized_url;")

    # 4) Create unique constraint on url
    op.create_unique_constraint('uq_content_items_url', 'content_items', ['url'])

    # 5) Set NOT NULL on url
    op.alter_column('content_items', 'url', existing_type=sa.Text(), nullable=False)

    # 6) Drop legacy columns we no longer use (safe if they exist)
    for col in ['content', 'ai_summary', 'normalized_url', 'embedding', 'source_url']:
        op.execute(f"ALTER TABLE content_items DROP COLUMN IF EXISTS {col};")


def downgrade() -> None:
    # Recreate legacy columns (nullable) for downgrade compatibility
    op.add_column('content_items', sa.Column('source_url', sa.Text(), nullable=True))
    op.add_column('content_items', sa.Column('content', sa.Text(), nullable=True))
    op.add_column('content_items', sa.Column('ai_summary', sa.Text(), nullable=True))
    op.add_column('content_items', sa.Column('normalized_url', sa.Text(), nullable=True))
    op.add_column('content_items', sa.Column('embedding', sa.Text(), nullable=True))

    # Backfill legacy source_url from url
    op.execute("UPDATE content_items SET source_url = url WHERE source_url IS NULL AND url IS NOT NULL")

    # Drop new unique constraint and columns
    op.drop_constraint('uq_content_items_url', 'content_items', type_='unique')
    op.execute("ALTER TABLE content_items DROP COLUMN IF EXISTS url;")
    op.execute("ALTER TABLE content_items DROP COLUMN IF EXISTS clicks;")

    # Recreate prior indexes/unique on normalized_url
    op.create_unique_constraint('uq_content_items_normalized_url', 'content_items', ['normalized_url'])
    op.create_index('ix_content_items_normalized_url', 'content_items', ['normalized_url'])
