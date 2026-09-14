#!/usr/bin/env python
"""Continuous Aruba mailbox acquisition for Purchased / Invoice Intake.

Polls `invoices@romesflavours.com` (or whichever mailbox `ARUBA_IMAP_*`
configures) on a configurable interval, delivering every new documental
attachment through the existing Invoice Intake pipeline. See
`mailbox_acquisition/README.md` for configuration and
`mailbox_acquisition/acquisition_service.py` for the pipeline itself.

Usage:
    python run_mailbox_acquisition.py            # continuous loop
    python run_mailbox_acquisition.py --once      # one poll cycle, then exit (cron/manual)
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mailbox_acquisition.acquisition_service import DEFAULT_DB_PATH, poll_once  # noqa: E402
from mailbox_acquisition.acquisition_store import AcquisitionStore  # noqa: E402
from mailbox_acquisition.config import MailboxConfigError, load_config  # noqa: E402
from mailbox_acquisition.imap_client import ArubaImapClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--once", action="store_true", help="Run a single poll cycle and exit, instead of looping.")
    args = parser.parse_args(argv)

    try:
        config = load_config()
    except MailboxConfigError as exc:
        print(f"Mailbox configuration error: {exc}")
        return 1

    store = AcquisitionStore(DEFAULT_DB_PATH)
    imap_client = ArubaImapClient(config)
    try:
        while True:
            try:
                result = poll_once(config, imap_client, store)
                print(
                    "Mailbox poll: "
                    f"{result.delivered} delivered, {result.duplicates} technical duplicate(s), "
                    f"{result.skipped_already_processed} already processed, "
                    f"{len(result.attachment_failures)} attachment failure(s), "
                    f"{len(result.message_failures)} message failure(s)"
                )
                for uid, filename, reason in result.attachment_failures:
                    print(f"  FAILED attachment: message={uid} file={filename!r}: {reason}")
                for uid, reason in result.message_failures:
                    print(f"  FAILED message fetch: message={uid}: {reason}")
            except Exception as exc:  # noqa: BLE001 — a whole-cycle failure (e.g. connection drop) must never kill the daemon
                # `exc` here is already redacted where it could plausibly carry
                # the password (see acquisition_service.redact); nothing else
                # in this loop ever touches config.password directly.
                print(f"Mailbox poll cycle failed, will retry next interval: {exc}")
                imap_client.close()

            if args.once:
                break
            time.sleep(config.poll_interval_seconds)
    finally:
        imap_client.close()
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
