"""Production entry point (gunicorn wsgi:app). Configuration comes from the environment;
no tables are created and no Clover call is made here."""
import os

import bootstrap  # noqa: F401
from rfone_data_store.database import create_configured_engine, create_session_factory
from app import create_app

app = create_app(create_session_factory(create_configured_engine(os.environ['RFONE_DATABASE_URL'])),
                 secret=os.environ.get('KITCHEN_BOARD_SECRET'),
                 view_token=os.environ.get('KITCHEN_BOARD_VIEW_TOKEN'),
                 release_token=os.environ.get('KITCHEN_BOARD_RELEASE_TOKEN'),
                 language=os.environ.get('RFONE_UI_LANGUAGE', 'en'))


@app.get('/health')
def health():
    return {'ok': True}
