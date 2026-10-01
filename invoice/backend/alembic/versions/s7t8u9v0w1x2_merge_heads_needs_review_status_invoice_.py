"""merge heads: NEEDS_REVIEW status + invoice_pdf_payloads

Revision ID: s7t8u9v0w1x2
Revises: g5h6i7j8k9l0, m1n2o3p4q5r6
Create Date: 2026-08-31 16:07:38.414167

g5h6i7j8k9l0 (PaymentStatus.NEEDS_REVIEW, 2026-08-28) and m1n2o3p4q5r6
(invoice_pdf_payloads table, 2026-08-31) were each branched off the same
parent (f4a5b6c7d8e9) independently and both ended up merged into main —
found because `alembic heads` reported two, which means `alembic upgrade
head` would refuse to run ("Multiple head revisions are present") in any
environment that tries to migrate main as it stood right after both
landed. No-op merge point, no schema change of its own.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 's7t8u9v0w1x2'
down_revision: Union[str, None] = ('g5h6i7j8k9l0', 'm1n2o3p4q5r6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
