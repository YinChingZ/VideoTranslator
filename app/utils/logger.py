#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enhanced logging system for VideoTranslator
优化的日志系统，支持敏感信息过滤和性能监控
"""

import logging
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Dict, Optional

from app.utils.paths import ensure_private_directory, get_state_dir

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 敏感信息模式，用于过滤API密钥等
SENSITIVE_PATTERNS = [
    r'["\']?(api[_-]?key|token|password|secret|credential)["\']?\s*[:=]\s*["\']?[A-Za-z0-9\-._~+/=]+',
    # Google Translation and some compatible APIs use a ``key`` query
    # parameter. Requests exceptions may include the fully prepared URL.
    r'(?<=[?&])key=[^&\s]+',
    r'Bearer\s+[A-Za-z0-9\-._~+/]+=*',
    r'sk-[A-Za-z0-9]{32,}',  # OpenAI API keys
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',  # UUID tokens
]

class SensitiveInfoFilter(logging.Filter):
    """过滤日志中的敏感信息的高级过滤器"""
    
    def __init__(self, patterns: list = None, replacement: str = "***REDACTED***"):
        super().__init__()
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in (patterns or SENSITIVE_PATTERNS)]
        self.replacement = replacement
        
    def filter(self, record):
        """过滤记录中的敏感信息"""
        if isinstance(record.msg, str):
            record.msg = self._redact_sensitive_info(record.msg)
        
        # 处理args中可能的敏感信息
        if isinstance(record.args, dict):
            record.args = self._redact_dict(record.args)
        elif record.args:
            args_list = []
            for arg in record.args:
                if isinstance(arg, str):
                    args_list.append(self._redact_sensitive_info(arg))
                elif isinstance(arg, dict):
                    args_list.append(self._redact_dict(arg))
                else:
                    args_list.append(arg)
            record.args = tuple(args_list)

        # Formatter renders tracebacks separately from ``record.msg``. Redact
        # prepared request URLs there as well (notably Google's ``?key=...``).
        if record.exc_info:
            exception_text = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = self._redact_sensitive_info(exception_text).rstrip()
        elif record.exc_text:
            record.exc_text = self._redact_sensitive_info(record.exc_text)
        if record.stack_info:
            record.stack_info = self._redact_sensitive_info(record.stack_info)
        
        return True
    
    def _redact_sensitive_info(self, text: str) -> str:
        """移除文本中的敏感信息"""
        for pattern in self.patterns:
            text = pattern.sub(self.replacement, text)
        return text
    
    def _redact_dict(self, data: dict) -> dict:
        """移除字典中的敏感信息"""
        redacted = {}
        for key, value in data.items():
            key_text = str(key)
            if any(
                keyword in key_text.lower()
                for keyword in ['key', 'token', 'password', 'secret']
            ):
                redacted[key] = self.replacement
            elif isinstance(value, str):
                redacted[key] = self._redact_sensitive_info(value)
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            else:
                redacted[key] = value
        return redacted


class PerformanceLogAdapter(logging.LoggerAdapter):
    """用于跟踪性能的日志适配器"""
    
    def __init__(self, logger, extra=None):
        super().__init__(logger, extra or {})
        self.timers: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def start_timer(self, name: str) -> None:
        """开始计时器"""
        with self._lock:
            self.timers[name] = time.time()
    
    def stop_timer(self, name: str, level: int = logging.DEBUG) -> float:
        """停止计时器并记录经过时间，返回耗时"""
        with self._lock:
            if name in self.timers:
                elapsed = time.time() - self.timers[name]
                self.log(level, f"性能计时 '{name}' 完成: {elapsed:.3f}秒")
                del self.timers[name]
                return elapsed
            else:
                self.warning(f"尝试停止不存在的计时器: {name}")
                return 0.0
    
    def time_function(self, func_name: str):
        """装饰器：自动计时函数执行时间"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                self.start_timer(func_name)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.stop_timer(func_name)
            return wrapper
        return decorator


class LogViewerHandler(logging.Handler):
    """将日志转发到GUI日志查看器的处理器"""
    
    def __init__(self, callback: Callable[[str, int], None], level: int = logging.INFO):
        super().__init__(level)
        self.callback = callback
        self.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    
    def emit(self, record):
        try:
            msg = self.format(record)
            self.callback(msg, record.levelno)
        except Exception:
            self.handleError(record)


def get_log_path() -> Path:
    """确定日志文件存储位置"""
    log_dir = ensure_private_directory(get_state_dir() / "logs")
    
    # 使用日期作为日志文件名
    date_str = datetime.now().strftime('%Y-%m-%d')
    return log_dir / f"videotranslator_{date_str}.log"


def setup_logger(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    设置和配置日志系统
    
    Args:
        level: 日志级别
        log_file: 日志文件路径，如果为None则使用默认路径
        
    Returns:
        配置好的Logger实例
    """
    # 获取根日志记录器
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)

    # Filtering must be active before any fallback warning is emitted.  A
    # logging failure should never become an application-startup failure: the
    # health checker can explain an unwritable state directory only after the
    # logger has been configured.
    sensitive_filter = SensitiveInfoFilter()
    console_handler.addFilter(sensitive_filter)
    
    # 创建文件处理器
    try:
        if log_file is None:
            log_file = get_log_path()
        else:
            log_path = Path(log_file).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_file = log_path

        file_handler = RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
        )
    except (OSError, PermissionError) as exc:
        # Console logging is sufficient to keep the GUI usable.  Do not retry
        # in the source tree or another surprising location.
        logger.warning("无法启用文件日志，仅使用控制台: %s", exc)
    else:
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        file_handler.addFilter(sensitive_filter)
        logger.addHandler(file_handler)
        logger.info("日志系统初始化完成，日志文件: %s", log_file)
    return logger


def add_log_viewer(callback: Callable[[str, int], None], level: int = logging.INFO) -> LogViewerHandler:
    """
    添加GUI日志查看器
    
    Args:
        callback: 接收日志消息的回调函数
        level: 日志级别
        
    Returns:
        创建的处理器实例
    """
    logger = logging.getLogger()
    viewer_handler = LogViewerHandler(callback, level)
    logger.addHandler(viewer_handler)
    return viewer_handler


def get_performance_logger(name: str) -> PerformanceLogAdapter:
    """获取性能日志适配器"""
    base_logger = logging.getLogger(name)
    return PerformanceLogAdapter(base_logger)


def cleanup_old_logs(days: int = 7) -> None:
    """
    清理旧的日志文件
    
    Args:
        days: 保留多少天的日志文件
    """
    log_dir = get_state_dir() / "logs"
    if not log_dir.exists():
        return
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for log_file in log_dir.glob("videotranslator_*.log*"):
        try:
            # 从文件名中提取日期
            name_parts = log_file.stem.split('_')
            if len(name_parts) >= 2:
                date_str = name_parts[1]
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                
                if file_date < cutoff_date:
                    log_file.unlink()
                    logging.info(f"已删除旧日志文件: {log_file.name}")
                    
        except (ValueError, IndexError) as e:
            logging.warning(f"解析日志文件日期失败: {log_file.name} - {e}")
        except Exception as e:
            logging.error(f"删除日志文件失败: {log_file.name} - {e}")


def generate_error_report() -> str:
    """生成错误报告，包含系统信息和最近的日志"""
    import platform
    import traceback
    
    report = [
        "=" * 60,
        "VideoTranslator 错误报告",
        "=" * 60,
        f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"系统: {platform.platform()}",
        f"Python版本: {platform.python_version()}",
        f"处理器: {platform.processor()}",
        "",
        "最近日志:",
        "-" * 40
    ]
    
    # 获取最近的日志
    log_path = get_log_path()
    if log_path.exists():
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                # 获取最后50行
                lines = f.readlines()[-50:]
                report.extend(lines)
        except Exception as e:
            report.append(f"无法读取日志文件: {e}")
            report.append(traceback.format_exc())
    else:
        report.append("找不到日志文件")
    
    return "\n".join(report)
