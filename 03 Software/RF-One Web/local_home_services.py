"""Local routing corresponding to CloudFront, on the same canonical database.

No services are provisioned and no migrations or account bootstrap run here.
The sibling applications retain their own routes and authorization checks.
"""
import importlib.util
import os
from pathlib import Path
import sys


def install(shell):
    software = Path(__file__).resolve().parent.parent
    os.environ['RFONE_SELECTION_CANONICAL_LOCAL'] = '1'
    os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN'] = '1'
    os.environ['RFONE_WEB_BASE_URL'] = 'http://127.0.0.1:5097'
    os.environ['RFONE_FLASK_SECRET_KEY'] = shell.secret_key
    for name in ('RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL'):
        os.environ.pop(name, None)
    apps = {}
    for name, folder in [('selection', 'Selection'), ('tips', 'Tips')]:
        previous_path = list(sys.path)
        previous_routes = sys.modules.get('routes')
        if name == 'tips':
            # RF-One already loaded Training with its isolated auth/db modules.
            sys.modules['routes'] = sys.modules['_training_internal_routes']
        sys.path.insert(0, str(software / folder))
        spec = importlib.util.spec_from_file_location('rfone_local_' + name, software / folder / 'app.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = previous_path
            if previous_routes is None:
                sys.modules.pop('routes', None)
            else:
                sys.modules['routes'] = previous_routes
        module.app.secret_key = shell.secret_key
        module.app.config.update(SESSION_COOKIE_SECURE=False,
            SESSION_COOKIE_NAME=shell.config['SESSION_COOKIE_NAME'],
            TRUSTED_HOSTS=['127.0.0.1', 'localhost'])
        apps[name] = module.app
        from rfone_data_store.web_access import install_access_context
        install_access_context(module.app, module.SessionFactory)
    root = shell.wsgi_app

    def dispatch(environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path == '/selection' or path.startswith('/selection/'):
            return apps['selection'](environ, start_response)
        if (path == '/tips' or path.startswith('/tips/')) and not path.startswith('/tips/runs'):
            return apps['tips'](environ, start_response)
        return root(environ, start_response)

    shell.wsgi_app = dispatch
    shell.extensions['local_home_services'] = apps
