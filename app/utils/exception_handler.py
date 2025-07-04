#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一异常处理系统
提供用户友好的错误提示和解决建议
"""

import sys
import traceback
import logging
from typing import Dict, Any, Optional, Callable, Type
from enum import Enum
from PyQt5.QtWidgets import QMessageBox, QWidget
from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误分类"""
    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    MEMORY = "memory"
    DEPENDENCY = "dependency"
    API = "api"
    CONFIGURATION = "configuration"
    PROCESSING = "processing"
    USER_INPUT = "user_input"
    SYSTEM = "system"


class UserFriendlyError(Exception):
    """用户友好的异常类"""
    
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.SYSTEM,
                 severity: ErrorSeverity = ErrorSeverity.ERROR,
                 user_message: str = None, suggestions: list = None,
                 technical_details: str = None):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.user_message = user_message or message
        self.suggestions = suggestions or []
        self.technical_details = technical_details


class ExceptionHandler(QObject):
    """统一异常处理器"""
    
    # 信号：发生错误时发出
    error_occurred = pyqtSignal(str, str, str)  # title, message, details
    
    # 错误消息映射
    ERROR_MESSAGES = {
        # 网络相关错误
        'network_timeout': {
            'title': '网络连接超时',
            'message': '网络连接超时，请检查您的网络连接。',
            'suggestions': [
                '检查网络连接是否正常',
                '尝试使用VPN或更换网络',
                '稍后重试',
                '检查防火墙设置'
            ]
        },
        'network_unavailable': {
            'title': '网络不可用',
            'message': '无法连接到互联网，某些功能可能受限。',
            'suggestions': [
                '检查网络连接',
                '重启路由器',
                '联系网络服务提供商'
            ]
        },
        'api_connection_failed': {
            'title': 'API连接失败',
            'message': '无法连接到服务器，请稍后重试。',
            'suggestions': [
                '检查网络连接',
                '稍后重试',
                '检查API服务状态',
                '联系技术支持'
            ]
        },
        
        # API相关错误
        'api_key_invalid': {
            'title': 'API密钥无效',
            'message': 'API密钥无效或已过期，请检查配置。',
            'suggestions': [
                '检查API密钥是否正确',
                '确认API密钥未过期',
                '重新获取API密钥',
                '检查API服务商账户状态'
            ]
        },
        'api_quota_exceeded': {
            'title': 'API配额已用完',
            'message': 'API调用次数已达到限制，请稍后重试或升级服务。',
            'suggestions': [
                '等待配额重置',
                '升级API服务计划',
                '使用其他翻译服务',
                '联系服务提供商'
            ]
        },
        'api_rate_limited': {
            'title': 'API调用频率限制',
            'message': 'API调用过于频繁，请稍后重试。',
            'suggestions': [
                '稍等几分钟后重试',
                '减少并发请求',
                '考虑升级API服务'
            ]
        },
        
        # 文件系统错误
        'file_not_found': {
            'title': '文件未找到',
            'message': '指定的文件不存在或已被移动。',
            'suggestions': [
                '检查文件路径是否正确',
                '确认文件未被删除或移动',
                '重新选择文件',
                '检查文件权限'
            ]
        },
        'file_permission_denied': {
            'title': '文件权限不足',
            'message': '没有权限访问指定文件或目录。',
            'suggestions': [
                '以管理员身份运行程序',
                '检查文件或文件夹权限',
                '选择其他位置保存文件',
                '联系系统管理员'
            ]
        },
        'disk_space_insufficient': {
            'title': '磁盘空间不足',
            'message': '磁盘空间不足，无法完成操作。',
            'suggestions': [
                '清理磁盘空间',
                '删除不需要的文件',
                '选择其他磁盘保存文件',
                '升级存储容量'
            ]
        },
        'file_format_unsupported': {
            'title': '不支持的文件格式',
            'message': '文件格式不受支持，请选择其他格式的文件。',
            'suggestions': [
                '转换文件格式',
                '使用支持的格式',
                '更新软件版本',
                '安装相关解码器'
            ]
        },
        
        # 内存相关错误
        'memory_insufficient': {
            'title': '内存不足',
            'message': '系统内存不足，无法处理该文件。',
            'suggestions': [
                '关闭其他程序释放内存',
                '重启应用程序',
                '处理较小的文件',
                '增加系统内存',
                '尝试分段处理'
            ]
        },
        'memory_allocation_failed': {
            'title': '内存分配失败',
            'message': '无法分配足够的内存来处理请求。',
            'suggestions': [
                '重启应用程序',
                '关闭其他程序',
                '处理较小的文件',
                '检查系统内存使用情况'
            ]
        },
        
        # 依赖相关错误
        'dependency_missing': {
            'title': '缺少依赖组件',
            'message': '系统缺少必要的组件，请安装相关依赖。',
            'suggestions': [
                '安装缺少的依赖',
                '重新安装应用程序',
                '检查安装文档',
                '联系技术支持'
            ]
        },
        'ffmpeg_not_found': {
            'title': 'FFmpeg未找到',
            'message': '系统中未找到FFmpeg，这是处理音视频文件的必要组件。',
            'suggestions': [
                '安装FFmpeg到系统PATH',
                '下载FFmpeg便携版',
                '重新安装应用程序',
                '查看安装指南'
            ]
        },
        
        # 处理相关错误
        'processing_failed': {
            'title': '处理失败',
            'message': '文件处理过程中发生错误。',
            'suggestions': [
                '重试操作',
                '检查文件是否完整',
                '尝试其他设置',
                '查看详细错误信息'
            ]
        },
        'processing_interrupted': {
            'title': '处理中断',
            'message': '处理过程被中断，可以选择继续或重新开始。',
            'suggestions': [
                '点击继续按钮恢复处理',
                '重新开始处理',
                '检查文件完整性',
                '确保有足够的磁盘空间'
            ]
        },
        
        # 配置相关错误
        'config_invalid': {
            'title': '配置文件无效',
            'message': '配置文件格式错误或损坏。',
            'suggestions': [
                '重置为默认配置',
                '手动修复配置文件',
                '重新配置设置',
                '恢复备份配置'
            ]
        },
        
        # 用户输入错误
        'invalid_input': {
            'title': '输入无效',
            'message': '输入的信息格式不正确。',
            'suggestions': [
                '检查输入格式',
                '参考示例',
                '重新输入',
                '查看帮助文档'
            ]
        }
    }
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.parent_widget = parent
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志记录"""
        # 设置全局异常处理器
        sys.excepthook = self._handle_uncaught_exception
    
    def _handle_uncaught_exception(self, exc_type, exc_value, exc_traceback):
        """处理未捕获的异常"""
        if issubclass(exc_type, KeyboardInterrupt):
            # 允许Ctrl+C中断
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # 记录异常
        logger.critical("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
        
        # 显示用户友好的错误对话框
        error_msg = f"程序遇到未预期的错误: {exc_value}"
        details = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        
        self.show_error_dialog(
            title="程序错误",
            message=error_msg,
            details=details,
            severity=ErrorSeverity.CRITICAL
        )
    
    def handle_exception(self, exception: Exception, context: str = "") -> bool:
        """
        处理异常并显示用户友好的错误信息
        
        Args:
            exception: 要处理的异常
            context: 异常发生的上下文信息
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            if isinstance(exception, UserFriendlyError):
                return self._handle_user_friendly_error(exception, context)
            else:
                return self._handle_generic_error(exception, context)
        except Exception as e:
            logger.error(f"异常处理器本身发生错误: {e}")
            return False
    
    def _handle_user_friendly_error(self, error: UserFriendlyError, context: str) -> bool:
        """处理用户友好的异常"""
        logger.error(f"用户友好异常 [{context}]: {error.user_message}")
        
        self.show_error_dialog(
            title=f"{error.category.value.title()}错误",
            message=error.user_message,
            suggestions=error.suggestions,
            details=error.technical_details,
            severity=error.severity
        )
        return True
    
    def _handle_generic_error(self, exception: Exception, context: str) -> bool:
        """处理通用异常"""
        error_type = type(exception).__name__
        error_msg = str(exception)
        
        # 尝试匹配已知的错误模式
        error_info = self._match_error_pattern(error_type, error_msg)
        
        if error_info:
            title = error_info['title']
            message = error_info['message']
            suggestions = error_info.get('suggestions', [])
        else:
            title = "处理错误"
            message = f"操作失败: {error_msg}"
            suggestions = [
                '重试操作',
                '检查输入参数',
                '查看详细错误信息',
                '联系技术支持'
            ]
        
        # 记录错误
        logger.error(f"异常处理 [{context}]: {error_type}: {error_msg}")
        
        # 显示错误对话框
        self.show_error_dialog(
            title=title,
            message=message,
            suggestions=suggestions,
            details=f"{error_type}: {error_msg}\n\n发生位置: {context}",
            severity=ErrorSeverity.ERROR
        )
        return True
    
    def _match_error_pattern(self, error_type: str, error_msg: str) -> Optional[Dict]:
        """匹配错误模式"""
        error_msg_lower = error_msg.lower()
        
        # 网络错误
        if any(keyword in error_msg_lower for keyword in ['timeout', '超时', 'connection', 'network']):
            if 'timeout' in error_msg_lower or '超时' in error_msg_lower:
                return self.ERROR_MESSAGES['network_timeout']
            else:
                return self.ERROR_MESSAGES['network_unavailable']
        
        # API错误
        if any(keyword in error_msg_lower for keyword in ['api', 'unauthorized', '401', '403']):
            if any(keyword in error_msg_lower for keyword in ['key', 'token', 'unauthorized', '401']):
                return self.ERROR_MESSAGES['api_key_invalid']
            elif any(keyword in error_msg_lower for keyword in ['quota', 'limit', 'exceeded']):
                return self.ERROR_MESSAGES['api_quota_exceeded']
            elif any(keyword in error_msg_lower for keyword in ['rate', 'too many', '429']):
                return self.ERROR_MESSAGES['api_rate_limited']
            else:
                return self.ERROR_MESSAGES['api_connection_failed']
        
        # 文件错误
        if any(keyword in error_msg_lower for keyword in ['file', 'directory', 'path']):
            if any(keyword in error_msg_lower for keyword in ['not found', 'does not exist', '找不到', '不存在']):
                return self.ERROR_MESSAGES['file_not_found']
            elif any(keyword in error_msg_lower for keyword in ['permission', 'access', 'denied', '权限', '拒绝']):
                return self.ERROR_MESSAGES['file_permission_denied']
            elif any(keyword in error_msg_lower for keyword in ['space', 'disk full', '空间', '磁盘满']):
                return self.ERROR_MESSAGES['disk_space_insufficient']
            elif any(keyword in error_msg_lower for keyword in ['format', 'codec', 'unsupported', '格式', '不支持']):
                return self.ERROR_MESSAGES['file_format_unsupported']
        
        # 内存错误
        if any(keyword in error_msg_lower for keyword in ['memory', 'ram', '内存', 'out of memory']):
            return self.ERROR_MESSAGES['memory_insufficient']
        
        # FFmpeg错误
        if any(keyword in error_msg_lower for keyword in ['ffmpeg', 'ffprobe']):
            return self.ERROR_MESSAGES['ffmpeg_not_found']
        
        # 依赖错误
        if any(keyword in error_msg_lower for keyword in ['module', 'import', 'package', '模块']):
            return self.ERROR_MESSAGES['dependency_missing']
        
        return None
    
    def show_error_dialog(self, title: str, message: str, 
                         suggestions: list = None, details: str = None,
                         severity: ErrorSeverity = ErrorSeverity.ERROR):
        """显示错误对话框"""
        if not self.parent_widget:
            # 如果没有父窗口，只记录日志
            logger.error(f"{title}: {message}")
            return
        
        # 创建消息框
        msg_box = QMessageBox(self.parent_widget)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        
        # 设置图标
        if severity == ErrorSeverity.CRITICAL:
            msg_box.setIcon(QMessageBox.Critical)
        elif severity == ErrorSeverity.ERROR:
            msg_box.setIcon(QMessageBox.Critical)
        elif severity == ErrorSeverity.WARNING:
            msg_box.setIcon(QMessageBox.Warning)
        else:
            msg_box.setIcon(QMessageBox.Information)
        
        # 添加建议
        if suggestions:
            suggestion_text = "\n解决建议:\n" + "\n".join(f"• {s}" for s in suggestions)
            msg_box.setInformativeText(suggestion_text)
        
        # 添加详细信息
        if details:
            msg_box.setDetailedText(details)
        
        # 添加按钮
        msg_box.setStandardButtons(QMessageBox.Ok)
        if severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
            retry_button = msg_box.addButton("重试", QMessageBox.ActionRole)
            msg_box.setDefaultButton(retry_button)
        
        # 发出信号
        self.error_occurred.emit(title, message, details or "")
        
        # 显示对话框
        msg_box.exec_()
    
    def create_user_friendly_error(self, category: ErrorCategory, 
                                 technical_message: str,
                                 severity: ErrorSeverity = ErrorSeverity.ERROR,
                                 suggestions: list = None) -> UserFriendlyError:
        """创建用户友好的异常"""
        # 根据类别获取用户消息
        error_key = f"{category.value}_error"
        error_info = self.ERROR_MESSAGES.get(error_key, {
            'title': '操作失败',
            'message': technical_message,
            'suggestions': suggestions or ['重试操作', '查看详细信息', '联系技术支持']
        })
        
        return UserFriendlyError(
            message=technical_message,
            category=category,
            severity=severity,
            user_message=error_info['message'],
            suggestions=error_info.get('suggestions', []),
            technical_details=technical_message
        )


# 全局异常处理器实例
_global_exception_handler: Optional[ExceptionHandler] = None


def get_global_exception_handler() -> ExceptionHandler:
    """获取全局异常处理器"""
    global _global_exception_handler
    if _global_exception_handler is None:
        _global_exception_handler = ExceptionHandler()
    return _global_exception_handler


def set_global_exception_handler(handler: ExceptionHandler):
    """设置全局异常处理器"""
    global _global_exception_handler
    _global_exception_handler = handler


def handle_exception(exception: Exception, context: str = "") -> bool:
    """便捷函数：处理异常"""
    handler = get_global_exception_handler()
    return handler.handle_exception(exception, context)


# 装饰器：自动异常处理
def exception_handler(context: str = "", reraise: bool = False):
    """异常处理装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                handle_exception(e, context or func.__name__)
                if reraise:
                    raise
                return None
        return wrapper
    return decorator
