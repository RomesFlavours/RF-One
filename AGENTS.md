# AGENTS.md

Instructions for AI development agents (Codex and others) working in the RF-One repository.

The canonical, version-controlled instructions are in [`CLAUDE.md`](CLAUDE.md). They apply to every agent, not only to Claude: read and follow them. This file adds nothing of its own and must not grow its own rules; any new rule belongs in `CLAUDE.md` or in the normative document it points to.

Standing rules most often missed by an agent:

- **How Works (UI_HOW_WORKS_001).** Every operational page has a visible "How Works" link to its own Help section; code and Help are one release unit; run `03 Software/Shared UI/check_how_works.py` before a release. Normative text: [`03 Software/Shared UI/How Works Standard.md`](03%20Software/Shared%20UI/How%20Works%20Standard.md).
- **Release Checklist:** [`03 Software/Infrastructure/deploy/RELEASE_CHECKLIST.md`](03%20Software/Infrastructure/deploy/RELEASE_CHECKLIST.md).
- **UI Rules:** [`03 Software/Shared UI/UI Rules.md`](03%20Software/Shared%20UI/UI%20Rules.md).
