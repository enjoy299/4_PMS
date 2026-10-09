"""
日志工具 —— 统一的日志记录格式，同时输出到终端和文件。

通俗理解：
  程序运行时需要记录“发生了什么”，这就是日志。
  这个工具让日志同时出现在两个地方：
    1. 终端屏幕 —— 实时看到运行情况
    2. 日志文件 —— 运行结束后可以回看
"""
import logging, sys    # logging 是 Python 内置的日志库
from datetime import datetime
from core.config import LOGS_DIR

def get_logger(name: str = "ai-test") -> logging.Logger:
    """
    获取一个日志记录器。

    参数：
        name: 日志记录器的名称（会显示在日志中，方便区分来源）

    返回：
        配置好的日志记录器，可以用 logger.info()、logger.error() 等方法记录日志
    """
    logger = logging.getLogger(name)
    # 如果已经配置过了，直接返回（避免重复添加处理器）
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)  # 设置最低记录级别为 DEBUG（记录所有级别的日志）

    # 配置终端输出（只显示 INFO 级别及以上的日志，避免刷屏）
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s", datefmt="%H:%M:%S"))

    # 配置文件输出（记录所有级别的日志，包括 DEBUG）
    log_file = LOGS_DIR / f"test_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s"))

    # 把两个输出处理器都添加到日志记录器
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
