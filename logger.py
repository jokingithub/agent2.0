import logging
import os
from logging.handlers import RotatingFileHandler
from config import Config


# 从环境变量获取配置，设置默认值
LOG_LEVEL = Config.LOG_LEVEL
LOG_TO_CONSOLE = Config.LOG_TO_CONSOLE
LOG_FILE_PATH = Config.LOG_FILE_PATH
LOG_MAX_BYTES = Config.LOG_MAX_BYTES
LOG_BACKUP_COUNT = Config.LOG_BACKUP_COUNT

def setup_logger(name: str):
    # 1. 创建日志目录
    log_dir = os.path.dirname(LOG_FILE_PATH)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # 2. 获取或创建 logger 实例
    logger = logging.getLogger(name)
    
    # 设置全局日志级别
    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(numeric_level)

    # 防止重复添加 Handler (在多次调用 setup_logger 时很重要)
    if not logger.handlers:
        
        # --- 格式定义 ---
        # 控制台格式：简洁点
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        # 文件格式：详细点，包含文件名和行号，方便排错
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        )

        # --- 3. 配置控制台输出 (StreamHandler) ---
        if LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

        # --- 4. 配置文件输出 (RotatingFileHandler) ---
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE_PATH,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"无法初始化日志文件处理器: {e}")

    return logger

# 创建一个默认的全局实例
logger = setup_logger("AppRoot")