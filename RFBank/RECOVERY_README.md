# RFBank complete local recovery copy

This directory contains the RFBank source and PayPal work copied from the sibling
RFBank directory, plus a private recovery snapshot under `recovery/`.
The original installation and running application were not moved or changed.

## Contents

- `app.py`, `chat_app.py`, `engine.py`, `_setup/`, `03 Software/`, `static/`,
  `templates/`, `parking/`: existing RFBank application and preserved work.
- `PAYPAL_IMPORT.md`, `requirements-paypal.txt`, `test_paypal_import.py`,
  `paypal-import-handoff.zip` and `.bundle`: PayPal software and handoff.
- `recovery/rfone.db`: consistent SQLite backup of the local RFBank database.
- `recovery/conversations/`: existing chat conversations.
- Other `recovery/` files preserve local state, previews and session material.
  They are private recovery files, excluded from Git. Do not publish them.

## Recover on the home PC

The application expects its active runtime data at
`%LOCALAPPDATA%\RF-One\RFBank`, not inside OneDrive. Keep the database here as
an identifiable recovery snapshot, not a second active database.

Stop the home RFBank application before restoring. Compare any existing home data
first: do not overwrite a newer or different database/conversation history.
If no home runtime exists, restore `recovery/rfone.db`, `recovery/conversations/`
and the session key into that local runtime directory. Do not restore server PIDs,
logs, caches or preview directories as active runtime state.

The launcher expects the existing RF-One Python environment at
`%LOCALAPPDATA%\RF-One\Bank\venv`. Restore/install the required environment
before starting. `Avvia RFBank.cmd` launches relative to this source directory,
but its Python path is the existing user's local installation.

PayPal source code is prepared and tested; the recovered shell intentionally
retains its read-only gate. See PAYPAL_IMPORT.md before enabling uploads in the
actual writable home environment. No import or reconciliation was run by this copy.

The GitHub push of the earlier PayPal handoff was blocked by authentication.
This directory does not indicate that anything has been pushed or deployed.
