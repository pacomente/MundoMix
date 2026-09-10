"""Conservative Gunicorn configuration for MundoMix + SQLite.

The defaults are intentionally modest because SQLite is a file database and
writes should not be overwhelmed by a large worker pool.
"""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

accesslog = "-"
errorlog = "-"
capture_output = True
preload_app = False

# Keep the process conservative for SQLite. Values can be overridden through
# environment variables when the deployment grows or the database changes.
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))
