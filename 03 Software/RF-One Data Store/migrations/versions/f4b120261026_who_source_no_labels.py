"""WHO + Source classification; permanently remove WHO activity labels."""
from alembic import op
import sqlalchemy as sa
import json
revision = "f4b120261026"
down_revision = "e3a120261024"
branch_labels = depends_on = None

REMOVED = {"labels", "who_labels", "label_hints", "label_ids", "label_definitions", "label_status", "label_question", "label_attempts"}
def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in REMOVED}
    if isinstance(value, list):
        return [clean(x) for x in value if not (isinstance(x, dict) and
                (x.get("stage") == "Labels" or str(x.get("kind", "")).startswith("WHO Labels")))]
    return value

def uses_label(value):
    if isinstance(value, dict):
        return value.get("field") == "label" or any(uses_label(v) for v in value.values())
    return isinstance(value, list) and any(uses_label(x) for x in value)

def upgrade():
    op.create_table("bank_who_source_classifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("occurrence_id", sa.Integer, sa.ForeignKey("bank_occurrences.id"), nullable=False),
        sa.Column("payment_instrument_id", sa.Integer, sa.ForeignKey("payment_instruments.id"), nullable=False),
        sa.Column("transaction_reason_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id")),
        sa.Column("updated_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("occurrence_id", "payment_instrument_id", name="uq_bank_who_source_classification"))
    op.create_index("ix_bank_who_source_classifications_occurrence_id", "bank_who_source_classifications", ["occurrence_id"])
    op.create_index("ix_bank_who_source_classifications_payment_instrument_id", "bank_who_source_classifications", ["payment_instrument_id"])
    bind = op.get_bind()
    pairs = set(bind.execute(sa.text("select distinct e.occurrence_id,t.payment_instrument_id from financial_transactions t join bank_transaction_explanations e on e.id=t.explanation_id where e.occurrence_id is not null and t.payment_instrument_id is not null")).fetchall())
    tx = dict(bind.execute(sa.text("select id,payment_instrument_id from financial_transactions")).fetchall())
    last = next((r[0] for r in bind.execute(sa.text("select id,scope_json from bank_engine_runs order by id desc")) if json.loads(r[1]).get("kind") == "all"), None)
    if last:
        for (payload,) in bind.execute(sa.text("select payload_json from bank_engine_results where run_id=:id"), dict(id=last)):
            r = json.loads(payload)
            if r.get("who_id") and tx.get(r['txn_id']): pairs.add((r['who_id'], tx[r['txn_id']]))
    active = set(bind.execute(sa.text("select id from bank_occurrences where status='ACTIVE'")).scalars())
    for who, source in sorted(pairs):
        if who in active:
            bind.execute(sa.text("insert into bank_who_source_classifications(occurrence_id,payment_instrument_id) values(:w,:s)"), dict(w=who,s=source))
    # An unscoped WHO default is deliberately not copied to any Source.
    op.drop_table("bank_occurrence_labels")
    op.drop_table("bank_who_labels")
    with op.batch_alter_table("bank_who_profiles") as batch:
        batch.drop_constraint("ck_bank_who_profile_label_status", type_="check")
        for column in ("label_status", "label_question", "label_attempts", "activity"): batch.drop_column(column)
    for table, key, column in (("bank_engine_results", "rowid", "payload_json"),
                               ("bank_flow_artifacts", "id", "payload"),
                               ("bank_who_recognition_keys", "id", "ai_answer_json")):
        # Engine results have a composite key; use its two columns portably below.
        if table == "bank_engine_results":
            records = bind.execute(sa.text("select run_id,financial_transaction_id,payload_json from bank_engine_results")).fetchall()
            for run_id, txn_id, payload in records:
                if not payload: continue
                data = json.loads(payload)
                bind.execute(sa.text("update bank_engine_results set payload_json=:p where run_id=:r and financial_transaction_id=:t"),dict(p=json.dumps(clean(data)),r=run_id,t=txn_id))
        else:
            for ident, payload in bind.execute(sa.text(f"select id,{column} from {table}")).fetchall():
                if not payload: continue
                try: data=json.loads(payload)
                except (ValueError, TypeError): continue
                bind.execute(sa.text(f"update {table} set {column}=:p where id=:i"),dict(p=json.dumps(clean(data)),i=ident))
    for ident, rule, spec in bind.execute(sa.text("select id,rule_id,spec from bank_ai_rule_versions")).fetchall():
        if not spec: continue
        try: data=json.loads(spec)
        except (ValueError, TypeError): continue
        if uses_label(data):
            bind.execute(sa.text("update bank_ai_rules set status='INACTIVE' where id=:r"),dict(r=rule))
            data={"engine":"RETIRED", "reason":"Retired activity-label rule"}
        bind.execute(sa.text("update bank_ai_rule_versions set spec=:s where id=:i"),dict(s=json.dumps(clean(data)),i=ident))

def downgrade():
    raise RuntimeError("Removed label data cannot be restored by downgrade; restore the pre-migration backup.")
