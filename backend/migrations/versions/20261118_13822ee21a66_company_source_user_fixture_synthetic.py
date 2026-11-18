"""company source (user / fixture / synthetic)

Revision ID: 13822ee21a66
Revises: 9633adfef360
Create Date: 2026-11-18 02:36:00.310811

Additive, backwards-compatible change:
- the new column has a server default ('user'), so every existing row gets a value
  immediately and old code that never mentions `source` keeps inserting rows without errors;
- the CHECK constraint only allows the three known values.
Downgrade drops the constraint and the column (the labels are lost, nothing else is).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13822ee21a66'
down_revision: Union[str, Sequence[str], None] = '9633adfef360'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('source', sa.String(length=20), server_default='user', nullable=False))
    op.create_check_constraint(op.f('ck_companies_source'), 'companies',
                               "source IN ('user', 'fixture', 'synthetic')")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_companies_source'), 'companies', type_='check')
    op.drop_column('companies', 'source')
