#!/bin/sh
set -eu
umask 077
Xvfb :99 -screen 0 1440x1000x24 -nolisten tcp -ac &
xvfb_pid=$!
trap 'kill "$xvfb_pid" 2>/dev/null || true' EXIT
attempt=0
while [ ! -S /tmp/.X11-unix/X99 ]; do
    kill -0 "$xvfb_pid"
    attempt=$((attempt + 1))
    [ "$attempt" -lt 100 ] || exit 1
    sleep 0.1
done
# x11vnc waits for Xvfb rather than racing browser startup.
x11vnc -display :99 -localhost -rfbport 5900 -forever -shared -nopw -quiet -loop &
exec gunicorn --config /app/gunicorn.conf.py --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 180 \
    --access-logfile /dev/null 'indeed_worker.service:create_app()'
