"""A crashed worker must restart the whole desktop, never inherit old windows."""
import os
import signal


def child_exit(server, worker):
    os.kill(server.pid, signal.SIGTERM)
