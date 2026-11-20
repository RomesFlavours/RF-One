"""Fail closed before importing the production app; no database writes or migrations."""
import os
import sys
from urllib.parse import urlsplit


def validate_environment(env):
    if urlsplit(env.get("RFONE_DATABASE_URL", "")).scheme not in ("postgresql", "postgresql+psycopg2"):
        raise RuntimeError("The server image requires an explicit PostgreSQL database URL.")
    for name in ("RFONE_FLASK_SECRET_KEY", "RFONE_SELECTION_DOCUMENT_BUCKET", "RFONE_WEB_BASE_URL", "RFONE_SELECTION_OPENAI_MODEL"):
        if not env.get(name):
            raise RuntimeError("Missing server configuration: " + name)
    if env.get("RFONE_SELECTION_REQUIRE_RFONE_LOGIN") != "1":
        raise RuntimeError("The server image requires RF-One authentication.")
    if env.get("RFONE_SELECTION_ENGINE") != "conversation":
        raise RuntimeError("The server image requires the conversational rules engine.")
    if env.get("RFONE_SELECTION_RULE_AI_PROVIDER") != "openai":
        raise RuntimeError("The server image requires the explicit OpenAI API provider.")
    if not (env.get("RFONE_SELECTION_OPENAI_API_KEY") or env.get("OPENAI_API_KEY")):
        raise RuntimeError("Missing application OpenAI credential.")


if __name__ == "__main__":
    try:
        validate_environment(os.environ)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        sys.exit(78)
    os.execvp(sys.argv[1], sys.argv[1:])
