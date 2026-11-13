"""Public Web Application Form intake orchestration (Task 5E Part B/C).
Thin glue over already-existing, unmodified services — résumé import
(`import_pipeline`), CandidatePerson/Application identity resolution
(`application_service`), Session linking (`session_service`), Acquisition
Source (`acquisition_source_service`), and Primary Screening
(`primary_screening_service`) — plus the two genuinely new Task 5E pieces
(`application_question_service`, `missing_evidence_service`). Nothing here
re-implements identity resolution, résumé parsing, or Primary Screening —
task §14's own "reuse existing CandidatePerson/Application identity-
resolution architecture."
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from . import application_question_service as aq_svc
from . import application_service as app_svc
from . import missing_evidence_service as me_svc
from . import primary_screening_service as ps_svc
from . import session_service as sess_svc


@dataclass
class IntakeResult:
    application: m.Application
    is_repeated_applicant: bool
    prior_application_count: int
    questionnaire: m.MissingEvidenceQuestionnaire | None = None
    warnings: list[str] = field(default_factory=list)


def submit_application(
    session: Session, *, restaurant_id: int, channel_publication_id: int | None, selection_session_id: int | None,
    target_role: str | None, original_filename: str, raw_text: str, content_hash: str,
    first_name: str, last_name: str, email: str, phone: str | None, candidate_message: str | None = None,
    answers: dict[int, str] | None = None, source_type: str = "WEB_APPLICATION_FORM",
) -> IntakeResult:
    """Task §14/§15 — the ONE function the public `/apply/<token>` route
    calls on a valid submission. Resolves/creates the `CandidatePerson`
    exactly the way every other Application entry point already does
    (never a parallel identity path), always creates a NEW Application
    (task §15 — a repeated applicant is never silently merged into a prior
    Application), links it to the Selection Session when the tracking link
    named one, attributes the Acquisition Source, preserves every
    structured first-screening answer, then runs Primary Screening and the
    Missing-Evidence readiness check automatically — completing the task's
    own end-to-end flow in one call."""

    from . import import_pipeline

    full_name = f"{first_name.strip()} {last_name.strip()}".strip()
    # `import_pipeline.import_one_resume` expects the résumé's own raw text
    # to already contain contact facts (task §14 reuses the SAME résumé-
    # parsing path every other intake route uses); we additionally pass the
    # form's own explicit name/email/phone ahead of the CV text so parsing
    # never depends on the candidate having typed contact details into the
    # CV body a second time.
    header = f"{full_name}\n{email}\n{phone or ''}\n\n"
    combined_text = header + (raw_text or "")

    imported = import_pipeline.import_one_resume(
        session, restaurant_id=restaurant_id, source_type=source_type, original_filename=original_filename,
        storage_path=None, raw_text=combined_text, content_hash=content_hash,
    )
    warnings: list[str] = []
    if imported.candidate_id is None:
        raise ValueError(imported.error or "Could not process the submitted résumé/CV.")

    prior_applications_for_candidate = app_svc.get_application_for_candidate(session, imported.candidate_id)
    if prior_applications_for_candidate is not None:
        # `import_one_resume` de-duplicates by content hash; an identical
        # resubmission resolves to the SAME Candidate/Application row.
        application = prior_applications_for_candidate
        is_new_application = False
    else:
        application = app_svc.create_application(
            session, candidate_id=imported.candidate_id, restaurant_id=restaurant_id, target_role=target_role,
        )
        is_new_application = True

    prior_applications = app_svc.list_prior_applications(session, application.id)

    if selection_session_id is not None and application.session_id is None:
        sess_svc.link_application_to_session(session, application.id, selection_session_id)

    if channel_publication_id is not None:
        application.channel_publication_id = channel_publication_id
        publication = session.get(m.ChannelPublication, channel_publication_id)
        channel = session.get(m.ChannelDefinition, publication.channel_id) if publication else None
        if channel is not None and channel.default_acquisition_source_id is not None:
            application.acquisition_source_id = channel.default_acquisition_source_id

    if candidate_message:
        app_svc.add_note(session, application.id, candidate_message, context_type="CANDIDATE_MESSAGE")

    session.flush()

    if is_new_application:
        for question_id, raw_answer in (answers or {}).items():
            if raw_answer is not None and str(raw_answer).strip():
                aq_svc.record_answer(session, application.id, question_id, raw_answer=str(raw_answer))

        run = ps_svc.create_screening_run(session, application.id)
        aq_svc.apply_answers_to_screening(session, application.id, run.id)
        questionnaire = me_svc.process_application_readiness(session, application.id)
    else:
        questionnaire = me_svc.get_pending_questionnaire(session, application.id)

    return IntakeResult(
        application=application, is_repeated_applicant=bool(prior_applications),
        prior_application_count=len(prior_applications), questionnaire=questionnaire, warnings=warnings,
    )
