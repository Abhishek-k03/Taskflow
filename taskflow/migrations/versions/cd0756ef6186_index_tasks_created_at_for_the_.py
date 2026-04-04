"""index tasks created_at for the unfiltered list query

Revision ID: cd0756ef6186
Revises: 326a0919e9eb
Create Date: 2026-08-25 22:34:54.313415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd0756ef6186'
down_revision: Union[str, Sequence[str], None] = '326a0919e9eb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ix_tasks_status_created_at already covers the filtered list query, but
    # it cannot serve the unfiltered one - a composite index is only usable
    # for ordering when the leading column is constrained, and here it isn't.
    op.create_index('ix_tasks_created_at', 'tasks', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_tasks_created_at', table_name='tasks')
