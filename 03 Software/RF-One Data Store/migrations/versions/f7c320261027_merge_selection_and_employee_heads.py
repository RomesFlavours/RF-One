"""Merge the additive Selection candidate and employee registry branches.

No schema operations: each branch retains its existing migrations.
"""
revision = "f7c320261027"
down_revision = ("b8e620261021", "e6b220261026")
branch_labels = None
depends_on = None

def upgrade():
    pass

def downgrade():
    pass
