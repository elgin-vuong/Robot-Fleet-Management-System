"""enable pgvector extension

Revision ID: 51242ae870d1
Revises: 248a25f997ae
Create Date: 2026-09-16 00:00:01.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "51242ae870d1"
down_revision: Union[str, Sequence[str], None] = "248a25f997ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP EXTENSION IF EXISTS vector")
