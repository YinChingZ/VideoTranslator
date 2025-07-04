#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Management utilities for video processing.
提供内存监控、限制和优化功能。
"""

import os
import gc
import sys
import time
import psutil
import logging
import threading
from typing import Optional, Callable, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class MemoryStats:
    """内存统计数据"""
    total_mb: float
    available_mb: float
    used_mb: float
    percent: float
    process_mb: float

class MemoryMonitor:
    """内存监控器"""
    
    def __init__(self, warning_threshold: float = 80.0, critical_threshold: float = 90.0):
        """
        初始化内存监控器
        
        Args:
            warning_threshold: 警告阈值（百分比）
            critical_threshold: 危险阈值（百分比）
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.process = psutil.Process()
        self.callbacks = {
            'warning': [],
            'critical': [],
            'normal': []
        }
        self._monitoring = False
        self._monitor_thread = None
    
    def get_memory_stats(self) -> MemoryStats:
        """获取当前内存统计"""
        try:
            # 系统内存
            memory = psutil.virtual_memory()
            
            # 进程内存
            process_memory = self.process.memory_info()
            
            return MemoryStats(
                total_mb=memory.total / (1024 * 1024),
                available_mb=memory.available / (1024 * 1024),
                used_mb=memory.used / (1024 * 1024),
                percent=memory.percent,
                process_mb=process_memory.rss / (1024 * 1024)
            )
        except Exception as e:
            logger.error(f"获取内存统计失败: {e}")
            return MemoryStats(0, 0, 0, 0, 0)
    
    def add_callback(self, level: str, callback: Callable[[MemoryStats], None]):
        """添加内存状态回调"""
        if level in self.callbacks:
            self.callbacks[level].append(callback)
    
    def start_monitoring(self, interval: float = 1.0):
        """开始内存监控"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, 
            args=(interval,), 
            daemon=True
        )
        self._monitor_thread.start()
        logger.info("内存监控已启动")
    
    def stop_monitoring(self):
        """停止内存监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2.0)
        logger.info("内存监控已停止")
    
    def _monitor_loop(self, interval: float):
        """监控循环"""
        last_level = 'normal'
        
        while self._monitoring:
            try:
                stats = self.get_memory_stats()
                current_level = self._get_memory_level(stats)
                
                # 只在状态变化时触发回调
                if current_level != last_level:
                    for callback in self.callbacks[current_level]:
                        try:
                            callback(stats)
                        except Exception as e:
                            logger.error(f"内存监控回调失败: {e}")
                    last_level = current_level
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"内存监控循环错误: {e}")
                time.sleep(interval)
    
    def _get_memory_level(self, stats: MemoryStats) -> str:
        """获取内存状态级别"""
        if stats.percent >= self.critical_threshold:
            return 'critical'
        elif stats.percent >= self.warning_threshold:
            return 'warning'
        else:
            return 'normal'
    
    def check_available_memory(self, required_mb: float) -> bool:
        """检查是否有足够的可用内存"""
        stats = self.get_memory_stats()
        return stats.available_mb >= required_mb

class MemoryLimiter:
    """内存限制器"""
    
    def __init__(self, max_memory_mb: float = 1024):
        """
        初始化内存限制器
        
        Args:
            max_memory_mb: 最大内存使用量（MB）
        """
        self.max_memory_mb = max_memory_mb
        self.monitor = MemoryMonitor()
    
    def check_memory_limit(self) -> bool:
        """检查是否超过内存限制"""
        stats = self.monitor.get_memory_stats()
        return stats.process_mb <= self.max_memory_mb
    
    def enforce_memory_limit(self):
        """强制执行内存限制"""
        if not self.check_memory_limit():
            logger.warning("内存使用超限，执行垃圾回收")
            gc.collect()
            
            # 再次检查
            if not self.check_memory_limit():
                stats = self.monitor.get_memory_stats()
                raise MemoryError(
                    f"内存使用超限: {stats.process_mb:.1f}MB > {self.max_memory_mb}MB"
                )

@contextmanager
def memory_managed_operation(max_memory_mb: float = 1024, 
                           cleanup_callback: Optional[Callable] = None):
    """
    内存管理的上下文管理器
    
    Args:
        max_memory_mb: 最大内存限制
        cleanup_callback: 清理回调函数
    """
    limiter = MemoryLimiter(max_memory_mb)
    monitor = MemoryMonitor()
    
    # 记录开始时的内存状态
    start_stats = monitor.get_memory_stats()
    logger.debug(f"操作开始 - 进程内存: {start_stats.process_mb:.1f}MB")
    
    try:
        yield limiter
        
        # 检查内存限制
        limiter.enforce_memory_limit()
        
    except MemoryError as e:
        logger.error(f"内存限制错误: {e}")
        if cleanup_callback:
            cleanup_callback()
        raise
        
    except Exception as e:
        logger.error(f"操作错误: {e}")
        raise
        
    finally:
        # 执行清理
        if cleanup_callback:
            cleanup_callback()
        
        # 强制垃圾回收
        gc.collect()
        
        # 记录结束时的内存状态
        end_stats = monitor.get_memory_stats()
        memory_diff = end_stats.process_mb - start_stats.process_mb
        logger.debug(
            f"操作完成 - 进程内存: {end_stats.process_mb:.1f}MB "
            f"(变化: {memory_diff:+.1f}MB)"
        )

class ChunkedProcessor:
    """分块处理器，用于处理大文件"""
    
    def __init__(self, chunk_size_mb: float = 100, max_memory_mb: float = 512):
        """
        初始化分块处理器
        
        Args:
            chunk_size_mb: 每块大小（MB）
            max_memory_mb: 最大内存使用（MB）
        """
        self.chunk_size_mb = chunk_size_mb
        self.max_memory_mb = max_memory_mb
        self.monitor = MemoryMonitor()
    
    def should_use_chunked_processing(self, file_size_mb: float) -> bool:
        """判断是否应该使用分块处理"""
        stats = self.monitor.get_memory_stats()
        
        # 如果文件大小超过可用内存的50%，使用分块处理
        return file_size_mb > (stats.available_mb * 0.5)
    
    def calculate_chunk_count(self, file_size_mb: float) -> int:
        """计算需要的块数"""
        if not self.should_use_chunked_processing(file_size_mb):
            return 1
        
        return max(1, int(file_size_mb / self.chunk_size_mb) + 1)
    
    def get_chunk_info(self, file_size_mb: float, chunk_index: int) -> Dict[str, Any]:
        """获取指定块的信息"""
        chunk_count = self.calculate_chunk_count(file_size_mb)
        
        if chunk_index >= chunk_count:
            raise ValueError(f"块索引超出范围: {chunk_index} >= {chunk_count}")
        
        chunk_size = self.chunk_size_mb
        start_mb = chunk_index * chunk_size
        end_mb = min(start_mb + chunk_size, file_size_mb)
        
        return {
            'index': chunk_index,
            'total_chunks': chunk_count,
            'start_mb': start_mb,
            'end_mb': end_mb,
            'size_mb': end_mb - start_mb,
            'start_bytes': int(start_mb * 1024 * 1024),
            'end_bytes': int(end_mb * 1024 * 1024)
        }

def optimize_memory_usage():
    """优化内存使用"""
    try:
        # 强制垃圾回收
        collected = gc.collect()
        
        # 获取内存统计
        monitor = MemoryMonitor()
        stats = monitor.get_memory_stats()
        
        logger.debug(
            f"内存优化完成 - 回收对象: {collected}, "
            f"进程内存: {stats.process_mb:.1f}MB, "
            f"系统内存使用: {stats.percent:.1f}%"
        )
        
        return {
            'collected_objects': collected,
            'process_memory_mb': stats.process_mb,
            'system_memory_percent': stats.percent
        }
        
    except Exception as e:
        logger.error(f"内存优化失败: {e}")
        return None

def get_memory_usage_recommendation(file_size_mb: float) -> Dict[str, Any]:
    """获取内存使用建议"""
    monitor = MemoryMonitor()
    stats = monitor.get_memory_stats()
    
    # 估算处理所需内存（文件大小的2-3倍）
    estimated_memory_mb = file_size_mb * 2.5
    
    recommendation = {
        'file_size_mb': file_size_mb,
        'estimated_memory_mb': estimated_memory_mb,
        'available_memory_mb': stats.available_mb,
        'sufficient_memory': estimated_memory_mb <= stats.available_mb,
        'use_chunked_processing': False,
        'recommended_chunk_size_mb': 100,
        'warning_message': None
    }
    
    if not recommendation['sufficient_memory']:
        recommendation['use_chunked_processing'] = True
        recommendation['recommended_chunk_size_mb'] = max(
            50, stats.available_mb * 0.3
        )
        recommendation['warning_message'] = (
            f"文件较大({file_size_mb:.1f}MB)，建议使用分块处理以避免内存不足"
        )
    
    elif estimated_memory_mb > stats.available_mb * 0.7:
        recommendation['warning_message'] = (
            f"内存使用可能较高，建议关闭其他程序以确保处理顺利"
        )
    
    return recommendation
