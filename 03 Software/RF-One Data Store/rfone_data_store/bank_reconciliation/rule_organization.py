"""Human-facing organization; validated signatures execute without AI at import."""
import json
KINDS = ("GENERAL", "RECOGNITION")

def inferred_kind(spec):
    if not isinstance(spec, dict):
        return "RECOGNITION"
    who = spec.get("who") or {}
    if who.get("mode") in ("between", "before_final_number", "to_end"):
        return "GENERAL"
    # Fixed counterparties and their conditional variants are recognition cards.
    if who.get("mode") == "fixed" or any((branch.get("who") or {}).get("mode") == "fixed" for branch in spec.get("branches", [])):
        return "RECOGNITION"
    literal_descriptors = [c for c in spec.get("conditions", []) if c.get("field") == "description" and c.get("value")]
    for branch in spec.get("branches", []):
        literal_descriptors.extend(c for c in branch.get("conditions", []) if c.get("field") == "description" and c.get("value"))
    # A literal descriptor without extraction is conservatively a reusable
    # signature. The person can explicitly organize a general criterion later.
    return "RECOGNITION" if literal_descriptors else "GENERAL"

def kind(rule, version):
    explicit = getattr(rule, "organization_kind", "AUTO")
    return explicit if explicit in KINDS else inferred_kind(json.loads(version.spec or "null") if version else None)
