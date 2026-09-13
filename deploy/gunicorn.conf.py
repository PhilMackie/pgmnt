# Gunicorn config for Pgmnt (Pi)
bind = "0.0.0.0:5004"
workers = 2
worker_class = "sync"
timeout = 30

accesslog = "/opt/pgmnt/logs/access.log"
errorlog  = "/opt/pgmnt/logs/error.log"
loglevel  = "info"

max_requests = 1000
max_requests_jitter = 100
