import logging
import json
import sys


# === 自訂 JSON Formatter ===
class CustomJsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "message": record.getMessage(),
            "level": record.levelname,
            "logger": record.name,
            "caller": f"{record.filename}:{record.lineno}",
            "funcName": record.funcName,
            "context": getattr(record, 'context', None),
        }
        return json.dumps(log_record)


# === Logging 設定 ===

# 創建 formatters
plain_formatter = logging.Formatter(
    fmt="[%(asctime)s] [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

json_formatter = CustomJsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
)

# 創建 handlers
console_plain_handler = logging.StreamHandler(sys.stdout)
console_plain_handler.setFormatter(plain_formatter)

console_json_handler = logging.StreamHandler(sys.stdout)
console_json_handler.setFormatter(json_formatter)

# 設定 root logger (用於 logging.info() 等)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_plain_handler)

# 設定 json_logger
json_logger = logging.getLogger("json_logger")
json_logger.setLevel(logging.INFO)
json_logger.addHandler(console_json_handler)
json_logger.propagate = False

# === 初始化 ===

