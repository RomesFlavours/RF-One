"""Selection's operational interface (SELECTION_AI_INTEGRATION_001), from the
approved Selection AI prototype: the internal position workspace
(`routes.py`, blueprint `positions`) and the public candidate pages
(`careers.py`, blueprint `careers`).

AI permissions are read once here: `RFONE_SELECTION_AI=1` lets AI draft
positions and messages (no candidate data sent); `RFONE_SELECTION_AI_CV=1`
also lets it read résumés and interview answers. Both off by default.
"""

from __future__ import annotations

import os

from . import ai_adapter
from .careers import bp as careers_bp
from .routes import _cfg
from .routes import bp as positions_bp
from . import sp_routes  # noqa: E402,F401  CV Selection SP routes on the positions blueprint
from . import interviews  # noqa: E402,F401  Interviews tab routes on the positions blueprint

from . import configuration  # noqa: F401 - register Configurations before blueprint installation
from . import observation_templates  # noqa: F401 - observation template configuration routes
from . import requirements_priorities  # noqa: F401 - current Selection PDL rules
from . import candidate_board  # noqa: F401 - PDL filters and candidate actions
from . import candidate_review  # noqa: F401 - candidate analysis and selected questions
from . import automation_routes  # noqa: F401
from . import selection_criteria  # noqa: F401 - local Old engine criterion editor

PUBLIC_BLUEPRINT = careers_bp.name


def register_workspace(app, *, SessionFactory, documents, rfone_web_base_url) -> None:
    from . import rule_ai
    rule_ai.validate_configuration()
    app.before_request(ai_adapter.reset_policy)
    app.teardown_request(lambda error: ai_adapter.reset_policy())
    from . import aruba_bridge
    aruba_bridge.install()
    from . import mail_delivery
    mail_delivery.install()
    _cfg.SessionFactory = SessionFactory
    _cfg.documents = documents
    _cfg.rfone_web_base_url = rfone_web_base_url
    ai_adapter.install_guard(ai_enabled=os.environ.get("RFONE_SELECTION_AI") == "1",
                             cv_ai_authorized=os.environ.get("RFONE_SELECTION_AI_CV") == "1")
    app.register_blueprint(positions_bp)
    app.register_blueprint(careers_bp)
