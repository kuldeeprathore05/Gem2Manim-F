bind = "0.0.0.0:5000"
workers = 1 
worker_class = "sync"
timeout = 120  
max_requests = 100
max_requests_jitter = 10
preload_app = True
