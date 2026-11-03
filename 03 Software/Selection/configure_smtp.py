"""Sets up the SMTP mailbox Selection uses for candidate verification codes.

The password is typed by the Product Owner at a hidden prompt — it is never
passed on the command line, printed, or logged.

    python configure_smtp.py setup   ONE step for the Product Owner ("Configura Email
                                     Selection.cmd"): asks the password, proves it with
                                     one real test message to the test mailbox, then
                                     stores it locally (DPAPI) and in AWS Secrets Manager
    python configure_smtp.py local   store host/port/user + DPAPI-protected password
                                     in %LOCALAPPDATA%\\RF-One\\Selection\\smtp.json
    python configure_smtp.py aws     store the password in AWS Secrets Manager
                                     (secret rfone-selection/smtp-password) for production;
                                     --from-local takes it from the DPAPI file, no prompt
    python configure_smtp.py test    send ONE real test message, using the local
                                     configuration, only to the test mailbox below

Defaults are Aruba's published parameters for a domain mailbox: smtps.aruba.it,
port 465, implicit TLS (TLS 1.2 minimum), full address as user name.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "RF-One Data Store"))

import smtp_local_config  # noqa: E402

DEFAULT_HOST = "smtps.aruba.it"
DEFAULT_PORT = 465
DEFAULT_USERNAME = "rfone@romesflavours.com"
TEST_RECIPIENT = "rfone@romesflavours.com"  # the only address a test message may go to
AWS_SECRET_NAME = "rfone-selection/smtp-password"


def _ask_password() -> str:
    first = getpass.getpass("Password della casella (non viene mostrata): ")
    if not first or getpass.getpass("Ripeti la password: ") != first:
        sys.exit("Le password non coincidono o sono vuote: nulla è stato salvato.")
    return first


def configure_local(args) -> None:
    path = smtp_local_config.save(host=args.host, port=args.port, username=args.username, password=_ask_password())
    print(f"Configurazione SMTP locale salvata (password protetta con Windows DPAPI): {path}")


def _store_in_aws(password: str, profile: str) -> str:
    import boto3

    client = boto3.Session(profile_name=profile, region_name="us-east-1").client("secretsmanager")
    try:
        arn = client.describe_secret(SecretId=AWS_SECRET_NAME)["ARN"]
        client.put_secret_value(SecretId=AWS_SECRET_NAME, SecretString=password)
        return f"Segreto AWS aggiornato: {arn}"
    except client.exceptions.ResourceNotFoundException:
        arn = client.create_secret(Name=AWS_SECRET_NAME, SecretString=password,
                                   Description="RF-One Selection: SMTP password of the verification-code mailbox")["ARN"]
        return f"Segreto AWS creato: {arn}"


def configure_aws(args) -> None:
    if args.from_local:
        if not smtp_local_config.apply_to_environment():
            sys.exit("Nessuna configurazione locale da cui leggere la password.")
        password = os.environ["RFONE_SMTP_PASSWORD"]
    else:
        password = _ask_password()
    print(_store_in_aws(password, args.profile))


def _send_test_message(settings) -> str:
    from rfone_data_store.technical import smtp_email

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    smtp_email.send_email(
        settings=settings, to_address=TEST_RECIPIENT, from_address=settings.username,
        subject="RF-One Selection - SMTP test",
        text_body=(f"Test message from RF-One Selection via {settings.host}:{settings.port}.\n"
                   f"Sent at {stamp}. Verification codes for candidates use this same path.\n"))
    return stamp


def setup(args) -> None:
    from rfone_data_store.technical import smtp_email

    print(f"Configurazione email di Selection - casella {DEFAULT_USERNAME} ({DEFAULT_HOST}:{DEFAULT_PORT})")
    for attempt in range(3):
        password = _ask_password()
        settings = smtp_email.SmtpSettings(host=DEFAULT_HOST, port=DEFAULT_PORT, username=DEFAULT_USERNAME,
                                           password=password)
        try:
            stamp = _send_test_message(settings)
            break
        except smtp_email.SmtpSendError as exc:
            if str(exc) == "authentication_failed" and attempt < 2:
                print("Aruba ha rifiutato la password. Riprova.")
                continue
            sys.exit(f"Invio di prova NON riuscito ({exc}): nulla è stato salvato.")
    else:
        sys.exit("Password rifiutata tre volte: nulla è stato salvato.")
    print(f"1/3 Password corretta: messaggio di prova accettato da Aruba per {TEST_RECIPIENT} ({stamp}).")
    path = smtp_local_config.save(host=DEFAULT_HOST, port=DEFAULT_PORT, username=DEFAULT_USERNAME, password=password)
    print(f"2/3 Salvata per Selection locale, protetta con Windows DPAPI: {path}")
    try:
        print("3/3 " + _store_in_aws(password, args.profile))
    except Exception as exc:  # noqa: BLE001 — AWS login may be expired; Claude completes this step from the local file
        print(f"3/3 AWS non raggiungibile ora ({type(exc).__name__}): la registrazione in AWS verrà completata "
              "da Claude dalla copia protetta, senza chiederti di nuovo la password.")
    print("\nFatto. Puoi chiudere questa finestra.")


def send_test(_args) -> None:
    from rfone_data_store.technical import smtp_email

    if not smtp_local_config.apply_to_environment():
        sys.exit("Nessuna configurazione locale: eseguire prima `python configure_smtp.py setup`.")
    try:
        stamp = _send_test_message(smtp_email.settings_from_environment())
    except smtp_email.SmtpSendError as exc:
        sys.exit(f"Invio NON riuscito: {exc}")
    print(f"Il server SMTP ha accettato il messaggio di prova per {TEST_RECIPIENT} ({stamp}). "
          "Controllare l'arrivo nella casella.")


def main() -> None:
    parser = argparse.ArgumentParser(description="SMTP per i codici di verifica di Selection")
    sub = parser.add_subparsers(dest="command", required=True)
    local = sub.add_parser("local")
    local.add_argument("--host", default=DEFAULT_HOST)
    local.add_argument("--port", type=int, default=DEFAULT_PORT)
    local.add_argument("--username", default=DEFAULT_USERNAME)
    local.set_defaults(run=configure_local)
    aws = sub.add_parser("aws")
    aws.add_argument("--profile", default="rfone-dev-login")
    aws.add_argument("--from-local", action="store_true")
    aws.set_defaults(run=configure_aws)
    one = sub.add_parser("setup")
    one.add_argument("--profile", default="rfone-dev-login")
    one.set_defaults(run=setup)
    sub.add_parser("test").set_defaults(run=send_test)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
