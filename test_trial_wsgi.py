"""Check the packaged launcher with a fresh synthetic SQLite DB, no external calls."""
import os
from pathlib import Path
import re
import secrets
import tempfile

with tempfile.TemporaryDirectory(prefix="render_trial_check_", ignore_cleanup_errors=True) as folder:
    os.environ.update(RFONE_RENDER_TRIAL="1", RFONE_RENDER_TRIAL_LOCAL_TEST="1",
        RFONE_DATABASE_URL="sqlite:///" + (Path(folder) / "test.db").as_posix(),
        RFONE_FLASK_SECRET_KEY=secrets.token_urlsafe(32),
        RFONE_TRIAL_ADMIN_PASSWORD=secrets.token_urlsafe(32))
    import trial_wsgi as trial
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    client = Client(trial.application, Response)
    def get(path):
        return client.get(path, base_url="https://localhost")
    assert get("/trial-health").json["status"] == "ok"
    assert get("/selection/").status_code == 302
    page = get("/login")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    response = client.post("/login", base_url="https://localhost", data={
        "csrf_token": csrf, "username": "render-trial",
        "password": os.environ["RFONE_TRIAL_ADMIN_PASSWORD"]})
    assert response.status_code == 302
    page = get("/selection/")
    assert page.status_code == 200 and "Open positions" in page.text
    assert "Synthetic data only" in page.text
    assert page.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert get("/selection/candidate/bridge/health").json["enabled"] is False
    assert os.environ["RFONE_AI_PROVIDER"] == "TRIAL_DISABLED"
    assert not os.environ.get("RFONE_SELECTION_DOCUMENT_BUCKET")
    print("PASS packaged WSGI: DB bootstrap, HTTPS login, Selection mount, banner, noindex, bridge disabled")
    trial.selection._engine.dispose()
    from db import _engine
    _engine.dispose()
