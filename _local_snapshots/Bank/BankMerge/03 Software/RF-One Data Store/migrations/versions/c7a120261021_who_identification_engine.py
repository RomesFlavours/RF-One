"""WHO identification engine: labels, recognition groups, movement links, runs (BANK_WHO_IDENTIFICATION_001). Additive."""
from alembic import op
import sqlalchemy as sa

revision = "c7a120261021"
down_revision = "f8e520261019"
branch_labels = depends_on = None

# The starting shared catalog of activity labels: English, one short
# definition each, no synonyms. The engine and people add to it.
SEED_LABELS = [
    ("Restaurant", "Serves prepared food and drinks to customers."),
    ("Bar", "Serves mainly alcoholic drinks for consumption on the premises."),
    ("Cafe & Bakery", "Sells coffee, pastries, bread or baked goods."),
    ("Grocery Store", "Retail store selling food and household groceries."),
    ("Warehouse Club", "Membership retailer selling goods in bulk (e.g. Costco, Sam's Club)."),
    ("Food Distributor", "Wholesale supplier of food products to businesses."),
    ("Beverage Distributor", "Wholesale supplier of drinks, wine, beer or spirits to businesses."),
    ("Wine & Liquor Store", "Retail store selling wine, beer or spirits."),
    ("Restaurant Supply", "Supplier of equipment, smallwares or disposables for food service."),
    ("Linen Service", "Rents or launders linens, uniforms or towels."),
    ("Bank", "Bank or credit union holding accounts or lending money."),
    ("Credit Card Issuer", "Issues credit cards and receives card payments."),
    ("Payment Processor", "Processes card or online payments for merchants."),
    ("Payroll Service", "Runs payroll, payroll taxes or HR services for employers."),
    ("Insurance", "Sells insurance coverage."),
    ("Tax Authority", "Government body collecting taxes."),
    ("Government Agency", "Public body issuing permits, licences, fines or services."),
    ("Utility", "Provides electricity, gas, water or waste services."),
    ("Telecommunications", "Provides phone or mobile service."),
    ("Internet Service", "Provides internet connectivity or hosting."),
    ("Software & SaaS", "Sells software, apps or online subscriptions."),
    ("Online Marketplace", "Online platform selling goods from many sellers."),
    ("Retail Store", "General retail store selling consumer goods."),
    ("Pharmacy", "Sells medicines and health products."),
    ("Hardware & Home Improvement", "Sells tools, building materials or home improvement goods."),
    ("Fuel Station", "Sells fuel for vehicles."),
    ("Ride Hailing", "Provides rides through an app or taxi service."),
    ("Delivery Platform", "Delivers food or goods ordered through an app."),
    ("Airline", "Sells air travel."),
    ("Hotel & Lodging", "Provides overnight accommodation."),
    ("Travel Agency", "Sells travel bookings on behalf of providers."),
    ("Car Rental", "Rents vehicles."),
    ("Real Estate & Landlord", "Leases or manages property."),
    ("Storage Facility", "Rents storage space."),
    ("Professional Services", "Accounting, legal, consulting or similar professional work."),
    ("Repair & Maintenance", "Repairs or maintains equipment, vehicles or buildings."),
    ("Cleaning Service", "Provides cleaning or janitorial services."),
    ("Advertising & Marketing", "Sells advertising, marketing or promotion."),
    ("Shipping & Postal", "Ships parcels or provides postal services."),
    ("Education", "Provides schooling, courses or training."),
    ("Healthcare", "Provides medical, dental or other health care."),
    ("Charity", "Non-profit organization receiving donations."),
    ("Entertainment", "Provides events, recreation or leisure activities."),
    ("Individual", "A private person, not a business."),
]


def _key(name):
    import re
    key = re.sub(r"[^0-9a-z]+", " ", name.lower()).strip()
    return key[:-1] if key.endswith("s") and not key.endswith("ss") else key


def upgrade():
    op.create_table(
        "bank_who_identify_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(8), nullable=False),
        sa.Column("transaction_ids_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(16), nullable=False, server_default="RECORDS"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor_transaction_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("counters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("scope IN ('ALL', 'NEW')", name="ck_bank_who_identify_run_scope"),
    )
    op.create_index("ix_bank_who_identify_runs_status", "bank_who_identify_runs", ["status"])
    labels = op.create_table(
        "bank_who_labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("name_key", sa.String(64), nullable=False),
        sa.Column("definition", sa.String(255), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name_key", name="uq_bank_who_label_name_key"),
        sa.CheckConstraint("source IN ('SEED', 'AI', 'HUMAN')", name="ck_bank_who_label_source"),
    )
    op.create_table(
        "bank_occurrence_labels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=False),
        sa.Column("label_id", sa.Integer(), sa.ForeignKey("bank_who_labels.id"), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("bank_who_identify_runs.id"), nullable=True),
        sa.Column("decided_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("occurrence_id", "label_id", name="uq_bank_occurrence_label"),
        sa.CheckConstraint("source IN ('AI', 'HUMAN')", name="ck_bank_occurrence_label_source"),
    )
    op.create_index("ix_bank_occurrence_labels_occurrence_id", "bank_occurrence_labels", ["occurrence_id"])
    op.create_index("ix_bank_occurrence_labels_label_id", "bank_occurrence_labels", ["label_id"])
    op.create_table(
        "bank_who_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=False, unique=True),
        sa.Column("identity_method", sa.String(16), nullable=True),
        sa.Column("identity_evidence", sa.Text(), nullable=True),
        sa.Column("identity_sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("activity", sa.Text(), nullable=True),
        sa.Column("label_status", sa.String(8), nullable=False, server_default="NONE"),
        sa.Column("label_question", sa.Text(), nullable=True),
        sa.Column("label_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_run_id", sa.Integer(), sa.ForeignKey("bank_who_identify_runs.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("label_status IN ('NONE', 'ACCEPTED', 'PENDING', 'HUMAN')", name="ck_bank_who_profile_label_status"),
    )
    op.create_table(
        "bank_who_recognition_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("variant_text", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("sources_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("candidates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("samples_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("ai_answer_json", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("bank_who_identify_runs.id"), nullable=True),
        sa.Column("decided_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_bank_who_recognition_key"),
        sa.CheckConstraint("kind IN ('NAME', 'GENERIC')", name="ck_bank_who_recognition_key_kind"),
    )
    op.create_index("ix_bank_who_recognition_keys_status", "bank_who_recognition_keys", ["status"])
    op.create_index("ix_bank_who_recognition_keys_occurrence_id", "bank_who_recognition_keys", ["occurrence_id"])
    op.create_table(
        "bank_who_identifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("financial_transaction_id", sa.Integer(), sa.ForeignKey("financial_transactions.id"), nullable=False, unique=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("method", sa.String(16), nullable=True),
        sa.Column("recognition_key_id", sa.Integer(), sa.ForeignKey("bank_who_recognition_keys.id"), nullable=True),
        sa.Column("rule_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("current_occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("current_source", sa.String(8), nullable=True),
        sa.Column("discrepancy", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("bank_who_identify_runs.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bank_who_identifications_occurrence_id", "bank_who_identifications", ["occurrence_id"])
    op.create_index("ix_bank_who_identifications_status", "bank_who_identifications", ["status"])
    op.create_index("ix_bank_who_identifications_recognition_key_id", "bank_who_identifications", ["recognition_key_id"])
    op.bulk_insert(labels, [dict(name=n, name_key=_key(n), definition=d, source="SEED", active=True) for n, d in SEED_LABELS])


def downgrade():
    for table in ("bank_who_identifications", "bank_who_recognition_keys", "bank_who_profiles",
                  "bank_occurrence_labels", "bank_who_labels", "bank_who_identify_runs"):
        op.drop_table(table)
