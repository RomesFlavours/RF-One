"""Release overlay HOME_REMOVE_SELECTION_OLD_001 (Product Owner, 2026-11-17).

Removes the "Selection Old" card (SELECTION_OLD_ENTRY_001) from the Home
template inside the live rfone-web image. Fails the build unless exactly one
block is found and the patched template still parses.
"""
import sys
from pathlib import Path

import jinja2

path = Path(sys.argv[1]) / "RF-One Web" / "templates" / "home.html"
text = path.read_text(encoding="utf-8")
block = """        {% if domain.code == 'SELECTION' %}
          {#- SELECTION_OLD_ENTRY_001 — same service and access as Selection. #}
          <a class="domain-card {{ 'domain-card-released' if released else 'domain-card-unreleased' }}" href="{{ selection_old_link }}">
            <div class="domain-name">Selection Old</div>
            <div class="domain-description">The previous Selection interface: candidates, requirement sets, screening, interviews and settings.</div>
          </a>
        {% endif %}
"""
if text.count(block) != 1:
    sys.exit(f"Selection Old block found {text.count(block)} times; refusing to patch")
text = text.replace(block, "")
assert "Selection Old" not in text and "selection_old_link" not in text
jinja2.Environment().parse(text)
path.write_text(text, encoding="utf-8")
print("Home: Selection Old removed;", path)
