import logging

json_logger = logging.getLogger("json_logger")

def test():
    json_logger.info("這是 JSON log", extra={
        "context": {"user": "Season", "action": "login"}
    })