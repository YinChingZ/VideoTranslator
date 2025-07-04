#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
错误恢复和重试机制
用于处理各种失败场景的自动恢复
"""

import time
import logging
import asyncio
from typing import Callable, Optional, Any, Dict, List
from enum import Enum
from functools import wraps
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略枚举"""
    IMMEDIATE = "immediate"           # 立即重试
    LINEAR_BACKOFF = "linear"        # 线性退避
    EXPONENTIAL_BACKOFF = "exponential"  # 指数退避
    CUSTOM = "custom"                # 自定义策略


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3           # 最大重试次数
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    base_delay: float = 1.0         # 基础延迟时间（秒）
    max_delay: float = 60.0         # 最大延迟时间（秒）
    backoff_factor: float = 2.0     # 退避因子
    retry_on_exceptions: tuple = (Exception,)  # 需要重试的异常类型
    should_retry: Optional[Callable[[Exception], bool]] = None  # 自定义重试判断函数


class RetryableError(Exception):
    """可重试的错误"""
    def __init__(self, message: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class NonRetryableError(Exception):
    """不可重试的错误"""
    pass


class RetryManager:
    """重试管理器"""
    
    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig()
        self.retry_history: Dict[str, List[Dict]] = {}
    
    def calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        if self.config.strategy == RetryStrategy.IMMEDIATE:
            return 0
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt
        elif self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (self.config.backoff_factor ** attempt)
        else:
            delay = self.config.base_delay
        
        return min(delay, self.config.max_delay)
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试"""
        # 检查重试次数
        if attempt >= self.config.max_attempts:
            return False
        
        # 检查异常类型
        if isinstance(exception, NonRetryableError):
            return False
        
        if not isinstance(exception, self.config.retry_on_exceptions):
            return False
        
        # 自定义重试判断
        if self.config.should_retry:
            return self.config.should_retry(exception)
        
        return True
    
    def record_attempt(self, operation_id: str, attempt: int, exception: Exception = None, success: bool = False):
        """记录重试尝试"""
        if operation_id not in self.retry_history:
            self.retry_history[operation_id] = []
        
        record = {
            'attempt': attempt,
            'timestamp': time.time(),
            'success': success,
            'exception': str(exception) if exception else None,
            'exception_type': type(exception).__name__ if exception else None
        }
        
        self.retry_history[operation_id].append(record)
    
    def get_retry_stats(self, operation_id: str) -> Dict:
        """获取重试统计信息"""
        if operation_id not in self.retry_history:
            return {}
        
        history = self.retry_history[operation_id]
        total_attempts = len(history)
        successful_attempts = len([h for h in history if h['success']])
        failed_attempts = total_attempts - successful_attempts
        
        return {
            'total_attempts': total_attempts,
            'successful_attempts': successful_attempts,
            'failed_attempts': failed_attempts,
            'success_rate': successful_attempts / total_attempts if total_attempts > 0 else 0,
            'last_attempt': history[-1] if history else None
        }


def retry_with_config(config: RetryConfig = None, operation_id: str = None):
    """重试装饰器（配置版本）"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_manager = RetryManager(config)
            op_id = operation_id or f"{func.__module__}.{func.__name__}"
            
            for attempt in range(config.max_attempts if config else 3):
                try:
                    result = func(*args, **kwargs)
                    retry_manager.record_attempt(op_id, attempt + 1, success=True)
                    
                    if attempt > 0:
                        logger.info(f"操作 {op_id} 在第 {attempt + 1} 次尝试后成功")
                    
                    return result
                    
                except Exception as e:
                    retry_manager.record_attempt(op_id, attempt + 1, exception=e)
                    
                    if not retry_manager.should_retry(e, attempt + 1):
                        logger.error(f"操作 {op_id} 最终失败，不再重试: {e}")
                        raise
                    
                    if attempt < (config.max_attempts if config else 3) - 1:
                        delay = retry_manager.calculate_delay(attempt + 1)
                        logger.warning(f"操作 {op_id} 第 {attempt + 1} 次尝试失败，{delay:.1f}秒后重试: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"操作 {op_id} 在 {attempt + 1} 次尝试后最终失败: {e}")
                        raise
            
            # 理论上不应该到达这里
            raise Exception(f"操作 {op_id} 超出最大重试次数")
        
        return wrapper
    return decorator


def retry(max_attempts: int = 3, delay: float = 1.0, 
         backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """简单重试装饰器"""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=delay,
        backoff_factor=backoff,
        retry_on_exceptions=exceptions
    )
    return retry_with_config(config)


class RecoveryManager:
    """恢复管理器"""
    
    def __init__(self):
        self.recovery_strategies: Dict[str, Callable] = {}
        self.recovery_history: List[Dict] = []
    
    def register_recovery_strategy(self, error_type: str, strategy: Callable):
        """注册恢复策略"""
        self.recovery_strategies[error_type] = strategy
        logger.info(f"已注册恢复策略: {error_type}")
    
    def attempt_recovery(self, error: Exception, context: Dict = None) -> bool:
        """尝试错误恢复"""
        error_type = type(error).__name__
        context = context or {}
        
        logger.info(f"尝试恢复错误: {error_type}")
        
        # 查找匹配的恢复策略
        strategy = None
        for registered_type, registered_strategy in self.recovery_strategies.items():
            if registered_type == error_type or registered_type == 'default':
                strategy = registered_strategy
                break
        
        if not strategy:
            logger.warning(f"未找到 {error_type} 的恢复策略")
            return False
        
        try:
            recovery_start = time.time()
            result = strategy(error, context)
            recovery_time = time.time() - recovery_start
            
            # 记录恢复尝试
            recovery_record = {
                'timestamp': time.time(),
                'error_type': error_type,
                'error_message': str(error),
                'context': context,
                'success': result,
                'recovery_time': recovery_time
            }
            self.recovery_history.append(recovery_record)
            
            if result:
                logger.info(f"成功恢复错误 {error_type}，用时 {recovery_time:.2f}秒")
            else:
                logger.warning(f"恢复错误 {error_type} 失败")
            
            return result
            
        except Exception as recovery_error:
            logger.error(f"恢复过程中发生错误: {recovery_error}")
            
            # 记录恢复失败
            recovery_record = {
                'timestamp': time.time(),
                'error_type': error_type,
                'error_message': str(error),
                'context': context,
                'success': False,
                'recovery_error': str(recovery_error),
                'recovery_time': time.time() - recovery_start
            }
            self.recovery_history.append(recovery_record)
            
            return False
    
    def get_recovery_stats(self) -> Dict:
        """获取恢复统计信息"""
        if not self.recovery_history:
            return {'total_attempts': 0, 'success_rate': 0}
        
        total_attempts = len(self.recovery_history)
        successful_recoveries = len([r for r in self.recovery_history if r['success']])
        
        return {
            'total_attempts': total_attempts,
            'successful_recoveries': successful_recoveries,
            'success_rate': successful_recoveries / total_attempts,
            'recent_attempts': self.recovery_history[-10:]  # 最近10次尝试
        }


# 全局恢复管理器实例
_global_recovery_manager = RecoveryManager()


def get_recovery_manager() -> RecoveryManager:
    """获取全局恢复管理器"""
    return _global_recovery_manager


def register_recovery_strategy(error_type: str):
    """注册恢复策略装饰器"""
    def decorator(func):
        _global_recovery_manager.register_recovery_strategy(error_type, func)
        return func
    return decorator


# 预定义的恢复策略
@register_recovery_strategy('FileNotFoundError')
def recover_file_not_found(error: FileNotFoundError, context: Dict) -> bool:
    """文件不存在错误的恢复策略"""
    file_path = context.get('file_path')
    if not file_path:
        return False
    
    # 尝试在常见位置查找文件
    import os
    from pathlib import Path
    
    search_paths = [
        Path(file_path).parent,
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.cwd()
    ]
    
    filename = Path(file_path).name
    for search_path in search_paths:
        candidate = search_path / filename
        if candidate.exists():
            logger.info(f"在 {candidate} 找到丢失的文件")
            context['recovered_file_path'] = str(candidate)
            return True
    
    return False


@register_recovery_strategy('MemoryError')
def recover_memory_error(error: MemoryError, context: Dict) -> bool:
    """内存错误的恢复策略"""
    import gc
    
    # 强制垃圾回收
    gc.collect()
    
    # 如果使用CUDA，清理GPU内存
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("已清理GPU内存缓存")
    except ImportError:
        pass
    
    # 建议用户关闭其他程序
    logger.info("已尝试释放内存，建议关闭其他程序后重试")
    return True


@register_recovery_strategy('ConnectionError')
def recover_connection_error(error: Exception, context: Dict) -> bool:
    """网络连接错误的恢复策略"""
    import socket
    
    # 测试网络连接
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        logger.info("网络连接正常，错误可能是临时的")
        return True
    except:
        logger.warning("网络连接异常，请检查网络设置")
        return False


@register_recovery_strategy('default')
def default_recovery_strategy(error: Exception, context: Dict) -> bool:
    """默认恢复策略"""
    # 记录错误信息
    logger.info(f"使用默认恢复策略处理错误: {type(error).__name__}")
    
    # 基本的清理操作
    import gc
    gc.collect()
    
    # 等待一小段时间
    time.sleep(0.5)
    
    return False  # 默认策略不执行实际恢复


def with_recovery(recovery_context: Dict = None):
    """带恢复功能的装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            context = recovery_context or {}
            context.update({
                'function': func.__name__,
                'args': args,
                'kwargs': kwargs
            })
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 尝试恢复
                recovery_manager = get_recovery_manager()
                if recovery_manager.attempt_recovery(e, context):
                    # 恢复成功，重试操作
                    logger.info(f"恢复成功，重试 {func.__name__}")
                    return func(*args, **kwargs)
                else:
                    # 恢复失败，重新抛出原异常
                    raise
        
        return wrapper
    return decorator
