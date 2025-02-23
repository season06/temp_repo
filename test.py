import logging
import uuid
import contextvars
import time

# 定義上下文變量
request_id_var = contextvars.ContextVar("request_id", default="N/A")

# 自定義 Filter
class ContextFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

# 配置 logging
logger = logging.getLogger("app")
logger.setLevel(logging.DEBUG)

handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s | %(request_id)s | %(levelname)s | %(message)s")
handler.setFormatter(formatter)

context_filter = ContextFilter()
handler.addFilter(context_filter)

logger.addHandler(handler)

# 定義模擬的函數
def function_a():
    logger.info("Entering Function A")
    # 執行一些邏輯
    function_b()
    logger.info("Exiting Function A")

def function_b():
    logger.info("Entering Function B")
    # 執行一些邏輯
    function_c()
    logger.info("Exiting Function B")

def function_c():
    logger.info("Entering Function C")
    # 執行一些邏輯
    logger.info("Exiting Function C")

# 處理請求
def process_request():
    request_id = str(uuid.uuid4())  # 生成唯一的 request_id
    token = request_id_var.set(request_id)  # 設置 request_id 到上下文變量
    try:
        logger.info("Start processing request")
        function_a()
        logger.info("Finished processing request")
    finally:
        pass
        # request_id_var.reset(token)  # 清除上下文變量

# 測試
if __name__ == "__main__":
    process_request()
    time.sleep(3)