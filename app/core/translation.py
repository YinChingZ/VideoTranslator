#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Translation module for video translation system.
Supports multiple translation APIs with caching, batch processing,
terminology management, and error recovery.

Refactored version with improved performance and maintainability.
"""

import hashlib
import html
import json
import logging
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.utils.paths import ensure_private_directory, get_cache_dir

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
            cache_dir = ensure_private_directory(get_cache_dir())
            self.cache_path = str(cache_dir / "translation-cache.db")
        else:
            self.cache_path = str(Path(cache_path).expanduser())
            Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
            
        self._init_db()
        
    def _init_db(self):
        """Initialize the SQLite database for persistent caching."""
        self._db_lock = threading.RLock()
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
        with self._db_lock:
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
            try:
                metadata = json.loads(metadata_str) if metadata_str else {}
            except (json.JSONDecodeError, TypeError):
                logger.warning("Ignoring translation cache entry with invalid metadata")
                with self._db_lock:
                    self.conn.execute("DELETE FROM translations WHERE hash = ?", (key,))
                    self.conn.commit()
                return None
                
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
        
        with self._db_lock:
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

    def close(self) -> None:
        """Flush and close the persistent cache connection idempotently."""
        connection = getattr(self, "conn", None)
        if connection is None:
            return
        with self._db_lock:
            connection.commit()
            connection.close()
            self.conn = None

    def clear(self) -> None:
        """Remove persistent and in-memory translations atomically."""
        with self._db_lock:
            self.conn.execute("DELETE FROM translations")
            self.conn.commit()
        self._memory_cache.clear()
        self._access_order.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


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
        """Translate multiple texts sequentially and preserve per-item failures."""
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
                    metadata={
                        "error": str(e),
                        "success": False,
                        "fallback": False,
                    }
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
            "target_lang": request.target_lang.upper(),
        }
        # DeepL performs language detection when source_lang is omitted; the
        # literal value "AUTO" is not a valid API language code.
        if request.source_lang.lower() != "auto":
            data["source_lang"] = request.source_lang.upper()
        
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
                metadata={
                    "detected_language": detected_lang,
                    "success": True,
                    "fallback": False,
                }
            )
        except requests.exceptions.RequestException as e:
            raise ServiceUnavailableError(f"DeepL API error: {e}")
    
    def translate_batch(self, requests: List[TranslationRequest]) -> List[TranslationResult]:
        """DeepL supports batch translation."""
        if not requests:
            return []
        if not self.api_key:
            raise ServiceUnavailableError("DeepL API key not configured")
        
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
                "target_lang": target_lang.upper(),
            }
            if source_lang.lower() != "auto":
                data["source_lang"] = source_lang.upper()
            
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
                if len(translations) != len(items):
                    raise TranslationError(
                        "DeepL returned a different number of translations"
                    )
                
                for (original_idx, req), translation in zip(items, translations):
                    results[original_idx] = TranslationResult(
                        original_text=req.text,
                        translated_text=translation["text"],
                        source_lang=translation.get("detected_source_language", source_lang).lower(),
                        target_lang=target_lang,
                        confidence=0.95,
                        service="DeepL",
                        metadata={"success": True, "fallback": False},
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
                        metadata={
                            "error": str(e),
                            "success": False,
                            "fallback": False,
                        }
                    )
        
        return results
    
    def is_available(self) -> bool:
        """Return whether DeepL is configured without a redundant network probe.

        ``translate_single`` is the authoritative availability check and lets
        the manager fail over on real API errors.  Calling ``/usage`` here made
        every subtitle incur an extra request and could incorrectly skip a
        healthy translation endpoint during a transient usage-endpoint error.
        """

        return bool(self.api_key)


class OpenAITranslator(TranslatorInterface):
    """Translate text with OpenAI's Responses API."""

    def __init__(self, api_key: str, model: str = "gpt-5.6-luna", **kwargs):
        super().__init__(api_key, **kwargs)
        self.model = model
        self.base_url = "https://api.openai.com/v1/responses"

    @staticmethod
    def _language_label(language_code: str) -> str:
        labels = {
            "ar": "Arabic",
            "de": "German",
            "en": "English",
            "es": "Spanish",
            "fr": "French",
            "it": "Italian",
            "ja": "Japanese",
            "ko": "Korean",
            "pt": "Portuguese",
            "ru": "Russian",
            "zh": "Chinese",
            "zh-cn": "Simplified Chinese",
            "zh-tw": "Traditional Chinese",
        }
        normalized = language_code.lower()
        return labels.get(normalized, labels.get(normalized.split("-")[0], language_code))

    @staticmethod
    def _extract_output_text(response_data: Dict[str, Any]) -> str:
        """Extract assistant text from the raw Responses API response."""
        if isinstance(response_data.get("output_text"), str):
            return response_data["output_text"].strip()

        text_parts = []
        for item in response_data.get("output", []):
            if item.get("type") != "message" or item.get("role") != "assistant":
                continue
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    value = content.get("text")
                    if isinstance(value, str):
                        text_parts.append(value)

        return "".join(text_parts).strip()

    @staticmethod
    def _raise_for_api_error(response: requests.Response) -> None:
        if response.status_code == 429:
            raise QuotaExceededError("OpenAI API quota or rate limit exceeded")
        if response.status_code in {401, 403}:
            raise ServiceUnavailableError("OpenAI API key is invalid or unauthorized")
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ServiceUnavailableError(f"OpenAI API error: {exc}") from exc

    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        if not self.api_key:
            raise ServiceUnavailableError("OpenAI API key not configured")

        source_label = (
            "the detected source language"
            if request.source_lang == "auto"
            else self._language_label(request.source_lang)
        )
        target_label = self._language_label(request.target_lang)
        instructions = (
            "You are a professional subtitle translator. Translate faithfully "
            f"from {source_label} to {target_label}. Return only the translated "
            "text, with no preamble, quotation marks, or commentary. Preserve "
            "line breaks, punctuation, tone, names, and subtitle timing cues."
        )
        if request.context:
            instructions += f" Context: {request.context}"
        if request.terminology:
            glossary = ", ".join(
                f"{source} -> {target}"
                for source, target in request.terminology.items()
            )
            instructions += f" Required terminology: {glossary}"

        payload = {
            "model": self.model,
            "instructions": instructions,
            "input": request.text,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = self.session.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=DEFAULT_TIMEOUT * 2,
            )
            self._raise_for_api_error(response)
            response_data = response.json()
        except (QuotaExceededError, ServiceUnavailableError):
            raise
        except (requests.exceptions.RequestException, ValueError) as exc:
            raise ServiceUnavailableError(f"OpenAI API error: {exc}") from exc

        translated_text = self._extract_output_text(response_data)
        if not translated_text:
            raise TranslationError("OpenAI Responses API returned no translated text")

        return TranslationResult(
            original_text=request.text,
            translated_text=translated_text,
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            confidence=0.9,
            service="OpenAI",
            metadata={
                "provider": "openai",
                "model": response_data.get("model", self.model),
                "response_id": response_data.get("id"),
                "usage": response_data.get("usage", {}),
                "success": True,
                "fallback": False,
            },
        )

    def translate_batch(
        self, requests: List[TranslationRequest]
    ) -> List[TranslationResult]:
        """Translate a batch while preserving the abstract adapter contract."""
        if not requests:
            return []

        # Each Responses API call returns one unconstrained text value. Keeping
        # one request per subtitle avoids delimiter/JSON hallucinations and
        # ensures subtitle-to-result alignment. The manager can still fail over
        # individual failed entries to another provider.
        return super().translate_batch(requests)

    def is_available(self) -> bool:
        # Avoid a paid/network probe for every subtitle. A configured key means
        # the service is eligible; translate_single reports authoritative API
        # errors and lets the manager fail over.
        return bool(self.api_key)


class GoogleTranslator(TranslatorInterface):
    """Google Cloud Translation Basic (v2) REST adapter."""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        self.base_url = "https://translation.googleapis.com/language/translate/v2"

    @staticmethod
    def _normalize_language_code(language_code: str) -> str:
        normalized = language_code.strip()
        if normalized.lower() == "auto":
            return ""
        # Google's documented examples use ISO-639 codes. Keep regions for
        # Chinese, where zh-CN/zh-TW carry useful script intent.
        if normalized.lower().startswith("zh-"):
            return normalized
        return normalized.split("-")[0]

    @staticmethod
    def _raise_for_api_error(response: requests.Response) -> None:
        if response.status_code == 429:
            raise QuotaExceededError("Google Translation API quota or rate limit exceeded")
        if response.status_code in {400, 401, 403}:
            raise ServiceUnavailableError(
                "Google Translation API rejected the request or API key"
            )
        try:
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ServiceUnavailableError(f"Google Translation API error: {exc}") from exc

    def _translate_requests(
        self, requests_to_translate: List[TranslationRequest]
    ) -> List[TranslationResult]:
        if not self.api_key:
            raise ServiceUnavailableError("Google Translation API key not configured")
        if not requests_to_translate:
            return []

        source_lang = requests_to_translate[0].source_lang
        target_lang = requests_to_translate[0].target_lang
        data = {
            "q": [request.text for request in requests_to_translate],
            "target": self._normalize_language_code(target_lang),
            "format": "text",
        }
        normalized_source = self._normalize_language_code(source_lang)
        if normalized_source:
            data["source"] = normalized_source

        try:
            response = self.session.post(
                self.base_url,
                params={"key": self.api_key},
                json=data,
                timeout=DEFAULT_TIMEOUT,
            )
            self._raise_for_api_error(response)
            translations = response.json().get("data", {}).get("translations", [])
        except (QuotaExceededError, ServiceUnavailableError):
            raise
        except (requests.exceptions.RequestException, ValueError) as exc:
            raise ServiceUnavailableError(
                f"Google Translation API error: {exc}"
            ) from exc

        if len(translations) != len(requests_to_translate):
            raise TranslationError(
                "Google Translation API returned a different number of translations"
            )

        results = []
        for request, translation in zip(requests_to_translate, translations):
            translated_text = translation.get("translatedText")
            if not isinstance(translated_text, str):
                raise TranslationError("Google Translation API returned invalid text")
            detected_lang = translation.get(
                "detectedSourceLanguage", request.source_lang
            )
            results.append(
                TranslationResult(
                    original_text=request.text,
                    translated_text=html.unescape(translated_text),
                    source_lang=detected_lang,
                    target_lang=request.target_lang,
                    confidence=1.0,
                    service="Google",
                    metadata={
                        "provider": "google",
                        "detected_source_language": detected_lang,
                        "model": translation.get("model", "nmt"),
                        "success": True,
                        "fallback": False,
                    },
                )
            )
        return results

    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        return self._translate_requests([request])[0]

    def translate_batch(
        self, requests: List[TranslationRequest]
    ) -> List[TranslationResult]:
        if not requests:
            return []

        # Manager requests share a language pair, but grouping here keeps the
        # adapter safe for direct callers and honors Google's 128-string limit.
        results: List[Optional[TranslationResult]] = [None] * len(requests)
        grouped: Dict[Tuple[str, str], List[Tuple[int, TranslationRequest]]] = {}
        for index, request in enumerate(requests):
            grouped.setdefault(
                (request.source_lang, request.target_lang), []
            ).append((index, request))

        for items in grouped.values():
            for offset in range(0, len(items), 128):
                chunk = items[offset:offset + 128]
                chunk_results = self._translate_requests(
                    [request for _, request in chunk]
                )
                for (index, _), result in zip(chunk, chunk_results):
                    results[index] = result

        return [result for result in results if result is not None]

    def is_available(self) -> bool:
        return bool(self.api_key)


class FallbackTranslator(TranslatorInterface):
    """回退翻译器，当其他服务不可用时使用"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key
    
    def is_available(self) -> bool:
        """回退翻译器总是可用的"""
        return True
    
    def translate_single(self, request: TranslationRequest) -> TranslationResult:
        """简单的回退翻译：返回原文本并记录警告"""
        logger.warning("使用回退翻译器：无可用的翻译服务，返回原文本")
        
        return TranslationResult(
            original_text=request.text,
            translated_text=request.text,  # 返回原文本
            source_lang=request.source_lang,
            target_lang=request.target_lang,
            confidence=0.0,  # 低置信度表示这不是真正的翻译
            service="fallback",
            metadata={
                "warning": "No translation service available; original text returned",
                "error": "no_translation_service",
                "success": False,
                "fallback": True,
            }
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
            provider_names = {
                "deepl": "DeepL",
                "openai": "OpenAI",
                "google": "Google",
                "fallback": "Fallback",
            }
            primary_service_title = provider_names.get(primary_service.lower())
            if primary_service_title in available_services:
                self.service_priority = [primary_service_title] + [s for s in available_services if s != primary_service_title]
            else:
                # If primary service is not recognized, use default order
                self.service_priority = ["DeepL", "OpenAI", "Google", "Fallback"]
        else:
            self.service_priority = ["DeepL", "OpenAI", "Google", "Fallback"]

    def close(self) -> None:
        """Release the SQLite cache owned by this manager."""
        self.cache.close()
    
    def _init_services(self):
        """Initialize available translation services."""
        normalized_keys = {
            str(provider).lower(): value
            for provider, value in self.api_keys.items()
        }

        if normalized_keys.get("deepl"):
            self.services["DeepL"] = DeepLTranslator(normalized_keys["deepl"])

        if normalized_keys.get("openai"):
            self.services["OpenAI"] = OpenAITranslator(
                normalized_keys["openai"],
                model=normalized_keys.get("openai_model", "gpt-5.6-luna"),
            )

        if normalized_keys.get("google"):
            self.services["Google"] = GoogleTranslator(normalized_keys["google"])
        
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
                service="passthrough",
                metadata={"success": True, "fallback": False},
            )
        
        # Check cache first
        if use_cache:
            for service_name in self.service_priority:
                if service_name in self.services and service_name != "Fallback":
                    cached_result = self.cache.get(text, source_lang, target_lang, service_name)
                    if cached_result and cached_result.metadata.get("success", True):
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
                
                # Never cache a fallback passthrough as a successful
                # translation. Doing so would mask a newly configured service
                # on the next attempt.
                if use_cache and result.metadata.get("success", True):
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
            metadata={
                "error": "all_translation_services_failed",
                "success": False,
                "fallback": True,
            }
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
                    service="passthrough",
                    metadata={"success": True, "fallback": False},
                ))
                continue
            
            cached_result = None
            if use_cache:
                for service_name in self.service_priority:
                    if service_name in self.services and service_name != "Fallback":
                        cached_result = self.cache.get(text, source_lang, target_lang, service_name)
                        if cached_result and cached_result.metadata.get("success", True):
                            break
            
            if cached_result:
                results.append(cached_result)
            else:
                results.append(None)  # Placeholder
                uncached_indices.append(i)
                uncached_texts.append(text)
        
        # Translate uncached texts, retrying only failed items with the next
        # configured provider. This keeps native provider batch calls while
        # preserving the manager's advertised service failover behavior.
        remaining_indices = list(uncached_indices)
        if remaining_indices:
            logger.info(f"Translating {len(remaining_indices)} uncached texts")

        for service_name in self.service_priority:
            if not remaining_indices or service_name == "Fallback":
                continue
            service = self.services.get(service_name)
            if service is None or not service.is_available():
                continue

            service_requests = [
                TranslationRequest(
                    text=texts[index],
                    source_lang=source_lang,
                    target_lang=target_lang,
                )
                for index in remaining_indices
            ]
            try:
                batch_results = service.translate_batch(service_requests)
                if len(batch_results) != len(service_requests):
                    raise TranslationError(
                        f"{service_name} returned {len(batch_results)} results "
                        f"for {len(service_requests)} requests"
                    )
            except Exception as exc:
                logger.error(f"{service_name} batch translation failed: {exc}")
                continue

            failed_indices = []
            for original_index, result in zip(remaining_indices, batch_results):
                if not result.metadata.get("success", True):
                    failed_indices.append(original_index)
                    continue

                result.translated_text = self.terminology.apply_terminology(
                    result.translated_text, source_lang, target_lang
                )
                if use_cache:
                    self.cache.store(result)
                results[original_index] = result
            remaining_indices = failed_indices

        # A passthrough is retained for backward compatibility, but is
        # explicitly machine-readable as a failed translation and is never
        # cached. Callers can surface configuration/network failures instead of
        # mistaking unchanged text for success.
        fallback = self.services.get("Fallback", FallbackTranslator())
        for index in remaining_indices:
            results[index] = fallback.translate_single(
                TranslationRequest(texts[index], source_lang, target_lang)
            )
        
        return results


# For backward compatibility
Translator = TranslationManager
