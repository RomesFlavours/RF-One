#!/usr/bin/env python
"""Prepares the folder to upload to the Aruba hosting (SELECTION_ARUBA_IDENTITY_001).

    python make_upload.py              build the folder (asks the mailbox password, hidden)
    python make_upload.py --with-check same, with check.php switched on (prints its address)
    python make_upload.py aws-secret   store the shared secret in AWS Secrets Manager
                                       (a production change: only with the Product Owner's approval)

`build` copies `upload/` to %LOCALAPPDATA%\\RF-One\\Selection\\aruba-careers-upload\\careers
(outside OneDrive and Git) — the `careers` folder to drag into the FTP root of
the Aruba Hosting Windows, next to `mdb-database` — and writes there
`private/config.php` with:
- the password of rfone@romesflavours.com, typed by you and never shown;
- the secret shared with Selection on AWS: generated once with Python's
  `secrets`, then kept on every later build so both sides stay equal.

`aws-secret` creates or updates `rfone-selection/candidate-identity-handoff`
with that same secret and prints its ARN, for `apprunner-service.json`.
Nothing here prints the password or the secret.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "upload"
PACKAGE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RF-One" / "Selection" / "aruba-careers-upload"
OUTPUT = PACKAGE / "careers"  # uploaded as /careers in the FTP root
SECRET_NAME = "rfone-selection/candidate-identity-handoff"
REGION = "us-east-1"


def php_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def existing_secret(config: Path) -> str | None:
    if not config.is_file():
        return None
    match = re.search(r"'handoff_secret' => '([^'\\]{32,})'", config.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def build(args) -> int:
    config_path = OUTPUT / "private" / "config.php"
    previous = existing_secret(config_path)
    secret = previous or secrets.token_urlsafe(48)
    password = getpass.getpass("Password of rfone@romesflavours.com (hidden): ")
    if not password:
        print("No password typed: nothing was built.")
        return 1
    # Files are overwritten in place (a later build keeps working even if Windows holds a folder open).
    shutil.copytree(SOURCE, OUTPUT, ignore=shutil.ignore_patterns("config.php", "data"), dirs_exist_ok=True)
    sample = (SOURCE / "private" / "config.sample.php").read_text(encoding="utf-8")
    config = (sample
              .replace("'handoff_secret' => 'CHANGE-ME'", f"'handoff_secret' => {php_string(secret)}")
              .replace("'password' => '',", f"'password' => {php_string(password)},")
              .replace("'selection_handoff_url' => 'https://rfone.romesflavours.com/selection/careers/verified-identity'",
                       f"'selection_handoff_url' => {php_string(args.selection_url)}"))
    check_key = secrets.token_urlsafe(24) if args.with_check else ""
    config = config.replace("'diagnostics_key' => ''", f"'diagnostics_key' => {php_string(check_key)}")
    config = config.replace("configuration TEMPLATE", "configuration (written by make_upload.py — keep private)")
    if "CHANGE-ME" in config or php_string(password) not in config:
        print("The configuration template changed: config.php was not written.")
        return 1
    config_path.write_text(config, encoding="utf-8")
    print(f"Ready to upload: {OUTPUT}")
    print("Upload this whole 'careers' folder into the FTP root of the Aruba hosting, next to mdb-database")
    print("(see ISTRUZIONI_PUBBLICAZIONE.md).")
    if check_key:
        print(f"check.php is ON: open https://careers.romesflavours.com/check.php?key={check_key}")
        print("When it is all OK, build again without --with-check and upload private/config.php again.")
    print("Shared secret: " + ("kept from the previous build." if previous else
                               "newly generated - run `python make_upload.py aws-secret` once the AWS change is approved."))
    return 0


def aws_secret(_args) -> int:
    secret = existing_secret(OUTPUT / "private" / "config.php")
    if secret is None:
        print("Build the folder first (python make_upload.py).")
        return 1
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("secretsmanager", region_name=REGION)
    try:
        try:
            arn = client.put_secret_value(SecretId=SECRET_NAME, SecretString=secret)["ARN"]
        except client.exceptions.ResourceNotFoundException:
            arn = client.create_secret(
                Name=SECRET_NAME, SecretString=secret,
                Description="Selection: secret shared with the careers page on Aruba (identity token)")["ARN"]
    except ClientError as exc:
        print("AWS refused the change:", exc.response.get("Error", {}).get("Code"))
        return 1
    print("Secret stored. ARN:", arn)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", default="build", choices=["build", "aws-secret"])
    parser.add_argument("--with-check", action="store_true", help="switch check.php on (temporarily)")
    parser.add_argument("--selection-url", default="https://rfone.romesflavours.com/selection/careers/verified-identity")
    args = parser.parse_args()
    return build(args) if args.command == "build" else aws_secret(args)


if __name__ == "__main__":
    sys.exit(main())
