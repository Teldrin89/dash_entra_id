"""Gunicorn settings. Override any of them via environment variables."""
import multiprocessing
import os

bind = os.getenv("BIND", "0.0.0.0:8050")
workers = int(os.getenv("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 4)))
threads = int(os.getenv("GUNICORN_THREADS", 2))
worker_class = "gthread"
timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info")

# Trust X-Forwarded-* only from these peers (gunicorn's own check; ProxyFix in
# app.py then applies them when PROXY_HOPS > 0). Use the proxy IP in production.
forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")
