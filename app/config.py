#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration management for VideoTranslator
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.paths import get_config_dir

# 应用程序全局配置常量
APP_NAME = "VideoTranslator"
APP_VERSION = "2.0.0"
KEYRING_SERVICE = "VideoTranslator"

# 使用pathlib进行路径管理
DEFAULT_BASE_DIR = get_config_dir()
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
        self.theme = "system"
        self.language = "zh-CN"
        self.window_size = [1200, 800]
        self.last_directory = str(Path.home())
        
        # 新增字段以保持兼容性
        self.language_codes = LANGUAGE_CODES.copy()
        self.default_target_language = "zh-CN"
        self.default_source_language = "auto"
        # 旧版本的 dark_mode 仅用于迁移；新代码统一读取 theme。
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
            # API 密钥只保存在系统钥匙串中，绝不写入配置 JSON。
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
        # Treat the JSON file as untrusted input.  Invalid UI preferences from
        # an older or hand-edited config must not leave the application in a
        # state that no settings control can represent.
        if config.theme not in {"system", "light", "dark"}:
            config.theme = "system"
        provider = str(config.translation_provider).strip().lower()
        config.translation_provider = (
            provider if provider in TRANSLATION_PROVIDERS else "openai"
        )
        if not isinstance(config.recent_files, list):
            config.recent_files = []
        config.recent_files = [
            str(path) for path in config.recent_files if isinstance(path, (str, Path))
        ]
        try:
            config.max_recent_files = max(0, int(config.max_recent_files))
        except (TypeError, ValueError):
            config.max_recent_files = 10
        return config


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = Path(config_file or CONFIG_FILE).expanduser()
        self.config = AppConfig()
        self.last_keyring_error: Optional[str] = None
        try:
            self._ensure_config_dir()
        except OSError as exc:
            # Keep in-memory defaults usable so startup can report the path
            # problem instead of crashing before the GUI exists.
            logging.warning("配置目录不可写，将使用本次会话配置: %s", exc)
        self.load_config()

    def _ensure_config_dir(self):
        """确保配置目录存在"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                legacy_keys = data.pop('api_keys', {}) or {}
                self.config = AppConfig.from_dict(data)
                if 'theme' not in data and data.get('dark_mode'):
                    self.config.theme = 'dark'
                for provider, key in legacy_keys.items():
                    if key:
                        self.set_api_key(provider, key, save_config=False)
                self._load_api_keys_into_memory()
                # The loaded config may choose a different private temp root.
                Path(self.config.temp_dir).expanduser().mkdir(parents=True, exist_ok=True)
                if legacy_keys:
                    # 迁移后立即重写，移除旧配置中的明文密钥。
                    self.save_config()
                logging.info(f"配置已从 {self.config_file} 加载")
            else:
                logging.info("配置文件不存在，使用默认配置")
                Path(self.config.temp_dir).expanduser().mkdir(parents=True, exist_ok=True)
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
            payload = config_to_save.to_dict()
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', dir=self.config_file.parent,
                    prefix=f".{self.config_file.name}.", suffix='.tmp', delete=False
                ) as f:
                    temp_name = f.name
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.chmod(temp_name, 0o600)
                except OSError:
                    # Some Windows/network filesystems do not implement POSIX
                    # modes; the containing application directory is private.
                    pass
                os.replace(temp_name, self.config_file)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
            logging.info(f"配置已保存到 {self.config_file}")
            return True
        except Exception as e:
            logging.error(f"保存配置失败: {e}")
            return False

    def get_api_key(self, provider: str) -> str:
        """获取API密钥"""
        provider = provider.strip().lower()
        if provider in self.config.api_keys:
            return self.config.api_keys[provider]
        env_name = f"VIDEOTRANSLATOR_{provider.upper()}_API_KEY"
        env_value = os.environ.get(env_name, "")
        if env_value:
            self.config.api_keys[provider] = env_value
            return env_value
        try:
            import keyring
            value = keyring.get_password(KEYRING_SERVICE, provider) or ""
        except Exception as exc:
            logging.debug("系统钥匙串不可用: %s", exc)
            value = ""
        if value:
            self.config.api_keys[provider] = value
        return value

    def set_api_key(self, provider: str, key: str, save_config: bool = True) -> bool:
        """Store an API key in the OS keyring.

        The return value describes keyring persistence only.  If the keyring
        is unavailable the value remains usable for this process, the method
        returns ``False``, and it is still never serialized to ``config.json``.
        """
        provider = provider.strip().lower()
        key = key.strip()
        self.last_keyring_error = None
        try:
            import keyring
            if key:
                keyring.set_password(KEYRING_SERVICE, provider, key)
                self.config.api_keys[provider] = key
            else:
                try:
                    keyring.delete_password(KEYRING_SERVICE, provider)
                except keyring.errors.PasswordDeleteError:
                    pass
                self.config.api_keys.pop(provider, None)
        except Exception as e:
            # 保留本次会话可用性，但不降级为明文落盘。
            if key:
                self.config.api_keys[provider] = key
            else:
                self.config.api_keys.pop(provider, None)
            self.last_keyring_error = str(e)
            logging.warning("系统钥匙串不可用，API 密钥仅在本次会话有效: %s", e)
            if save_config:
                self.save_config()
            return False
        if save_config and not self.save_config():
            # The secret itself is already safely persisted.  A failure to
            # rewrite non-secret preferences must not be reported as a
            # keyring failure, but is still visible in the log.
            logging.error("API 密钥已保存，但配置文件写入失败")
        return True

    def _load_api_keys_into_memory(self) -> None:
        for provider in TRANSLATION_PROVIDERS:
            self.get_api_key(provider)

    def add_recent_file(self, file_path: str) -> bool:
        """添加最近文件"""
        try:
            file_path = str(Path(file_path).expanduser().resolve())
            path_key = os.path.normcase(file_path)
            # Normalize historical relative entries while removing duplicates.
            self.config.recent_files = [
                existing
                for existing in self.config.recent_files
                if os.path.normcase(str(Path(existing).expanduser().resolve())) != path_key
            ]
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
