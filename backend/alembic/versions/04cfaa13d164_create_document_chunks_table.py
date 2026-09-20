"""create document_chunks table

Revision ID: 04cfaa13d164
Revises: 635f56c7f820
Create Date: 2026-09-16 00:00:03.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = "04cfaa13d164"
down_revision: Union[str, Sequence[str], None] = "635f56c7f820"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"),
    )
    # lists=10 targets a small ops knowledge base (roughly tens to a few
    # hundred chunks to start, growing toward low thousands) — sqrt(N) for
    # N in that range is single/low-double digits. A large `lists` value
    # actively hurts correctness at small N: ivfflat's default probes=1
    # only checks the single nearest list centroid, so with too many lists
    # relative to row count, a query can miss matching rows entirely rather
    # than merely losing recall. search_documents (backend/app/agent/tools.py)
    # additionally sets ivfflat.probes=10 per query to probe multiple lists.
    # If the corpus grows well past low-thousands, REINDEX with a larger
    # `lists` (or switch to HNSW) — no application-code change needed either way.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_ivfflat "
        "ON document_chunks USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 10)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_ivfflat")
    op.drop_table("document_chunks")
