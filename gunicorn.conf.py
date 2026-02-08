import os
import multiprocessing

# ワーカー設定
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'sync'
worker_connections = 1000
timeout = 60
keepalive = 5

# バインド設定
bind = f"0.0.0.0:{os.environ.get('PORT', 5000)}"

# ロギング
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# プロセス名
proc_name = 'sekailabo-webhook-proxy'

# プリロード
preload_app = True

# 最大リクエストサイズ（1MB）
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
