"""Create the initial operational and local analytical schema."""

from alembic import op

from crawltech.models import Base

revision = "0001_operational_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create all tables and constraints represented by the baseline models."""
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop the baseline schema in dependency order."""
    Base.metadata.drop_all(bind=op.get_bind())
