# Local development backup — 2026-10-21

Isolated backup of RF-One local development environments before moving to another PC.
Not to be merged. Base: `491694b907e370ccf0a55673a1a0400f55595a02` (branch handoff/2026-10-17).

- In place (same paths, base = handoff/2026-10-17): Selection AI prototype, Selection AI TEST deploy files,
  AI Organization local prototype files, Bank reconciliation chat preview (RF-One Web/previews/bank-reconciliation).
- `_local-backup/rf-one-bank-simple-who-rules/`: uncommitted Bank files of worktree feature/bank-simple-who-rules
  @ a455f9f46ef825fdc5255f6f2dd82d06716f691a (the code served on 5080). Shared files NOT included: 03 Software/RF-One Data Store/rfone_data_store/models.py, 03 Software/RF-One Web/domain_registry.py.
- `_local-backup/rf-one-c-bank-prototype/03 Software/C-Bank Prototype/`: worktree rf-one-c-bank-prototype, branch feature/c-bank-prototype @ 47310ae
- `_local-backup/RF Test/prototype/`: folder AI-RF-ONE/RF Test (not a git repository)

No database, .env, credential, CV, log or personal data is included. Restore: see RESTORE-INSTRUCTIONS.md in the
OneDrive backup folder RF-One/Backups/Local-Development/2026-10-21/.
