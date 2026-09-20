"""create incidents table

Revision ID: 248a25f997ae
Revises: bdf01c707480
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "248a25f997ae"
down_revision: Union[str, Sequence[str], None] = "bdf01c707480"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("robot_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["robot_id"],
            ["robots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incidents_robot_id_created_at", "incidents", ["robot_id", "created_at"])
    op.create_index("ix_incidents_status", "incidents", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_robot_id_created_at", table_name="incidents")
    op.drop_table("incidents")
