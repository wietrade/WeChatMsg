import logging
from functools import wraps

logger = logging.getLogger("test")
logger.setLevel(level=logging.WARNING)  # 只显示警告以上，减少干扰
formatter = logging.Formatter(
    "%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s"
)
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.WARNING)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
logger.addHandler(stream_handler)


def log(func):
    @wraps(func)
    def log_(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.error(
                f"\n{func.__qualname__} is error,params:{(args, kwargs)},here are details:\n{traceback.format_exc()}"
            )

    return log_
