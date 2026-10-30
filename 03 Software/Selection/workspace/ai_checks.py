"""Real provider checks using synthetic content; no email or candidate changes."""
import time
from . import ai_adapter, position_settings

CV = "Synthetic test only. Worked as a server for three years. Took orders, served tables and trained two new servers."

def run(position, feature):
    policy = position_settings.bind(position)
    if not policy.allows(feature):
        raise ValueError("Save and enable this feature for the position before testing it.")
    started = time.monotonic()
    if feature == "position_drafting":
        result = ai_adapter.draft_position(title=position.title, role=position.role_code,
            location=position.location_label,
            description="Synthetic connection test: one server opening, table-service experience required. Return two requirements.",
            company_facts=[position_settings.get(position)["profile"]] if position_settings.get(position)["profile"] else [],
            missing_facts=["pay", "benefits"])
        summary = f"Received {len(result['requirements'])} requirements and an English job ad."
    elif feature == "message_drafting":
        result = {"body": ai_adapter.draft_message(kind="GENERAL", title=position.title,
            location=position.location_label, facts="Synthetic test only: confirm receipt of the application. Do not send this message.")}
        summary = "Received an English message draft. No email was sent."
    elif feature == "cv_questions":
        result = {"questions": ai_adapter.interview_followups(title=position.title, role=position.role_code,
            requirements=["Server experience"], standard=["Are you available on weekends?"], cv_text=CV)}
        if not result["questions"]:
            raise ValueError("The provider returned no interview questions.")
        summary = f"Received {len(result['questions'])} résumé-based interview questions."
    elif feature == "cv_evaluation":
        result = ai_adapter.evaluate_candidate(requirements=[{"id": 1, "name": "Server experience",
            "description": "Experience taking orders and serving tables", "criticality": "MUST_HAVE"}],
            cv_text=CV, answers_text="Q: Can you explain your experience? A: I served tables and took orders.")
        quotes = sum(len(row["quotes"]) for row in result["requirements"].values())
        if not quotes:
            raise ValueError("The provider returned no verifiable evidence quotes.")
        summary = f"Evaluated the synthetic résumé with {quotes} quotes verified against the source text."
    else:
        raise ValueError("Unknown AI feature.")
    return {"ok": True, "summary": summary, "output": result,
            "seconds": round(time.monotonic() - started, 1), "provider": policy.provider_label}
