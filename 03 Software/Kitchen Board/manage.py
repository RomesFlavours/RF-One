"""Explicit Kitchen Board setup, worker and local server commands."""
import argparse
import logging
import os
from datetime import datetime

import bootstrap  # noqa: F401
from rfone_data_store.database import create_configured_engine, create_session_factory


def main():
    parser = argparse.ArgumentParser(description='RF-One Kitchen Board')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('upgrade-display')
    init = commands.add_parser('init')
    init.add_argument('--location-id', type=int, required=True)
    init.add_argument('--since', required=True)
    sync = commands.add_parser('sync')
    sync.add_argument('--location-id', type=int, required=True)
    sync.add_argument('--interval-seconds', type=float, default=15)
    serve = commands.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=5090)
    serve.add_argument('--language',choices=('en','it'),default=os.environ.get('RFONE_UI_LANGUAGE'))
    args = parser.parse_args()
    url = os.environ.get('RFONE_DATABASE_URL')
    if not url:
        parser.error('Set RFONE_DATABASE_URL to the existing canonical database; no fallback database is created')
    if args.command == 'upgrade-display':
        from sqlalchemy import inspect
        from display_settings import DisplaySettings
        engine=create_configured_engine(url)
        if not inspect(engine).has_table('kitchen_boards'):
            parser.error('Initialize Kitchen Board first')
        DisplaySettings.__table__.create(engine,checkfirst=True)
    elif args.command == 'init':
        since = datetime.fromisoformat(args.since)
        if since.tzinfo is None:
            parser.error('--since requires a timezone offset')
        from store import initialize
        initialize(create_configured_engine(url), args.location_id, since)
    elif args.command == 'sync':
        if args.interval_seconds < 5:
            parser.error('Polling interval must be at least 5 seconds')
        from sync import run_forever
        logging.basicConfig(level=logging.INFO)
        run_forever(create_session_factory(create_configured_engine(url)), args.location_id, args.interval_seconds)
    else:
        from app import create_app
        local = os.environ.get('KITCHEN_BOARD_LOCAL') == '1'
        if local and args.host not in ('127.0.0.1', 'localhost', '::1'):
            parser.error('Local mode may bind only to loopback; use HTTPS for shared devices')
        app = create_app(create_session_factory(create_configured_engine(url)),
            secret=os.environ.get('KITCHEN_BOARD_SECRET'),
            view_token=os.environ.get('KITCHEN_BOARD_VIEW_TOKEN'),
            release_token=os.environ.get('KITCHEN_BOARD_RELEASE_TOKEN'), local=local,language=args.language)
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == '__main__':
    main()
