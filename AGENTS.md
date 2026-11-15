# AGENTS.md

Instructions for AI development agents (Codex and others) working in the RF-One repository.

The canonical, version-controlled instructions are in [`CLAUDE.md`](CLAUDE.md). They apply to every agent, not only to Claude: read and follow them. This file adds nothing of its own and must not grow its own rules; any new rule belongs in `CLAUDE.md` or in the normative document it points to.

**Before any task, read the repository's main instructions (`CLAUDE.md`).**

Standing rules most often missed by an agent:

- **Contextual help on every page (UI_CONTEXTUAL_HELP_001, Product Owner, 2026-11-05).** Verbatim:
  > Prima di ogni attività leggere le istruzioni principali del repository. Ogni pagina RF-One deve avere un aiuto contestuale accessibile tramite un link coerente che apre una modale. Le home spiegano il sistema o modulo; le altre pagine spiegano la pagina specifica. Ogni creazione o modifica di pagina deve includere la verifica e l'eventuale aggiornamento del relativo aiuto. L'attività non è completa se interfaccia e spiegazione non corrispondono.

  How: the one component `03 Software/Shared UI/help/_how_works.html` (identical copy in each app), `help_section`/`help_title` declared by the page, content in `templates/help/<section>.html`, registry and check as in the standard below. Section *Contextual help on every page* of `CLAUDE.md`.
- **How Works (UI_HOW_WORKS_001).** Code and help are one release unit; run `03 Software/Shared UI/check_how_works.py` before a release. Normative text: [`03 Software/Shared UI/How Works Standard.md`](03%20Software/Shared%20UI/How%20Works%20Standard.md).
- **Release Checklist:** [`03 Software/Infrastructure/deploy/RELEASE_CHECKLIST.md`](03%20Software/Infrastructure/deploy/RELEASE_CHECKLIST.md).
- **UI Rules:** [`03 Software/Shared UI/UI Rules.md`](03%20Software/Shared%20UI/UI%20Rules.md).
