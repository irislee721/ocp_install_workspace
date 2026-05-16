import sys
from datetime import datetime

def log_info(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[32mINFO\033[0m: {msg}")

def log_error(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[31mERROR\033[0m: {msg}", file=sys.stderr)

def log_success(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] \033[32mSUCCESS\033[0m: {msg}")