import os
import uuid
import shutil
import logging
import tempfile
import time
from typing import List, Optional, Dict
from pathlib import Path
import psutil

class TempFileManager:
    """临时文件管理器，处理临时文件和目录的创建、追踪和删除"""
    
    def __init__(self, base_dir: Optional[str] = None, prefix: str = "videotranslator_"):
        """
        初始化临时文件管理器
        
        Args:
            base_dir: 基本临时目录，未提供则使用系统临时目录
            prefix: 临时文件和目录的前缀
        """
        self.base_dir = base_dir or os.path.join(tempfile.gettempdir(), "videotranslator")
        self.prefix = prefix
        self.temp_files: Dict[str, Dict] = {}  # 会话ID -> 文件列表
        self.current_session = str(uuid.uuid4())
        
        # 确保基础目录存在
        os.makedirs(self.base_dir, exist_ok=True)
        
        # 初次运行时清理旧的临时文件
        self._cleanup_old_files()
        
        logging.debug(f"临时文件管理器初始化，基础目录: {self.base_dir}")
    
    def create_temp_file(self, extension: str = "", session_id: Optional[str] = None) -> str:
        """
        创建临时文件
        
        Args:
            extension: 文件扩展名（带点，如 .txt）
            session_id: 会话ID，用于分组临时文件，未提供则使用当前会话
            
        Returns:
            临时文件的绝对路径
        """
        session = session_id or self.current_session
        
        # 确保会话记录存在
        if session not in self.temp_files:
            self.temp_files[session] = {
                'files': [],
                'dirs': [],
                'created_time': time.time()
            }
        
        # 生成唯一文件名
        filename = f"{self.prefix}{uuid.uuid4().hex}{extension}"
        filepath = os.path.join(self.base_dir, filename)
        
        # 记录文件
        self.temp_files[session]['files'].append({
            'path': filepath,
            'created_time': time.time()
        })
        
        logging.debug(f"创建临时文件: {filepath}")
        return filepath
    
    def create_temp_dir(self, session_id: Optional[str] = None) -> str:
        """
        创建临时目录
        
        Args:
            session_id: 会话ID，用于分组临时目录，未提供则使用当前会话
            
        Returns:
            临时目录的绝对路径
        """
        session = session_id or self.current_session
        
        # 确保会话记录存在
        if session not in self.temp_files:
            self.temp_files[session] = {
                'files': [],
                'dirs': [],
                'created_time': time.time()
            }
        
        # 生成唯一目录名
        dirname = f"{self.prefix}{uuid.uuid4().hex}"
        dirpath = os.path.join(self.base_dir, dirname)
        
        # 创建目录
        os.makedirs(dirpath, exist_ok=True)
        
        # 记录目录
        self.temp_files[session]['dirs'].append({
            'path': dirpath,
            'created_time': time.time()
        })
        
        logging.debug(f"创建临时目录: {dirpath}")
        return dirpath
    
    def register_file(self, filepath: str, session_id: Optional[str] = None) -> None:
        """
        注册外部临时文件到管理器
        
        Args:
            filepath: 文件路径
            session_id: 会话ID，未提供则使用当前会话
        """
        session = session_id or self.current_session
        
        # 确保会话记录存在
        if session not in self.temp_files:
            self.temp_files[session] = {
                'files': [],
                'dirs': [],
                'created_time': time.time()
            }
        
        # 记录文件
        self.temp_files[session]['files'].append({
            'path': filepath,
            'created_time': time.time()
        })
        
        logging.debug(f"注册外部临时文件: {filepath}")
    
    def cleanup_session(self, session_id: Optional[str] = None) -> int:
        """
        清理指定会话的所有临时文件和目录
        
        Args:
            session_id: 要清理的会话ID，未提供则使用当前会话
            
        Returns:
            清理的文件和目录总数
        """
        session = session_id or self.current_session
        
        if session not in self.temp_files:
            logging.warning(f"找不到会话 {session} 的临时文件记录")
            return 0
        
        count = 0
        
        # 先删除文件
        for file_info in self.temp_files[session]['files']:
            filepath = file_info['path']
            if os.path.exists(filepath) and os.path.isfile(filepath):
                try:
                    os.remove(filepath)
                    count += 1
                    logging.debug(f"删除临时文件: {filepath}")
                except Exception as e:
                    logging.error(f"删除临时文件 {filepath} 失败: {str(e)}")
        
        # 再删除目录
        for dir_info in self.temp_files[session]['dirs']:
            dirpath = dir_info['path']
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                try:
                    shutil.rmtree(dirpath)
                    count += 1
                    logging.debug(f"删除临时目录: {dirpath}")
                except Exception as e:
                    logging.error(f"删除临时目录 {dirpath} 失败: {str(e)}")
        
        # 从记录中移除
        del self.temp_files[session]
        
        return count
    
    def cleanup_all(self) -> int:
        """
        清理所有会话的临时文件和目录
        
        Returns:
            清理的会话数
        """
        sessions = list(self.temp_files.keys())
        count = 0
        
        for session in sessions:
            self.cleanup_session(session)
            count += 1
        
        return count
    
    def _cleanup_old_files(self, max_age_days: int = 1) -> int:
        """
        清理旧的临时文件（非当前会话管理的文件）
        
        Args:
            max_age_days: 最大保留天数，默认1天
            
        Returns:
            清理的文件和目录数
        """
        max_age_seconds = max_age_days * 86400  # 天数转换为秒
        current_time = time.time()
        count = 0
        
        try:
            # 清理基础目录中的旧文件
            if os.path.exists(self.base_dir):
                for item in os.listdir(self.base_dir):
                    item_path = os.path.join(self.base_dir, item)
                    
                    # 确保是我们的临时文件/目录
                    if not item.startswith(self.prefix):
                        continue
                    
                    # 检查创建时间
                    try:
                        ctime = os.path.getctime(item_path)
                        if current_time - ctime > max_age_seconds:
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                                count += 1
                            elif os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                                count += 1
                    except Exception as e:
                        logging.warning(f"清理旧临时项目 {item_path} 失败: {str(e)}")
        
        except Exception as e:
            logging.error(f"清理旧临时文件失败: {str(e)}")
        
        return count
    
    def check_space(self, min_free_space_mb: int = 500) -> bool:
        """
        检查临时目录是否有足够的可用空间
        
        Args:
            min_free_space_mb: 最低可用空间要求 (MB)
            
        Returns:
            空间充足返回 True，否则返回 False
        """
        try:
            disk_usage = psutil.disk_usage(self.base_dir)
            free_mb = disk_usage.free / (1024 * 1024)  # 字节转换为 MB
            
            if free_mb < min_free_space_mb:
                logging.warning(f"临时目录空间不足: {free_mb:.2f}MB < {min_free_space_mb}MB")
                return False
                
            return True
        except Exception as e:
            logging.error(f"检查磁盘空间失败: {str(e)}")
            return False  # 如果无法检查，则假设空间不足
    
    def get_session_file_count(self, session_id: Optional[str] = None) -> int:
        """
        获取会话的临时文件和目录数量
        
        Args:
            session_id: 会话 ID，未提供则使用当前会话
            
        Returns:
            临时文件和目录的总数
        """
        session = session_id or self.current_session
        
        if session not in self.temp_files:
            return 0
            
        return len(self.temp_files[session]['files']) + len(self.temp_files[session]['dirs'])
    
    def get_total_size(self, session_id: Optional[str] = None) -> int:
        """
        获取会话的临时文件和目录总大小
        
        Args:
            session_id: 会话 ID，未提供则使用当前会话
            
        Returns:
            总大小 (字节)
        """
        session = session_id or self.current_session
        
        if session not in self.temp_files:
            return 0
            
        total_size = 0
        
        # 计算文件大小
        for file_info in self.temp_files[session]['files']:
            filepath = file_info['path']
            if os.path.exists(filepath) and os.path.isfile(filepath):
                total_size += os.path.getsize(filepath)
        
        # 计算目录大小
        for dir_info in self.temp_files[session]['dirs']:
            dirpath = dir_info['path']
            if os.path.exists(dirpath) and os.path.isdir(dirpath):
                for root, dirs, files in os.walk(dirpath):
                    for file in files:
                        filepath = os.path.join(root, file)
                        if os.path.exists(filepath):
                            total_size += os.path.getsize(filepath)
        
        return total_size
    
    def start_new_session(self) -> str:
        """
        开始新的会话
        
        Returns:
            新会话的 ID
        """
        self.current_session = str(uuid.uuid4())
        self.temp_files[self.current_session] = {
            'files': [],
            'dirs': [],
            'created_time': time.time()
        }
        return self.current_session
