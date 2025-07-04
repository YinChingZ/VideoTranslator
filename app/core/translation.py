#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Translation module for video translation system.
Supports multiple translation APIs with caching, batch processing,
terminology management, and error recovery.

Refactored version with improved performance and maintainability.
"""

import os
import logging
import json
import hashlib
import time
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import sqlite3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Constants
DEFAULT_RETRY_COUNT = 3
DEFAULT_BACKOFF_FACTOR = 0.5
DEFAULT_BATCH_SIZE = 10
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_CACHE_SIZE = 1000  # entries


@dataclass
class TranslationResult:
    """Class to represent a translation result."""
    original_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    confidence: float = 0.0
    service: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class TranslationRequest:
    """Class to represent a translation request."""
    text: str
    source_lang: str
    target_lang: str
    context: Optional[str] = None
    terminology: Optional[Dict[str, str]] = None


class TranslationError(Exception):
    """Base exception for translation errors."""
    pass


class ServiceUnavailableError(TranslationError):
    """Raised when a translation service is unavailable."""
    pass


class QuotaExceededError(TranslationError):
    """Raised when translation quota is exceeded."""
    pass


class TranslationCache:
    """
    Improved cache with LRU memory cache + SQLite persistence.
    """
    
    def __init__(self, cache_path: str = None, max_memory_size: int = 1000):
        """
        Initialize the translation cache.
        
        Args:
            cache_path: Path to cache file (if None, use default location)
            max_memory_size: Maximum number of entries in memory cache
        """
        self.max_memory_size = max_memory_size
        self._memory_cache = {}  # Simple dict-based LRU implementation
        self._access_order = []  # Track access order for LRU
        
        # Determine cache path
        if cache_path is None:
            user_cache_dir = os.path.join(
                os.path.expanduser("~"),
                ".cache",
                "video_translator"
            )
            os.makedirs(user_cache_dir, exist_ok=True)
            self.cache_path = os.path.join(user_cache_dir, "translation_cache.db")
        else:
            self.cache_path = cache_path
            
        self._init_db()
        
    def _init_db(self):
        """Initialize the SQLite database for persistent caching."""
        self.conn = sqlite3.connect(self.cache_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                hash TEXT PRIMARY KEY,
                original_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                source_lang TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                service TEXT NOT NULL,
                timestamp REAL NOT NULL,
                confidence REAL,
                metadata TEXT
            )
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_translations_timestamp 
            ON translations(timestamp)
        """)
        
        self.conn.commit()
        
    def _generate_key(self, text: str, source_lang: str, target_lang: str, service: str) -> str:
        """Generate a unique cache key."""
        key_str = f"{text}:{source_lang}:{target_lang}:{service}"
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
        
    def _maintain_lru(self, key: str):
        """Maintain LRU order in memory cache."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
        
        # Remove oldest entries if exceeding max size
        while len(self._memory_cache) > self.max_memory_size:
            oldest_key = self._access_order.pop(0)
            self._memory_cache.pop(oldest_key, None)
    
    def get(self, text: str, source_lang: str, target_lang: str, 
            service: str) -> Optional[TranslationResult]:
        """Get translation from cache."""
        key = self._generate_key(text, source_lang, target_lang, service)
        
        # Check memory cache first
        if key in self._memory_cache:
            self._maintain_lru(key)
            return self._memory_cache[key]
        
        # Check persistent cache
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT original_text, translated_text, source_lang, target_lang, "
            "service, confidence, metadata FROM translations WHERE hash = ?", 
            (key,)
        )
        
        result = cursor.fetchone()
        if result:
            original, translated, src_lang, tgt_lang, svc, confidence, metadata_str = result
            
            # Parse metadata
            metadata = json.loads(metadata_str) if metadata_str else {}
                
            # Create result object
            translation_result = TranslationResult(
                original_text=original,
                translated_text=translated,
                source_lang=src_lang,
                target_lang=tgt_lang,
                confidence=confidence or 0.0,
                service=svc,
                metadata=metadata
            )
            
            # Store in memory cache
            self._memory_cache[key] = translation_result
            self._maintain_lru(key)
            
            return translation_result
            
        return None
    
    def store(self, result: TranslationResult):
        """Store translation result in cache."""
        key = self._generate_key(
            result.original_text, 
            result.source_lang, 
            result.target_lang,
            result.service
        )
        
        # Store in memory cache
        self._memory_cache[key] = result
        self._maintain_lru(key)
        
        # Store in persistent cache
        metadata_str = json.dumps(result.metadata) if result.metadata else None
        
        self.conn.execute(
            "INSERT OR REPLACE INTO translations "
            "(hash, original_text, translated_text, source_lang, target_lang, "
            "service, timestamp, confidence, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key, result.original_text, result.translated_text,
                result.source_lang, result.target_lang, result.service,
                time.time(), result.confidence, metadata_str
            )
        )
        self.conn.commit()


class TerminologyManager:
    """Manages translation terminology and glossaries."""
    
    def __init__(self):
        self.terminology: Dict[str, Dict[str, str]] = {}
        self.load_default_terminology()
    
    def load_default_terminology(self):
        """Load default technical terminology."""
        self.terminology = {
            "zh-en": {
                "字幕": "subtitle",
                "视频": "video", 
                "翻译": "translation",
                "语音识别": "speech recognition",
                "人工智能": "artificial intelligence"
            },
            "en-zh": {
                "subtitle": "字幕",
                "video": "视频",
                "translation": "翻译", 
                "speech recognition": "语音识别",
                "artificial intelligence": "人工智能"
            }
        }
    
    def add_term(self, source_lang: str, target_lang: str, source_term: str, target_term: str):
        """Add a terminology entry."""
        lang_pair = f"{source_lang}-{target_lang}"
        if lang_pair not in self.terminology:
            self.terminology[lang_pair] = {}
        self.terminology[lang_pair][source_term] = target_term
    
    def apply_terminology(self, text: str, source_lang: str, target_lang: str) -> str:
        """Apply terminology replacements to text."""
        lang_pair = f"{source_lang}-{target_lang}"
        if lang_pair not in self.terminology:
            return text
        
        result = text
        for source_term, target_term in self.terminology[lang_pair].items():
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(source_term) + r'\b'
            result = re.sub(pattern, target_term, result, flags=re.IGNORECASE)
        
        return result


class TranslatorInterface(ABC):
    """Abstract base class for translation service implementations."""
    
    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=DEFAULT_RETRY_COUNT,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    @abstractmethod
    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        """Translate a single text."""
        pass
    
    def translate_batch(self, requests: List[TranslationRequest]) -> List[TranslationResult]:
        """Translate multiple texts. Default implementation processes sequentially."""
        results = []
        for request in requests:
            try:
                result = self.translate_single(request)
                results.append(result)
            except Exception as e:
                logger.error(f"Translation failed for '{request.text[:50]}...': {e}")
                # Return failed result instead of raising exception
                results.append(TranslationResult(
                    original_text=request.text,
                    translated_text=request.text,  # Fallback to original
                    source_lang=request.source_lang,
                    target_lang=request.target_lang,
                    confidence=0.0,
                    service=self.__class__.__name__,
                    metadata={"error": str(e)}
                ))
        return results
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the service is available."""
        pass


class DeepLTranslator(TranslatorInterface):
    """DeepL API translation service."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://api-free.deepl.com/v2"
        if api_key and not api_key.endswith(":fx"):
            self.base_url = "https://api.deepl.com/v2"
    
    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        """Translate using DeepL API."""
        if not self.api_key:
            raise ServiceUnavailableError("DeepL API key not configured")
        
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
        data = {
            "text": [request.text],
            "source_lang": request.source_lang.upper(),
            "target_lang": request.target_lang.upper(),
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/translate",
                headers=headers,
                data=data,
                timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            
            result_data = response.json()
            translated_text = result_data["translations"][0]["text"]
            detected_lang = result_data["translations"][0].get("detected_source_language", request.source_lang)
            
            return TranslationResult(
                original_text=request.text,
                translated_text=translated_text,
                source_lang=detected_lang.lower(),
                target_lang=request.target_lang,
                confidence=0.95,  # DeepL generally high quality
                service="DeepL",
                metadata={"detected_language": detected_lang}
            )
        except requests.exceptions.RequestException as e:
            raise ServiceUnavailableError(f"DeepL API error: {e}")
    
    def translate_batch(self, requests: List[TranslationRequest]) -> List[TranslationResult]:
        """DeepL supports batch translation."""
        if not requests:
            return []
        
        # Group by language pair for efficiency
        grouped = {}
        for i, req in enumerate(requests):
            key = (req.source_lang, req.target_lang)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append((i, req))
        
        results = [None] * len(requests)
        
        for (source_lang, target_lang), items in grouped.items():
            texts = [req.text for _, req in items]
            
            headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
            data = {
                "text": texts,
                "source_lang": source_lang.upper(),
                "target_lang": target_lang.upper(),
            }
            
            try:
                response = self.session.post(
                    f"{self.base_url}/translate",
                    headers=headers,
                    data=data,
                    timeout=DEFAULT_TIMEOUT
                )
                response.raise_for_status()
                
                result_data = response.json()
                translations = result_data["translations"]
                
                for (original_idx, req), translation in zip(items, translations):
                    results[original_idx] = TranslationResult(
                        original_text=req.text,
                        translated_text=translation["text"],
                        source_lang=translation.get("detected_source_language", source_lang).lower(),
                        target_lang=target_lang,
                        confidence=0.95,
                        service="DeepL"
                    )
                    
            except Exception as e:
                logger.error(f"DeepL batch translation failed: {e}")
                # Fill failed results
                for original_idx, req in items:
                    results[original_idx] = TranslationResult(
                        original_text=req.text,
                        translated_text=req.text,
                        source_lang=req.source_lang,
                        target_lang=req.target_lang,
                        confidence=0.0,
                        service="DeepL",
                        metadata={"error": str(e)}
                    )
        
        return results
    
    def is_available(self) -> bool:
        """Check DeepL service availability."""
        if not self.api_key:
            return False
        
        try:
            headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
            response = self.session.get(
                f"{self.base_url}/usage",
                headers=headers,
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False


class FallbackTranslator(TranslatorInterface):
    """回退翻译器，当其他服务不可用时使用"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
    
    def is_available(self) -> bool:
        """回退翻译器总是可用的"""
        return True
    
    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        """简单的回退翻译：返回原文本并记录警告"""
        logger.warning(f"使用回退翻译器：无可用的翻译服务，返回原文本")
        
        return TranslationResult(
            original_text=request.text,
            translated_text=request.text,  # 返回原文本
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            confidence=0.0,  # 低置信度表示这不是真正的翻译
            service="fallback",
            metadata={"warning": "No translation service available"}
        )
    
    def translate_batch(self, requests: List[TranslationRequest]) -> List[TranslationResult]:
        """批量回退翻译"""
        return [self.translate_single(request) for request in requests]


class TranslationManager:
    """
    Main translation manager with service failover and caching.
    """
    
    def __init__(self, api_keys: Dict[str, str] = None, cache_path: str = None, primary_service: str = None):
        """
        Initialize translation manager.
        
        Args:
            api_keys: Dictionary of API keys for different services
            cache_path: Path to cache database
            primary_service: Primary translation service to use
        """
        self.api_keys = api_keys or {}
        self.cache = TranslationCache(cache_path)
        self.terminology = TerminologyManager()
        
        # Initialize available services
        self.services = {}
        self._init_services()
        
        # Service priority order - use primary_service if specified
        if primary_service:
            # Move primary service to front of priority list
            available_services = ["DeepL", "OpenAI", "Google", "Fallback"]
            primary_service_title = primary_service.title()
            if primary_service_title in available_services:
                self.service_priority = [primary_service_title] + [s for s in available_services if s != primary_service_title]
            else:
                # If primary service is not recognized, use default order
                self.service_priority = ["DeepL", "OpenAI", "Google", "Fallback"]
        else:
            self.service_priority = ["DeepL", "OpenAI", "Google", "Fallback"]
    
    def _init_services(self):
        """Initialize available translation services."""
        if "deepl" in self.api_keys:
            self.services["DeepL"] = DeepLTranslator(self.api_keys["deepl"])
        
        # TODO: 实现 OpenAI 和 Google 翻译器
        # if "openai" in self.api_keys:
        #     self.services["OpenAI"] = OpenAITranslator(self.api_keys["openai"])
        # if "google" in self.api_keys:
        #     self.services["Google"] = GoogleTranslator(self.api_keys["google"])
        
        # 总是添加回退翻译器作为最后的选择
        self.services["Fallback"] = FallbackTranslator()
        
        logger.info(f"初始化了 {len(self.services)} 个翻译服务: {list(self.services.keys())}")
    
    def translate(self, text: str, source_lang: str = "auto", 
                 target_lang: str = "en", use_cache: bool = True) -> TranslationResult:
        """
        Translate text using available services with failover.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code  
            use_cache: Whether to use caching
            
        Returns:
            TranslationResult object
        """
        if not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text=text,
                source_lang=source_lang,
                target_lang=target_lang,
                confidence=1.0,
                service="passthrough"
            )
        
        # Check cache first
        if use_cache:
            for service_name in self.service_priority:
                if service_name in self.services:
                    cached_result = self.cache.get(text, source_lang, target_lang, service_name)
                    if cached_result:
                        logger.debug(f"Cache hit for '{text[:50]}...' using {service_name}")
                        return cached_result
        
        # Try services in priority order
        for service_name in self.service_priority:
            if service_name not in self.services:
                continue
                
            service = self.services[service_name]
            if not service.is_available():
                logger.warning(f"{service_name} service is not available")
                continue
            
            try:
                request = TranslationRequest(
                    text=text,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
                
                result = service.translate_single(request)
                
                # Apply terminology if available
                result.translated_text = self.terminology.apply_terminology(
                    result.translated_text, source_lang, target_lang
                )
                
                # Cache the result
                if use_cache:
                    self.cache.store(result)
                
                logger.debug(f"Successfully translated using {service_name}")
                return result
                
            except Exception as e:
                logger.error(f"{service_name} translation failed: {e}")
                continue
        
        # All services failed - but this should not happen with fallback service
        logger.error("All translation services failed, including fallback")
        return TranslationResult(
            original_text=text,
            translated_text=text,  # 返回原文本
            source_lang=source_lang, 
            target_lang=target_lang,
            confidence=0.0,
            service="emergency_fallback",
            metadata={"error": "All services failed including fallback"}
        )
    
    def translate_batch(self, texts: List[str], source_lang: str = "auto",
                       target_lang: str = "en", use_cache: bool = True,
                       max_workers: int = 5) -> List[TranslationResult]:
        """
        Translate multiple texts efficiently with caching and batching.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            use_cache: Whether to use caching
            max_workers: Maximum concurrent workers
            
        Returns:
            List of TranslationResult objects
        """
        if not texts:
            return []
        
        results = []
        uncached_indices = []
        uncached_texts = []
        
        # Check cache for each text
        for i, text in enumerate(texts):
            if not text.strip():
                results.append(TranslationResult(
                    original_text=text,
                    translated_text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    confidence=1.0,
                    service="passthrough"
                ))
                continue
            
            cached_result = None
            if use_cache:
                for service_name in self.service_priority:
                    if service_name in self.services:
                        cached_result = self.cache.get(text, source_lang, target_lang, service_name)
                        if cached_result:
                            break
            
            if cached_result:
                results.append(cached_result)
            else:
                results.append(None)  # Placeholder
                uncached_indices.append(i)
                uncached_texts.append(text)
        
        # Translate uncached texts
        if uncached_texts:
            logger.info(f"Translating {len(uncached_texts)} uncached texts")
            
            # Use the first available service for batch translation
            service = None
            for service_name in self.service_priority:
                if service_name in self.services and self.services[service_name].is_available():
                    service = self.services[service_name]
                    break
            
            if service:
                requests = [
                    TranslationRequest(text=text, source_lang=source_lang, target_lang=target_lang)
                    for text in uncached_texts
                ]
                
                batch_results = service.translate_batch(requests)
                
                # Apply terminology and cache results
                for i, result in enumerate(batch_results):
                    result.translated_text = self.terminology.apply_terminology(
                        result.translated_text, source_lang, target_lang
                    )
                    
                    if use_cache:
                        self.cache.store(result)
                    
                    # Place result in correct position
                    original_index = uncached_indices[i]
                    results[original_index] = result
            else:
                # No service available - fill with fallback results
                for i in uncached_indices:
                    results[i] = TranslationResult(
                        original_text=texts[i],
                        translated_text=texts[i],
                        source_lang=source_lang,
                        target_lang=target_lang,
                        confidence=0.0,
                        service="fallback",
                        metadata={"error": "No service available"}
                    )
        
        return results


# For backward compatibility
Translator = TranslationManager
