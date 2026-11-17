"""Build-only smoke test. Never connects to an operational database."""
import os
import sys
import tempfile

os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + tempfile.mktemp(prefix='rfone_test_email_image_', suffix='.db')
os.environ['RFONE_WEB_TEST_SECRET_KEY'] = 'email-image-check-not-a-production-secret'
sys.path.insert(0, '/app/RF-One Web')
sys.path.insert(0, '/app/RF-One Data Store')
import app

endpoints = {rule.endpoint for rule in app.app.url_map.iter_rules()}
assert {'email_control', 'email_detail', 'email_requests', 'email_status', 'email_action', 'home', 'login'} <= endpoints
print('Email image route imports passed; no database migrations or SMTP sends.')
