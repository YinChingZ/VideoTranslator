#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration management for VideoTranslator
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# 应用程序全局配置常量
APP_NAME = "VideoTranslator"
APP_VERSION = "1.0.0"

# 使用pathlib进行路径管理
DEFAULT_BASE_DIR = Path.home() / ".videotranslator"
CONFIG_FILE = DEFAULT_BASE_DIR / "config.json"

# 支持的语言代码映射
LANGUAGE_CODES = {
    "zh-CN": "中文(简体)",
    "zh-TW": "中文(繁体)",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "ar": "阿拉伯语",
}

# Whisper模型选项
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]

# 翻译服务提供商
TRANSLATION_PROVIDERS = ["openai", "deepl", "google"]

# 支持的语言
LANGUAGES = {
    "zh-CN": "中文",
    "en": "English"
}


class AppConfig:
    """应用配置类，支持字典式访问"""

    def __init__(self):
        self.app_name = APP_NAME
        self.app_version = APP_VERSION
        self.debug = False
        self.log_level = "INFO"

        # 目录配置
        self.base_dir = DEFAULT_BASE_DIR
        self.temp_dir = self.base_dir / "temp"
        self.output_dir = Path.home() / "Videos" / "VideoTranslator"

        # 视频配置
        self.supported_video_formats = ["mp4", "mkv", "avi", "mov", "webm"]
        self.supported_subtitle_formats = ["srt", "vtt", "ass"]

        # 处理配置
        self.whisper_model = "base"
        self.translation_provider = "openai"
        self.source_language = "auto"
        self.target_language = "zh-CN"

        # API密钥
        self.api_keys = {}

        # 最近文件
        self.recent_files = []
        self.max_recent_files = 10

        # 界面配置
        self.theme = "dark"
        self.language = "zh-CN"
        self.window_size = [1200, 800]
        self.last_directory = str(Path.home())
        
        # 新增字段以保持兼容性
        self.language_codes = LANGUAGE_CODES.copy()
        self.default_target_language = "zh-CN"
        self.default_source_language = "auto"
        self.dark_mode = False

    def get(self, key: str, default=None):
        """字典式访问方法，保持向后兼容"""
        return getattr(self, key, default)
    
    def __getitem__(self, key: str):
        """支持方括号访问"""
        return getattr(self, key)
    
    def __setitem__(self, key: str, value):
        """支持方括号赋值"""
        setattr(self, key, value)
    
    def __contains__(self, key: str):
        """支持in操作符"""
        return hasattr(self, key)

    def setdefault(self, key: str, default=None):
        """字典式setdefault方法"""
        if hasattr(self, key):
            return getattr(self, key)
        else:
            setattr(self, key, default)
            return default

    def keys(self):
        """返回所有属性名（字典式接口）"""
        return [attr for attr in dir(self) if not attr.startswith('_') and not callable(getattr(self, attr))]

    def items(self):
        """返回所有属性键值对（字典式接口）"""
        return [(key, getattr(self, key)) for key in self.keys()]

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'app_name': self.app_name,
            'app_version': self.app_version,
            'debug': self.debug,
            'log_level': self.log_level,
            'base_dir': str(self.base_dir),
            'temp_dir': str(self.temp_dir),
            'output_dir': str(self.output_dir),
            'supported_video_formats': self.supported_video_formats,
            'supported_subtitle_formats': self.supported_subtitle_formats,
            'whisper_model': self.whisper_model,
            'translation_provider': self.translation_provider,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'api_keys': self.api_keys,
            'recent_files': self.recent_files,
            'max_recent_files': self.max_recent_files,
            'theme': self.theme,
            'language': self.language,
            'window_size': self.window_size,
            'last_directory': self.last_directory,
            'language_codes': self.language_codes,
            'default_target_language': self.default_target_language,
            'default_source_language': self.default_source_language,
            'dark_mode': self.dark_mode
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """从字典创建配置"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                if key in ['base_dir', 'temp_dir', 'output_dir']:
                    setattr(config, key, Path(value))
                else:
                    setattr(config, key, value)
        return config


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or CONFIG_FILE
        self.config = AppConfig()
        self._ensure_config_dir()
        self.load_config()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        # 创建必要的子目录
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
                logging.info(f"配置已从 {self.config_file} 加载")
            else:
                logging.info("配置文件不存在，使用默认配置")
                self.save_config()
            return True
        except Exception as e:
            logging.error(f"加载配置失败: {e}")
            self.config = AppConfig()  # 使用默认配置
            return False

    def save_config(self, config: Optional[AppConfig] = None) -> bool:
        """保存配置文件"""
        try:
            config_to_save = config or self.config
            self._ensure_config_dir()
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_to_save.to_dict(), f, ensure_ascii=False, indent=2)
            logging.info(f"配置已保存到 {self.config_file}")
            return True
        except Exception as e:
            logging.error(f"保存配置失败: {e}")
            return False

    def get_api_key(self, provider: str) -> str:
        """获取API密钥"""
        return self.config.api_keys.get(provider, "")

    def set_api_key(self, provider: str, key: str) -> bool:
        """设置API密钥"""
        try:
            self.config.api_keys[provider] = key
            return self.save_config()
        except Exception as e:
            logging.error(f"设置API密钥失败: {e}")
            return False

    def add_recent_file(self, file_path: str) -> bool:
        """添加最近文件"""
        try:
            file_path = str(Path(file_path).resolve())
            # 移除重复项
            if file_path in self.config.recent_files:
                self.config.recent_files.remove(file_path)
            # 添加到开头
            self.config.recent_files.insert(0, file_path)
            # 限制数量
            if len(self.config.recent_files) > self.config.max_recent_files:
                self.config.recent_files = self.config.recent_files[:self.config.max_recent_files]
            return self.save_config()
        except Exception as e:
            logging.error(f"添加最近文件失败: {e}")
            return False


# 全局配置管理器实例
_config_manager = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例（单例模式）"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
