"""Template-literal localization; imported facts and export schemas are unchanged."""
import json, os, html
from pathlib import Path
_CATALOG = json.loads(Path(__file__).with_name("ui_it.json").read_text(encoding="utf-8"))
def ui(value):
    return html.unescape(_CATALOG.get(value, value) if os.environ.get("RFONE_UI_LANGUAGE", "en") == "it" else value)
