"""Release controls change language; candidate facts and protocol codes do not."""
import os
import unittest
from unittest.mock import patch
from jinja2 import Environment
from local_i18n import ItalianLiterals


class ReleaseLocale(unittest.TestCase):
    def render(self, language, source, **facts):
        with patch.dict(os.environ, {"RFONE_UI_LANGUAGE": language}):
            return Environment(extensions=[ItalianLiterals]).from_string(source).render(**facts)

    def test_english_controls_and_unchanged_candidate(self):
        text = self.render("en", '<button>Salva Regola</button><p>{{ candidate }}</p><button>Applica Filtri e Regole</button>', candidate="Persona con continuità")
        self.assertIn("Save Rule", text)
        self.assertIn("Apply Filters and Rules", text)
        self.assertIn("Persona con continuità", text)

    def test_local_italian_stays_italian(self):
        self.assertIn("Salva Regola", self.render("it", '<button>Salva Regola</button>'))

    def test_script_and_identifiers(self):
        text = self.render("en", '<script>const code="requirements"; const label="Salva Regola";</script><input name="pdl" value="__all__">')
        self.assertIn('code="requirements"', text)
        self.assertIn('"Save Rule"', text)
        self.assertIn('name="pdl" value="__all__"', text)


if __name__ == "__main__":
    unittest.main()
