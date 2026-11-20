"""Independent settings stored in each position's existing context document."""
from __future__ import annotations
import json
from . import ai_adapter

FEATURES = (
    ("position_drafting", "AI position drafts", "Draft requirements, headcount and the English job ad."),
    ("message_drafting", "AI message drafts", "Draft messages without sharing candidate data."),
    ("cv_questions", "Résumé-based questions", "Add interview questions based on the candidate’s résumé."),
    ("cv_evaluation", "AI résumé and answer evaluation", "Read résumé evidence and interview answers against approved requirements."),
)

def context(position):
    try:
        value = json.loads(position.organization_context_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}

def get(position):
    data = context(position)
    saved = data.get("configuration", {})
    if not isinstance(saved, dict):
        saved = {}
    profile = saved.get("profile")
    if profile is None:
        # The original position snapshot is a baseline, never another position's settings.
        prefixes = ("Company profile (written by the owner in Selection): ",
                    "Profilo aziendale (scritto dal proprietario in Selection): ")
        profile = next((fact[len(prefix):] for fact in data.get("facts", []) if isinstance(fact, str)
                        for prefix in prefixes if fact.startswith(prefix)), "")
    values = {"profile": str(profile or "")}
    for key, _, _ in FEATURES:
        values[key] = bool(saved.get(key, False))
    return values

def save(position, values, *, actor_name):
    data = context(position)
    data["configuration"] = dict(values)
    data["configuration_updated_by"] = actor_name
    position.organization_context_json = json.dumps(data, ensure_ascii=False)

def bind(position):
    values = get(position)
    platform = ai_adapter.POLICY
    policy = ai_adapter.AIPolicy(
        ai_enabled=platform.ai_enabled and (values["position_drafting"] or values["message_drafting"]),
        cv_ai_authorized=platform.cv_ai_authorized and (values["cv_questions"] or values["cv_evaluation"]),
        features={key: values[key] and (platform.cv_ai_authorized if key.startswith("cv_") else platform.ai_enabled)
                  for key, _, _ in FEATURES})
    ai_adapter.bind_policy(policy)
    return policy
