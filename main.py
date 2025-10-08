from functools import wraps
import inspect
from dataclasses import dataclass
from typing import Callable, Any
import time

@dataclass(frozen=True)
class DomainServiceMonitorMeta:
    """對應 Java annotation 的屬性"""
    source_app: str = ""
    target_product: str = ""
    target_service: str = ""
    target_action: str = ""

def _ensure_histogram(meta) -> None:
    print(f'_ensure_histogram: {meta}')

def _labels_from_response(result):
    return {"is_error": "false", "error_code": "", "error_type": "", "http_status": "200"}

def _labels_from_exception(exc: BaseException) -> dict[str, str]:
    return {
        "is_error": "true",
        "error_code": getattr(exc, "code", ""),
        "error_type": exc.__class__.__name__,
        "http_status": ""
    }

class DomainServiceMonitor:
    def __init__(self, 
            source_app: str = "",
            target_product: str = "",
            target_service: str = "",
            target_action: str = ""
        ):
        self.source_app = source_app
        self.target_product = target_product
        self.target_service = target_service
        self.target_action = target_action
 
    def __call__(self, func: Callable[..., Any]):
        def monitor_metrics(*args, **kargs) -> Callable[..., Any]:
            # if not hasattr(func, "_monitor_meta_"):
            #     # 若開發者忘記加 @domain_service_monitor，仍然可以監控，只是不
            #     # 會有預設的 label（全部為 empty），但仍會產生 metrics。
            #     meta = {
            #         "class": func.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0],
            #         "method": func.__name__,
            #         "source_app": "",
            #         "target_product": "",
            #         "target_service": "",
            #         "target_action": "",
            #     }
            # else:
                # meta = func._monitor_meta_.__dict__ if hasattr(func._monitor_meta_, "__dict__") else func._monitor_meta_
            meta = DomainServiceMonitorMeta(
                source_app=self.source_app,
                target_product=self.target_product,
                target_service=self.target_service,
                target_action=self.target_action,
            ).__dict__

            response_histogram = _ensure_histogram(meta)
            req_labels = {
                **meta,
                "is_error": "false",
                "error_code": "",
                "error_type": "",
                "http_status": "",
            }
            # request_counter.labels(**req_labels).inc()
            start = time.time()

            if inspect.iscoroutinefunction(func):  # async version
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    try:
                        start = time.time()
                        result = await func(*args, **kwargs)
                        resp_labels = {
                            **meta,
                            **_labels_from_response(result),
                        }
                        elapsed = time.time() - start
                        # response_counter.labels(**resp_labels).inc()
                        return result
                    except Exception as exc:
                        resp_labels = {
                            **meta,
                            **_labels_from_exception(exc),
                        }
                        elapsed = time.time() - start
                        raise
                return async_wrapper
            else:
                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    try:
                        result = func(*args, **kwargs)
                        resp_labels = {
                            **meta,
                            **_labels_from_response(result),
                        }
                        elapsed = time.time() - start
                        return result
                    except Exception as exc:
                        resp_labels = {
                            **meta,
                            **_labels_from_exception(exc),
                        }
                        
                        elapsed = time.time() - start
                        raise
                return sync_wrapper
        return monitor_metrics


import time
@DomainServiceMonitor(source_app="demo", target_product="test", target_service="svc", target_action="run")
def test_func(x):
    print(f"test_func called with {x}")
    time.sleep(1)
    return x * 2

if __name__ == "__main__":
    print("Result:", test_func(5))