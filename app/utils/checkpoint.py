#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Checkpoint Manager for video processing recovery.
提供处理过程中的断点续传和错误恢复功能。
"""

import os
import json
import time
import logging
import hashlib
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

def serialize_for_json(obj):
    """将对象序列化为JSON兼容格式"""
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(item) for item in obj]
    else:
        return obj

@dataclass
class ProcessingCheckpoint:
    """处理检查点数据结构"""
    video_path: str
    video_hash: str
    source_language: str
    target_language: str
    whisper_model: str
    translation_provider: str
    timestamp: float
    completed_stages: List[str]
    stage_data: Dict[str, Any]
    version: str = "1.0.0"

class CheckpointManager:
    """断点续传管理器"""
    
    def __init__(self, project_dir: str = None):
        """
        初始化检查点管理器
        
        Args:
            project_dir: 项目目录，默认为用户目录下的.videotranslator
        """
        if project_dir is None:
            project_dir = os.path.expanduser("~/.videotranslator/checkpoints")
        
        self.project_dir = Path(project_dir)
        self.project_dir.mkdir(parents=True, exist_ok=True)
        
        # 定义处理阶段
        self.STAGES = [
            "audio_extraction",
            "speech_recognition", 
            "text_translation",
            "subtitle_generation"
        ]
        
        # 在初始化时清理损坏的检查点
        try:
            self.cleanup_corrupted_checkpoints()
        except Exception as e:
            logger.warning(f"初始化时清理检查点失败: {e}")
    
    def _get_video_hash(self, video_path: str) -> str:
        """计算视频文件的哈希值用于唯一标识"""
        try:
            hasher = hashlib.md5()
            # 使用文件路径和大小计算哈希（避免读取整个文件）
            hasher.update(video_path.encode('utf-8'))
            if os.path.exists(video_path):
                stat = os.stat(video_path)
                hasher.update(str(stat.st_size).encode('utf-8'))
                hasher.update(str(stat.st_mtime).encode('utf-8'))
            return hasher.hexdigest()
        except Exception as e:
            logger.warning(f"计算视频哈希失败: {e}")
            return hashlib.md5(video_path.encode('utf-8')).hexdigest()
    
    def _get_checkpoint_file(self, video_path: str) -> Path:
        """获取检查点文件路径"""
        video_hash = self._get_video_hash(video_path)
        filename = f"checkpoint_{video_hash}.json"
        return self.project_dir / filename
    
    def save_checkpoint(self, video_path: str, stage: str, 
                       stage_data: Dict[str, Any], **kwargs) -> bool:
        """
        保存处理检查点
        
        Args:
            video_path: 视频文件路径
            stage: 当前完成的阶段
            stage_data: 阶段数据
            **kwargs: 其他处理参数
            
        Returns:
            保存成功返回True
        """
        try:
            checkpoint_file = self._get_checkpoint_file(video_path)
            
            # 加载现有检查点或创建新的
            if checkpoint_file.exists():
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    checkpoint = ProcessingCheckpoint(**existing_data)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"现有检查点文件损坏，将创建新的: {e}")
                    # 删除损坏的文件
                    checkpoint_file.unlink()
                    # 创建新的检查点
                    checkpoint = ProcessingCheckpoint(
                        video_path=video_path,
                        video_hash=self._get_video_hash(video_path),
                        source_language=kwargs.get('source_language', 'auto'),
                        target_language=kwargs.get('target_language', 'zh-CN'),
                        whisper_model=kwargs.get('whisper_model', 'base'),
                        translation_provider=kwargs.get('translation_provider', 'openai'),
                        timestamp=time.time(),
                        completed_stages=[],
                        stage_data={}
                    )
            else:
                checkpoint = ProcessingCheckpoint(
                    video_path=video_path,
                    video_hash=self._get_video_hash(video_path),
                    source_language=kwargs.get('source_language', 'auto'),
                    target_language=kwargs.get('target_language', 'zh-CN'),
                    whisper_model=kwargs.get('whisper_model', 'base'),
                    translation_provider=kwargs.get('translation_provider', 'openai'),
                    timestamp=time.time(),
                    completed_stages=[],
                    stage_data={}
                )
            
            # 更新检查点数据
            if stage not in checkpoint.completed_stages:
                checkpoint.completed_stages.append(stage)
            
            checkpoint.stage_data[stage] = stage_data
            checkpoint.timestamp = time.time()
            
            # 保存到文件
            checkpoint_data = asdict(checkpoint)
            # 序列化 Path 对象
            checkpoint_data = serialize_for_json(checkpoint_data)
            
            with open(checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"检查点已保存: {stage} for {os.path.basename(video_path)}")
            return True
            
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")
            return False
    
    def load_checkpoint(self, video_path: str) -> Optional[ProcessingCheckpoint]:
        """
        加载处理检查点
        
        Args:
            video_path: 视频文件路径
            
        Returns:
            检查点对象，如果不存在或无效则返回None
        """
        try:
            checkpoint_file = self._get_checkpoint_file(video_path)
            
            if not checkpoint_file.exists():
                return None

            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            checkpoint = ProcessingCheckpoint(**data)
            
            # 验证检查点有效性
            if not self._validate_checkpoint(checkpoint, video_path):
                logger.warning(f"检查点验证失败，将被忽略: {checkpoint_file}")
                return None
            
            return checkpoint
            
        except json.JSONDecodeError as e:
            logger.error(f"检查点文件JSON格式错误: {e}")
            # 删除损坏的检查点文件
            try:
                checkpoint_file = self._get_checkpoint_file(video_path)
                if checkpoint_file.exists():
                    checkpoint_file.unlink()
                    logger.info(f"已删除损坏的检查点文件: {checkpoint_file}")
            except Exception as cleanup_error:
                logger.warning(f"清理损坏检查点文件失败: {cleanup_error}")
            return None
        except Exception as e:
            logger.error(f"加载检查点失败: {e}")
            return None
    
    def _validate_checkpoint(self, checkpoint: ProcessingCheckpoint, video_path: str) -> bool:
        """验证检查点有效性"""
        try:
            # 验证视频文件是否存在且未修改
            if not os.path.exists(video_path):
                return False
            
            current_hash = self._get_video_hash(video_path)
            if current_hash != checkpoint.video_hash:
                return False
            
            # 验证检查点文件不超过7天
            if time.time() - checkpoint.timestamp > 7 * 24 * 3600:
                return False
            
            # 验证版本兼容性
            # 可以在这里添加版本检查逻辑
            
            return True
            
        except Exception:
            return False
    
    def can_resume(self, video_path: str) -> bool:
        """检查是否可以恢复处理"""
        checkpoint = self.load_checkpoint(video_path)
        return checkpoint is not None and len(checkpoint.completed_stages) > 0
    
    def get_next_stage(self, video_path: str) -> Optional[str]:
        """获取下一个需要处理的阶段"""
        checkpoint = self.load_checkpoint(video_path)
        if checkpoint is None:
            return self.STAGES[0]  # 从第一个阶段开始
        
        completed = set(checkpoint.completed_stages)
        for stage in self.STAGES:
            if stage not in completed:
                return stage
        
        return None  # 所有阶段都已完成
    
    def get_stage_data(self, video_path: str, stage: str) -> Optional[Dict[str, Any]]:
        """获取指定阶段的数据"""
        checkpoint = self.load_checkpoint(video_path)
        if checkpoint is None:
            return None
        
        return checkpoint.stage_data.get(stage)
    
    def clear_checkpoint(self, video_path: str) -> bool:
        """清除检查点（处理完成或用户主动清除）"""
        try:
            checkpoint_file = self._get_checkpoint_file(video_path)
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                logger.info(f"检查点已清除: {os.path.basename(video_path)}")
            return True
        except Exception as e:
            logger.error(f"清除检查点失败: {e}")
            return False
    
    def cleanup_old_checkpoints(self, days: int = 7) -> int:
        """清理过期的检查点文件"""
        cleaned = 0
        try:
            cutoff_time = time.time() - days * 24 * 3600
            
            for checkpoint_file in self.project_dir.glob("checkpoint_*.json"):
                try:
                    if checkpoint_file.stat().st_mtime < cutoff_time:
                        checkpoint_file.unlink()
                        cleaned += 1
                except Exception as e:
                    logger.warning(f"清理检查点文件失败 {checkpoint_file}: {e}")
            
            if cleaned > 0:
                logger.info(f"已清理 {cleaned} 个过期检查点文件")
                
        except Exception as e:
            logger.error(f"清理检查点文件失败: {e}")
        
        return cleaned
    
    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """列出所有可用的检查点"""
        checkpoints = []
        try:
            for checkpoint_file in self.project_dir.glob("checkpoint_*.json"):
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    checkpoint = ProcessingCheckpoint(**data)
                    checkpoints.append({
                        'video_path': checkpoint.video_path,
                        'timestamp': checkpoint.timestamp,
                        'completed_stages': checkpoint.completed_stages,
                        'can_resume': self._validate_checkpoint(checkpoint, checkpoint.video_path)
                    })
                except Exception as e:
                    logger.warning(f"读取检查点文件失败 {checkpoint_file}: {e}")
        
        except Exception as e:
            logger.error(f"列出检查点失败: {e}")
        
        return checkpoints

    def get_recovery_info(self, video_path: str) -> Optional[Dict[str, Any]]:
        """获取恢复信息摘要"""
        checkpoint = self.load_checkpoint(video_path)
        if checkpoint is None:
            return None
        
        next_stage = self.get_next_stage(video_path)
        progress = len(checkpoint.completed_stages) / len(self.STAGES) * 100
        
        return {
            'video_path': checkpoint.video_path,
            'progress_percent': progress,
            'completed_stages': checkpoint.completed_stages,
            'next_stage': next_stage,
            'timestamp': checkpoint.timestamp,
            'time_ago': time.time() - checkpoint.timestamp,
            'can_resume': next_stage is not None
        }
    
    def cleanup_corrupted_checkpoints(self) -> int:
        """
        清理损坏的检查点文件
        
        Returns:
            清理的文件数量
        """
        cleaned_count = 0
        try:
            for checkpoint_file in self.project_dir.glob("*.json"):
                try:
                    with open(checkpoint_file, 'r', encoding='utf-8') as f:
                        json.load(f)  # 尝试解析JSON
                except json.JSONDecodeError:
                    logger.warning(f"发现损坏的检查点文件，正在删除: {checkpoint_file}")
                    checkpoint_file.unlink()
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"检查文件时出错: {checkpoint_file} - {e}")
                    
            if cleaned_count > 0:
                logger.info(f"已清理 {cleaned_count} 个损坏的检查点文件")
                
        except Exception as e:
            logger.error(f"清理检查点文件时出错: {e}")
            
        return cleaned_count
