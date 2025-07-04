#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Translation module for video translation system.
Supports multiple translation APIs with caching, batch processing,
terminology management, and error recovery.
"""

import os
import logging
import json
import hashlib
import time
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union, Set
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TranslationCache:
    """
    Cache for translation results to avoid redundant API calls.
    Uses SQLite for persistent storage.
    """
    
    def __init__(self, cache_path: str = None, max_size: int = DEFAULT_CACHE_SIZE):
        """
        Initialize the translation cache.
        
        Args:
            cache_path: Path to cache file (if None, use in-memory cache)
            max_size: Maximum number of entries in cache
        """
        self.max_size = max_size
        
        # Determine cache path
        if cache_path is None:
            # User cache directory
            user_cache_dir = os.path.join(
                os.path.expanduser("~"),
                ".cache",
                "video_translator"
            )
            os.makedirs(user_cache_dir, exist_ok=True)
            self.cache_path = os.path.join(user_cache_dir, "translation_cache.db")
        else:
            self.cache_path = cache_path
            
        # Initialize the cache database
        self._init_db()
        
    def _init_db(self):
        """Initialize the SQLite database for caching."""
        # Allow connections across threads
        self.conn = sqlite3.connect(self.cache_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency and performance
        
        # Create cache table if it doesn't exist
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
        
        # Create index for faster lookups
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_translations_timestamp 
            ON translations(timestamp)
        """)
        
        self.conn.commit()
        
    def _generate_key(self, text: str, source_lang: str, target_lang: str, service: str) -> str:
        """
        Generate a unique cache key for the translation request.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name
            
        Returns:
            Cache key as a string
        """
        # Create a string combining all parameters
        key_str = f"{text}:{source_lang}:{target_lang}:{service}"
        
        # Generate MD5 hash as the key
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
        
    def get(self, text: str, source_lang: str, target_lang: str, 
            service: str) -> Optional[TranslationResult]:
        """
        Get translation from cache.
        
        Args:
            text: Text to lookup
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name
            
        Returns:
            TranslationResult object if found, None otherwise
        """
        key = self._generate_key(text, source_lang, target_lang, service)
        
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT original_text, translated_text, source_lang, target_lang, "
            "service, confidence, metadata FROM translations WHERE hash = ?", 
            (key,)
        )
        
        result = cursor.fetchone()
        if result:
            original, translated, src_lang, tgt_lang, svc, confidence, metadata_str = result
            
            # Update timestamp to mark as recently used
            cursor.execute(
                "UPDATE translations SET timestamp = ? WHERE hash = ?",
                (time.time(), key)
            )
            self.conn.commit()
            
            # Parse metadata if present
            if metadata_str:
                try:
                    metadata = json.loads(metadata_str)
                except json.JSONDecodeError:
                    metadata = {}
            else:
                metadata = {}
                
            # Return cached result
            return TranslationResult(
                original_text=original,
                translated_text=translated,
                source_lang=src_lang,
                target_lang=tgt_lang,
                confidence=confidence or 0.0,
                service=svc,
                metadata=metadata
            )
            
        return None
    
    def store(self, result: TranslationResult):
        """
        Store translation result in cache.
        
        Args:
            result: TranslationResult object to store
        """
        key = self._generate_key(
            result.original_text, 
            result.source_lang, 
            result.target_lang,
            result.service
        )
        
        # Serialize metadata
        metadata_str = json.dumps(result.metadata) if result.metadata else None
        
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO translations "
            "(hash, original_text, translated_text, source_lang, target_lang, "
            "service, timestamp, confidence, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                key, 
                result.original_text, 
                result.translated_text,
                result.source_lang,
                result.target_lang,
                result.service,
                time.time(),
                result.confidence,
                metadata_str
            )
        )
        
        self.conn.commit()
        
        # Check if cache needs pruning
        self._prune_if_needed()
    
    def _prune_if_needed(self):
        """Remove oldest entries if cache exceeds maximum size."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM translations")
        count = cursor.fetchone()[0]
        
        if count > self.max_size:
            # Calculate how many entries to remove
            to_remove = count - int(self.max_size * 0.8)  # Remove 20% more than needed
            
            # Delete oldest entries
            cursor.execute(
                "DELETE FROM translations WHERE hash IN "
                "(SELECT hash FROM translations ORDER BY timestamp ASC LIMIT ?)",
                (to_remove,)
            )
            self.conn.commit()
            logger.debug(f"Pruned {to_remove} entries from translation cache")
    
    def clear(self):
        """Clear all entries from the cache."""
        self.conn.execute("DELETE FROM translations")
        self.conn.commit()
        logger.info("Translation cache cleared")
    
    def close(self):
        """Close the database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
    
    def __del__(self):
        """Ensure database connection is closed on deletion."""
        self.close()


class TerminologyManager:
    """
    Manages terminology to ensure consistent translation of specific terms.
    """
    
    def __init__(self, terminology_file: str = None):
        """
        Initialize the terminology manager.
        
        Args:
            terminology_file: Path to JSON file with terminology mappings
        """
        self.terminology: Dict[str, Dict[str, str]] = {}
        
        if terminology_file and os.path.exists(terminology_file):
            try:
                with open(terminology_file, 'r', encoding='utf-8') as f:
                    self.terminology = json.load(f)
                logger.info(f"Loaded terminology file: {terminology_file}")
            except Exception as e:
                logger.error(f"Failed to load terminology file: {e}")
    
    def add_term(self, source_term: str, target_term: str, lang_pair: str):
        """
        Add a terminology entry.
        
        Args:
            source_term: Term in source language
            target_term: Term in target language
            lang_pair: Language pair code (e.g., "en-de")
        """
        if lang_pair not in self.terminology:
            self.terminology[lang_pair] = {}
            
        self.terminology[lang_pair][source_term] = target_term
        logger.debug(f"Added terminology: {source_term} → {target_term} ({lang_pair})")
    
    def get_translation(self, term: str, lang_pair: str) -> Optional[str]:
        """
        Get translation for a specific term.
        
        Args:
            term: Term to translate
            lang_pair: Language pair code
            
        Returns:
            Translated term if found, None otherwise
        """
        if lang_pair in self.terminology and term in self.terminology[lang_pair]:
            return self.terminology[lang_pair][term]
        return None
    
    def apply_terminology(self, text: str, translated_text: str, 
                         source_lang: str, target_lang: str) -> str:
        """
        Apply terminology to ensure consistent translation.
        
        Args:
            text: Original text
            translated_text: Translated text from API
            source_lang: Source language code
            target_lang: Target language code
            
        Returns:
            Updated translation with consistent terminology
        """
        lang_pair = f"{source_lang}-{target_lang}"
        
        # If we don't have terminology for this language pair, return as is
        if lang_pair not in self.terminology:
            return translated_text
            
        result = translated_text
        
        # Apply each term in the terminology
        for source_term, target_term in self.terminology[lang_pair].items():
            # Skip if source term is not in original text
            if source_term.lower() not in text.lower():
                continue
                
            # Create regex pattern that preserves case sensitivity where possible
            pattern = re.compile(re.escape(target_term), re.IGNORECASE)
            result = pattern.sub(target_term, result)
            
        return result
    
    def save_to_file(self, file_path: str):
        """
        Save terminology to a file.
        
        Args:
            file_path: Path to save terminology
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.terminology, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved terminology to: {file_path}")
        except Exception as e:
            logger.error(f"Failed to save terminology file: {e}")


class TranslatorInterface(ABC):
    """Abstract base class for translation service implementations."""
    
    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str, 
                 **kwargs) -> TranslationResult:
        """
        Translate a single text.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional provider-specific parameters
            
        Returns:
            TranslationResult with the translation
        """
        pass
    
    @abstractmethod
    def batch_translate(self, texts: List[str], source_lang: str, target_lang: str,
                       **kwargs) -> List[TranslationResult]:
        """
        Translate a batch of texts.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional provider-specific parameters
            
        Returns:
            List of TranslationResult objects
        """
        pass
    
    @abstractmethod
    def detect_language(self, text: str) -> Dict[str, float]:
        """
        Detect the language of a text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        pass


class DeepLTranslator(TranslatorInterface):
    """DeepL API translator implementation."""
    
    # Language code mappings (DeepL uses different codes than ISO)
    LANGUAGE_MAP = {
        "en": "EN",  # English
        "de": "DE",  # German
        "fr": "FR",  # French
        "es": "ES",  # Spanish
        "it": "IT",  # Italian
        "nl": "NL",  # Dutch
        "pl": "PL",  # Polish
        "pt": "PT",  # Portuguese
        "ru": "RU",  # Russian
        "ja": "JA",  # Japanese
        "zh": "ZH",  # Chinese
        "ko": "KO",  # Korean
    }
    
    def __init__(self, api_key: str, free_api: bool = False):
        """
        Initialize DeepL translator.
        
        Args:
            api_key: DeepL API key
            free_api: Whether to use the free API (api-free.deepl.com)
        """
        self.api_key = api_key
        # 保存 free_api 标志并构建对应的 endpoint
        self.free_api = free_api
        self.base_url = "https://api-free.deepl.com/v2" if self.free_api else "https://api.deepl.com/v2"
        
        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=DEFAULT_RETRY_COUNT,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        # Validate API key on initialization
        self._validate_api_key()
    
    def _validate_api_key(self):
        """Validate the API key by checking account information."""
        try:
            # 初次验证
            url = f"{self.base_url}/usage"
            response = self.session.get(
                url,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                timeout=DEFAULT_TIMEOUT
            )
            if response.status_code == 200:
                usage_data = response.json()
                logger.info(f"DeepL API connected. "
                           f"Character usage: {usage_data.get('character_count', 0)}/"
                           f"{usage_data.get('character_limit', 0)}")
            else:
                # 如果检测到付费 endpoint 错误，尝试切换到免费 endpoint 并重试
                if response.status_code == 403 and not self.free_api and 'Wrong endpoint' in response.text:
                    logger.info("Detected wrong endpoint error, switching to DeepL free API endpoint and retrying.")
                    self.free_api = True
                    self.base_url = "https://api-free.deepl.com/v2"
                    # 重试验证
                    retry_resp = self.session.get(
                        f"{self.base_url}/usage",
                        headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                        timeout=DEFAULT_TIMEOUT
                    )
                    if retry_resp.status_code == 200:
                        usage_data = retry_resp.json()
                        logger.info(f"DeepL free API connected. Character usage: {usage_data.get('character_count',0)}/"
                                    f"{usage_data.get('character_limit',0)}")
                    else:
                        logger.warning(f"DeepL free endpoint validation failed: {retry_resp.status_code} {retry_resp.text}")
                else:
                    logger.warning(f"DeepL API key validation failed: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error validating DeepL API key: {e}")
    
    def _map_language_code(self, code: str, is_source: bool = True) -> str:
        """
        Map ISO language code to DeepL language code.
        
        Args:
            code: ISO language code
            is_source: Whether this is a source language
            
        Returns:
            DeepL language code
        """
        base_code = code.split('-')[0].lower()  # Extract base language code
        
        if base_code in self.LANGUAGE_MAP:
            mapped_code = self.LANGUAGE_MAP[base_code]
            
            # For target languages, we can specify regional variants
            if not is_source and '-' in code:
                region = code.split('-')[1].upper()
                
                # Add regional variants for supported languages
                if base_code == "en" and region in ("US", "GB"):
                    mapped_code = f"{mapped_code}-{region}"
                elif base_code == "pt" and region == "BR":
                    mapped_code = "PT-BR"
                elif base_code == "zh" and region == "CN":
                    mapped_code = "ZH"  # DeepL only supports simplified Chinese
                    
            return mapped_code
            
        # If no mapping found, use original code
        return code.upper()
    
    def translate(self, text: str, source_lang: str, target_lang: str, 
                 **kwargs) -> TranslationResult:
        """
        Translate a single text using DeepL API.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters:
                      - formality: "default", "more", "less"
                      - preserve_formatting: bool
                      
        Returns:
            TranslationResult with the translation
            
        Raises:
            ValueError: If text is empty
            RuntimeError: If translation fails
        """
        if not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                service="deepl"
            )
            
        # Map language codes to DeepL format
        source_lang_mapped = self._map_language_code(source_lang, is_source=True) if source_lang != "auto" else "auto"
        target_lang_mapped = self._map_language_code(target_lang, is_source=False)
        
        # Prepare parameters
        params = {
            "text": text,
            "target_lang": target_lang_mapped,
        }
        
        # Add source language if not auto-detect
        if source_lang != "auto":
            params["source_lang"] = source_lang_mapped
            
        # Add optional parameters
        if "formality" in kwargs:
            params["formality"] = kwargs["formality"]
            
        if kwargs.get("preserve_formatting", False):
            params["preserve_formatting"] = "1"
            
        try:
            url = f"{self.base_url}/translate"
            response = self.session.post(
                url,
                data=params,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"DeepL API error: {response.status_code} {response.text}")
                
            result = response.json()
            translations = result.get("translations", [])
            
            if not translations:
                raise RuntimeError("No translation returned from DeepL API")
                
            # Get detected source language if auto-detection was used
            detected_source_lang = source_lang
            if source_lang == "auto":
                detected_source_lang = translations[0].get("detected_source_language", "").lower()
                
            return TranslationResult(
                original_text=text,
                translated_text=translations[0]["text"],
                source_lang=detected_source_lang,
                target_lang=target_lang,
                confidence=1.0,  # DeepL doesn't provide confidence scores
                service="deepl",
                metadata={
                    "provider": "deepl",
                    "detected_source_language": detected_source_lang
                }
            )
            
        except Exception as e:
            logger.error(f"DeepL translation error: {str(e)}")
            raise RuntimeError(f"Translation failed: {str(e)}")
    
    def batch_translate(self, texts: List[str], source_lang: str, target_lang: str,
                       **kwargs) -> List[TranslationResult]:
        """
        Translate a batch of texts using DeepL API.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters
            
        Returns:
            List of TranslationResult objects
            
        Note:
            DeepL API supports batch translation natively
        """
        if not texts:
            return []
            
        # Filter out empty texts but remember their positions
        non_empty_texts = []
        indices = []
        
        for i, text in enumerate(texts):
            if text.strip():
                non_empty_texts.append(text)
                indices.append(i)
                
        if not non_empty_texts:
            return [TranslationResult(
                original_text="",
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                service="deepl"
            ) for _ in texts]
        
        # Map language codes
        source_lang_mapped = self._map_language_code(source_lang, is_source=True) if source_lang != "auto" else "auto"
        target_lang_mapped = self._map_language_code(target_lang, is_source=False)
        
        # Prepare parameters (DeepL expects multiple 'text' parameters)
        params = {
            "target_lang": target_lang_mapped,
        }
        
        # Add source language if not auto-detect
        if source_lang != "auto":
            params["source_lang"] = source_lang_mapped
            
        # Add optional parameters
        if "formality" in kwargs:
            params["formality"] = kwargs["formality"]
            
        if kwargs.get("preserve_formatting", False):
            params["preserve_formatting"] = "1"
        
        # Add texts as multiple 'text' parameters
        for text in non_empty_texts:
            if "text" not in params:
                params["text"] = [text]
            else:
                params["text"].append(text)
                
        try:
            url = f"{self.base_url}/translate"
            response = self.session.post(
                url,
                data=params,
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"DeepL API error: {response.status_code} {response.text}")
                
            result = response.json()
            translations = result.get("translations", [])
            
            if len(translations) != len(non_empty_texts):
                raise RuntimeError("Number of translations doesn't match input texts")
                
            # Create results list with empty slots for all texts
            results = [None] * len(texts)
            
            # Fill in translations for non-empty texts
            for i, (idx, translation) in enumerate(zip(indices, translations)):
                # Get detected source language if auto-detection was used
                detected_source_lang = source_lang
                if source_lang == "auto":
                    detected_source_lang = translation.get("detected_source_language", "").lower()
                    
                results[idx] = TranslationResult(
                    original_text=texts[idx],
                    translated_text=translation["text"],
                    source_lang=detected_source_lang,
                    target_lang=target_lang,
                    confidence=1.0,
                    service="deepl",
                    metadata={
                        "provider": "deepl",
                        "detected_source_language": detected_source_lang
                    }
                )
            
            # Fill in empty results
            for i in range(len(texts)):
                if results[i] is None:
                    results[i] = TranslationResult(
                        original_text=texts[i],
                        translated_text="",
                        source_lang=source_lang,
                        target_lang=target_lang,
                        confidence=1.0,
                        service="deepl"
                    )
                    
            return results
            
        except Exception as e:
            logger.error(f"DeepL batch translation error: {str(e)}")
            raise RuntimeError(f"Batch translation failed: {str(e)}")
    
    def detect_language(self, text: str) -> Dict[str, float]:
        """
        Detect the language of a text using DeepL.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        try:
            # DeepL doesn't have a dedicated language detection endpoint
            # We'll use the translation endpoint with auto-detection
            url = f"{self.base_url}/translate"
            response = self.session.post(
                url,
                data={
                    "text": text,
                    "target_lang": "EN"  # Use English as target language
                },
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"DeepL API error: {response.status_code} {response.text}")
                
            result = response.json()
            translations = result.get("translations", [])
            
            if not translations:
                return {}
                
            detected_lang = translations[0].get("detected_source_language", "").lower()
            
            # Return with confidence 1.0 since DeepL doesn't provide confidence scores
            return {detected_lang: 1.0}
            
        except Exception as e:
            logger.error(f"DeepL language detection error: {str(e)}")
            return {}


class OpenAITranslator(TranslatorInterface):
    """OpenAI API translator implementation using GPT models."""
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo"):
        """
        Initialize OpenAI translator.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (e.g., "gpt-3.5-turbo", "gpt-4")
        """
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"
        
        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=DEFAULT_RETRY_COUNT,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        # Create language name mapping for better prompts
        self.language_names = {
            "en": "English",
            "zh": "Chinese",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "ja": "Japanese",
            "ru": "Russian",
            "pt": "Portuguese",
            "it": "Italian",
            "ko": "Korean",
            "ar": "Arabic",
            "tr": "Turkish",
            "vi": "Vietnamese",
            "pl": "Polish",
            "nl": "Dutch",
            "th": "Thai",
            "id": "Indonesian",
            "sv": "Swedish",
            "cs": "Czech",
            "fi": "Finnish",
            "el": "Greek",
            "uk": "Ukrainian",
        }
    
    def _get_language_name(self, code: str) -> str:
        """Get full language name from code."""
        base_code = code.split('-')[0].lower()
        return self.language_names.get(base_code, code)
    
    def translate(self, text: str, source_lang: str, target_lang: str, 
                 **kwargs) -> TranslationResult:
        """
        Translate a single text using OpenAI API.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters:
                      - temperature: float (0.0-2.0)
                      - preserve_formatting: bool
                      - context: str (additional context for translation)
                      
        Returns:
            TranslationResult with the translation
            
        Raises:
            ValueError: If text is empty
            RuntimeError: If translation fails
        """
        if not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                service="openai"
            )
            
        # Determine language names for better prompting
        source_name = self._get_language_name(source_lang) if source_lang != "auto" else "the source language"
        target_name = self._get_language_name(target_lang)
        
        # Prepare system message with instructions
        system_message = (
            f"You are a professional translator. Translate the text from {source_name} to {target_name}. "
            f"Maintain the original meaning, tone, and style. "
        )
        
        # Add formatting instruction if requested
        if kwargs.get("preserve_formatting", True):
            system_message += "Preserve the original formatting including line breaks and punctuation. "
        
        # Add context if provided
        context = kwargs.get("context", "")
        if context:
            system_message += f"Context for the translation: {context}. "
        
        # Prepare messages
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": text}
        ]
        
        # Set parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),  # Lower temperature for more consistent translations
            "max_tokens": min(4096, len(text) * 2),  # Estimate max tokens needed
        }
        
        try:
            url = f"{self.base_url}/chat/completions"
            response = self.session.post(
                url,
                json=params,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=DEFAULT_TIMEOUT * 2  # Longer timeout for GPT models
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            if not result.get("choices"):
                raise RuntimeError("No translation returned from OpenAI API")
                
            translated_text = result["choices"][0]["message"]["content"].strip()
            
            return TranslationResult(
                original_text=text,
                translated_text=translated_text,
                source_lang=source_lang,
                target_lang=target_lang,
                confidence=0.9,  # Arbitrary confidence for GPT
                service="openai",
                metadata={
                    "provider": "openai",
                    "model": self.model,
                    "usage": result.get("usage", {})
                }
            )
            
        except Exception as e:
            logger.error(f"OpenAI translation error: {str(e)}")
            raise RuntimeError(f"Translation failed: {str(e)}")
    
    def batch_translate(self, texts: List[str], source_lang: str, target_lang: str,
                       **kwargs) -> List[TranslationResult]:
        """
        Translate a batch of texts using OpenAI API.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters
            
        Returns:
            List of TranslationResult objects
        """
        if not texts:
            return []
            
        # For smaller batches, OpenAI can handle multiple texts in a single API call
        if len(texts) <= 5 and sum(len(t) for t in texts) < 1000:
            return self._batch_translate_single_call(texts, source_lang, target_lang, **kwargs)
        
        # For larger batches, use parallel requests
        return self._batch_translate_parallel(texts, source_lang, target_lang, **kwargs)
    
    def _batch_translate_single_call(self, texts: List[str], source_lang: str, 
                                   target_lang: str, **kwargs) -> List[TranslationResult]:
        """Translate multiple texts in a single API call."""
        # Determine language names for better prompting
        source_name = self._get_language_name(source_lang) if source_lang != "auto" else "the source language"
        target_name = self._get_language_name(target_lang)
        
        # Prepare system message
        system_message = (
            f"You are a professional translator. Translate the following texts from {source_name} to {target_name}. "
            f"Return the translations as a JSON array of strings, maintaining the exact same order as the input. "
            f"Only include the translated texts in the array, no additional information."
        )
        
        # Format input texts as a numbered list
        input_content = "Translate the following texts:\n\n"
        for i, text in enumerate(texts):
            input_content += f"{i+1}. {text}\n\n"
            
        # Prepare messages
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": input_content}
        ]
        
        # Set parameters
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": min(4096, sum(len(t) for t in texts) * 2),
            "response_format": {"type": "json_object"}
        }
        
        try:
            url = f"{self.base_url}/chat/completions"
            response = self.session.post(
                url,
                json=params,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=DEFAULT_TIMEOUT * 2
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            if not result.get("choices"):
                raise RuntimeError("No translation returned from OpenAI API")
                
            # Parse JSON response
            content = result["choices"][0]["message"]["content"].strip()
            try:
                translations = json.loads(content).get("translations", [])
                
                # Ensure we have the right number of translations
                if len(translations) != len(texts):
                    raise ValueError(f"Expected {len(texts)} translations, got {len(translations)}")
                    
                return [
                    TranslationResult(
                        original_text=orig,
                        translated_text=trans,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        confidence=0.9,
                        service="openai",
                        metadata={
                            "provider": "openai",
                            "model": self.model,
                            "batch_size": len(texts)
                        }
                    )
                    for orig, trans in zip(texts, translations)
                ]
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Error parsing OpenAI batch translation response: {e}")
                raise RuntimeError(f"Failed to parse batch translation response: {e}")
                
        except Exception as e:
            logger.error(f"OpenAI batch translation error: {str(e)}")
            raise RuntimeError(f"Batch translation failed: {str(e)}")
    
    def _batch_translate_parallel(self, texts: List[str], source_lang: str,
                                target_lang: str, **kwargs) -> List[TranslationResult]:
        """Translate batch of texts using parallel API calls."""
        results = [None] * len(texts)
        
        # Process in smaller batches if texts are short
        if max(len(t) for t in texts) < 200:
            batch_size = min(5, len(texts))
            batches = [texts[i:i+batch_size] for i in range(0, len(texts), batch_size)]
            
            with ThreadPoolExecutor(max_workers=min(5, len(batches))) as executor:
                future_to_batch = {
                    executor.submit(
                        self._batch_translate_single_call, 
                        batch, source_lang, target_lang, **kwargs
                    ): (i, len(batch)) 
                    for i, batch in enumerate(batches)
                }
                
                for future in as_completed(future_to_batch):
                    batch_idx, batch_len = future_to_batch[future]
                    try:
                        batch_results = future.result()
                        start_idx = batch_idx * batch_size
                        for j, result in enumerate(batch_results):
                            results[start_idx + j] = result
                    except Exception as e:
                        logger.error(f"Error in batch {batch_idx}: {e}")
                        # Fill in empty results for failed batch
                        for j in range(batch_len):
                            idx = batch_idx * batch_size + j
                            if idx < len(results):
                                results[idx] = TranslationResult(
                                    original_text=texts[idx],
                                    translated_text="",
                                    source_lang=source_lang,
                                    target_lang=target_lang,
                                    confidence=0,
                                    service="openai",
                                    metadata={"error": str(e)}
                                )
        else:
            # For longer texts, use single requests
            with ThreadPoolExecutor(max_workers=5) as executor:
                future_to_idx = {
                    executor.submit(self.translate, text, source_lang, target_lang, **kwargs): i
                    for i, text in enumerate(texts)
                }
                
                for future in as_completed(future_to_idx):
                    idx = future_to_idx[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        logger.error(f"Error translating text {idx}: {e}")
                        results[idx] = TranslationResult(
                            original_text=texts[idx],
                            translated_text="",
                            source_lang=source_lang,
                            target_lang=target_lang,
                            confidence=0,
                            service="openai",
                            metadata={"error": str(e)}
                        )
        
        return results
    
    def detect_language(self, text: str) -> Dict[str, float]:
        """
        Detect the language of a text using OpenAI.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        if not text.strip():
            return {}
            
        try:
            # Use a simple prompt for language detection
            messages = [
                {"role": "system", "content": (
                    "Identify the language of the following text. "
                    "Respond with only the ISO 639-1 language code (e.g., 'en' for English). "
                    "If you're uncertain, provide your best guess."
                )},
                {"role": "user", "content": text[:1000]}  # Limit to 1000 chars
            ]
            
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 10,  # We only need a short response
            }
            
            url = f"{self.base_url}/chat/completions"
            response = self.session.post(
                url,
                json=params,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            if not result.get("choices"):
                return {}
                
            # Extract the language code from the response
            content = result["choices"][0]["message"]["content"].strip().lower()
            
            # Extract just the language code if there's additional text
            match = re.search(r'\b[a-z]{2}(-[a-z]{2})?\b', content)
            if match:
                lang_code = match.group(0)
                return {lang_code: 0.9}  # Arbitrary confidence
            else:
                return {}
                
        except Exception as e:
            logger.error(f"OpenAI language detection error: {str(e)}")
            return {}


class GoogleTranslator(TranslatorInterface):
    """Google Cloud Translation API implementation."""
    
    def __init__(self, api_key: str):
        """
        Initialize Google translator.
        
        Args:
            api_key: Google Cloud API key
        """
        self.api_key = api_key
        self.base_url = "https://translation.googleapis.com/language/translate/v2"
        
        # Set up session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=DEFAULT_RETRY_COUNT,
            backoff_factor=DEFAULT_BACKOFF_FACTOR,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
    
    def translate(self, text: str, source_lang: str, target_lang: str, 
                 **kwargs) -> TranslationResult:
        """
        Translate a single text using Google Cloud Translation API.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters:
                      - format: "text" or "html"
                      
        Returns:
            TranslationResult with the translation
        """
        if not text.strip():
            return TranslationResult(
                original_text=text,
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                service="google"
            )
            
        # Map "auto" to empty string for Google API
        source_lang_param = "" if source_lang == "auto" else source_lang
        
        # Prepare parameters
        params = {
            "key": self.api_key,
            "q": text,
            "target": target_lang,
            "format": kwargs.get("format", "text")
        }
        
        # Add source language if not auto-detect
        if source_lang_param:
            params["source"] = source_lang_param
            
        try:
            response = self.session.post(
                self.base_url,
                json=params,
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            translations = result.get("data", {}).get("translations", [])
            
            if not translations:
                raise RuntimeError("No translation returned from Google API")
                
            # Get detected source language if auto-detection was used
            detected_source_lang = translations[0].get("detectedSourceLanguage", source_lang)
            
            return TranslationResult(
                original_text=text,
                translated_text=translations[0]["translatedText"],
                source_lang=detected_source_lang,
                target_lang=target_lang,
                confidence=1.0,  # Google doesn't provide confidence scores
                service="google",
                metadata={
                    "provider": "google",
                    "detected_source_language": detected_source_lang
                }
            )
            
        except Exception as e:
            logger.error(f"Google translation error: {str(e)}")
            raise RuntimeError(f"Translation failed: {str(e)}")
    
    def batch_translate(self, texts: List[str], source_lang: str, target_lang: str,
                       **kwargs) -> List[TranslationResult]:
        """
        Translate a batch of texts using Google Cloud Translation API.
        
        Args:
            texts: List of texts to translate
            source_lang: Source language code
            target_lang: Target language code
            **kwargs: Additional parameters
            
        Returns:
            List of TranslationResult objects
        """
        if not texts:
            return []
            
        # Filter out empty texts but remember their positions
        non_empty_texts = []
        indices = []
        
        for i, text in enumerate(texts):
            if text.strip():
                non_empty_texts.append(text)
                indices.append(i)
                
        if not non_empty_texts:
            return [TranslationResult(
                original_text="",
                translated_text="",
                source_lang=source_lang,
                target_lang=target_lang,
                service="google"
            ) for _ in texts]
        
        # Map "auto" to empty string for Google API
        source_lang_param = "" if source_lang == "auto" else source_lang
        
        # Prepare parameters
        params = {
            "key": self.api_key,
            "q": non_empty_texts,
            "target": target_lang,
            "format": kwargs.get("format", "text")
        }
        
        # Add source language if not auto-detect
        if source_lang_param:
            params["source"] = source_lang_param
            
        try:
            response = self.session.post(
                self.base_url,
                json=params,
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            translations = result.get("data", {}).get("translations", [])
            
            if len(translations) != len(non_empty_texts):
                raise RuntimeError("Number of translations doesn't match input texts")
                
            # Create results list with empty slots for all texts
            results = [None] * len(texts)
            
            # Fill in translations for non-empty texts
            for i, (idx, translation) in enumerate(zip(indices, translations)):
                # Get detected source language if auto-detection was used
                detected_source_lang = translation.get("detectedSourceLanguage", source_lang)
                
                results[idx] = TranslationResult(
                    original_text=texts[idx],
                    translated_text=translation["translatedText"],
                    source_lang=detected_source_lang,
                    target_lang=target_lang,
                    confidence=1.0,
                    service="google",
                    metadata={
                        "provider": "google",
                        "detected_source_language": detected_source_lang
                    }
                )
            
            # Fill in empty results
            for i in range(len(texts)):
                if results[i] is None:
                    results[i] = TranslationResult(
                        original_text=texts[i],
                        translated_text="",
                        source_lang=source_lang,
                        target_lang=target_lang,
                        confidence=1.0,
                        service="google"
                    )
                    
            return results
            
        except Exception as e:
            logger.error(f"Google batch translation error: {str(e)}")
            raise RuntimeError(f"Batch translation failed: {str(e)}")
    
    def detect_language(self, text: str) -> Dict[str, float]:
        """
        Detect the language of a text using Google Cloud Translation API.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        if not text.strip():
            return {}
            
        try:
            url = f"https://translation.googleapis.com/language/translate/v2/detect"
            response = self.session.post(
                url,
                json={
                    "key": self.api_key,
                    "q": text[:1000]  # Limit to 1000 chars
                },
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code != 200:
                raise RuntimeError(f"Google API error: {response.status_code} {response.text}")
                
            result = response.json()
            
            detections = result.get("data", {}).get("detections", [])
            
            if not detections or not detections[0]:
                return {}
                
            # Get all detections with confidence scores
            lang_scores = {}
            for detection in detections[0]:
                lang_code = detection["language"]
                confidence = detection.get("confidence", 0.0)
                lang_scores[lang_code] = confidence
                
            return lang_scores
            
        except Exception as e:
            logger.error(f"Google language detection error: {str(e)}")
            return {}


class Translator:
    """
    Main translator class that manages different translation services,
    caching, batch processing, and error recovery.
    """
    
    def __init__(self, primary_service: str = "openai", 
                fallback_services: List[str] = None,
                api_keys: Dict[str, str] = None,
                cache_path: str = None):
        """
        Initialize the translator.
        
        Args:
            primary_service: Primary translation service to use
            fallback_services: List of fallback services if primary fails
            api_keys: Dictionary mapping service names to API keys
            cache_path: Path to cache file
        """
        # 统一使用小写服务名称
        self.primary_service = (primary_service or "").lower()
        self.fallback_services = [s.lower() for s in (fallback_services or [])]
        self.api_keys = api_keys or {}

        logger.debug(f"初始化翻译器: primary={self.primary_service}, api_keys={list(self.api_keys.keys())}")
        
        # Initialize translation services
        self.services = {}
        self._init_services()
        
        # Initialize cache
        self.cache = TranslationCache(cache_path)
        
        # Initialize terminology manager
        self.terminology = TerminologyManager()
    
    def _init_services(self):
        """Initialize available translation services."""
        # 添加更详细的调试信息
        logger.debug(f"初始化翻译服务，可用的API键: {list(self.api_keys.keys())}")
        logger.debug(f"检查是否有deepl键: {'deepl' in self.api_keys}")
        logger.debug(f"检查是否有DeepL键: {'DeepL' in self.api_keys}")
        
        if "deepl" in self.api_keys:
            logger.debug(f"deepl API键长度: {len(self.api_keys['deepl'])}")
        if "DeepL" in self.api_keys:
            logger.debug(f"DeepL API键长度: {len(self.api_keys['DeepL'])}")

        """Initialize available translation services."""
        # Create OpenAI service if API key is provided
        if "openai" in self.api_keys or "OpenAI" in self.api_keys:
            try:
                api_key = self.api_keys.get("openai") or self.api_keys.get("OpenAI")
                self.services["openai"] = OpenAITranslator(
                    api_key=api_key,
                    model=self.api_keys.get("openai_model", "gpt-3.5-turbo")
                )
                logger.info("Initialized OpenAI translator service")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI translator: {e}")
                
        # Create DeepL service if API key is provided
        if "deepl" in self.api_keys or "DeepL" in self.api_keys:
            try:
                api_key = self.api_keys.get("deepl") or self.api_keys.get("DeepL")
                self.services["deepl"] = DeepLTranslator(
                    api_key=api_key,
                    free_api=self.api_keys.get("deepl_free", False)
                )
                logger.info("Initialized DeepL translator service")
            except Exception as e:
                logger.error(f"Failed to initialize DeepL translator: {e}")
                
        # Create Google service if API key is provided
        if "google" in self.api_keys or "Google" in self.api_keys:
            try:
                api_key = self.api_keys.get("google") or self.api_keys.get("Google")
                self.services["google"] = GoogleTranslator(
                    api_key=api_key
                )
                logger.info("Initialized Google translator service")
            except Exception as e:
                logger.error(f"Failed to initialize Google translator: {e}")
    
    def add_service(self, name: str, service: TranslatorInterface):
        """
        Add a custom translation service.
        
        Args:
            name: Service name
            service: TranslatorInterface implementation
        """
        self.services[name] = service
    
    def _get_service(self, service_name: str = None) -> Optional[TranslatorInterface]:
        """
        Get a translation service by name.
        
        Args:
            service_name: Service name (if None, use primary)
            
        Returns:
            TranslatorInterface implementation or None if not available
        """
        # 统一查找小写服务名称
        name = (service_name or self.primary_service).lower()
        service = self.services.get(name)
        if not service:
            logger.warning(f"Translation service not found: {name}")
        return service
    
    def translate(self, text: str, source_lang: str, target_lang: str, 
                 service: str = None, use_cache: bool = True,
                 apply_terminology: bool = True, **kwargs) -> TranslationResult:
        """
        Translate a single text.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code
            service: Translation service name (if None, use primary service)
            use_cache: Whether to use cached translation if available
            apply_terminology: Whether to apply terminology management
            **kwargs: Additional parameters for the translation service
            
        Returns:
            TranslationResult with the translation
        """
        # Check cache first
        if use_cache:
            cached_result = self.cache.get(text, source_lang, target_lang, service or self.primary_service)
            if cached_result:
                logger.info(f"Cache hit for translation: {text[:50]}...")
                return cached_result
        
        # Determine service
        service_name = service or self.primary_service
        service_obj = self._get_service(service_name)
        if not service_obj:
            raise RuntimeError(f"Translation service not available: {service_name}")
        
        try:
            # Perform translation
            result = service_obj.translate(text, source_lang, target_lang, **kwargs)
            
            # Apply terminology if needed
            if apply_terminology:
                result.translated_text = self.terminology.apply_terminology(
                    result.original_text, result.translated_text, result.source_lang, result.target_lang)
            
            # Store in cache
            if use_cache:
                self.cache.store(result)
            
            return result
        
        except Exception as e:
            logger.error(f"Translation failed with service '{service_name}': {e}")
            # Try fallback services
            for fallback in self.fallback_services:
                fallback_service = self._get_service(fallback)
                if fallback_service:
                    try:
                        logger.info(f"Trying fallback service: {fallback}")
                        result = fallback_service.translate(text, source_lang, target_lang, **kwargs)
                        
                        # Apply terminology if needed
                        if apply_terminology:
                            result.translated_text = self.terminology.apply_terminology(
                                result.original_text, result.translated_text, result.source_lang, result.target_lang)
                        
                        # Store in cache
                        if use_cache:
                            self.cache.store(result)
                        
                        return result
                    except Exception as e:
                        logger.error(f"Fallback translation failed with service '{fallback}': {e}")
        
        raise RuntimeError(f"Translation failed for text: {text}")
    
    def batch_translate(self, texts: List[str], source_lang: str, target_lang: str,
                        service: str = None, use_cache: bool = True,
                        apply_terminology: bool = True, **kwargs) -> List[TranslationResult]:
        """
        Batch translate a list of texts using the specified service.
        If the underlying service supports batch_translate, use it; otherwise fallback to individual calls.
        """
        if not texts:
            return []
        # Determine service
        service_name = service or self.primary_service
        service_obj = self._get_service(service_name)
        try:
            if hasattr(service_obj, 'batch_translate'):
                results = service_obj.batch_translate(texts, source_lang, target_lang, **kwargs)
            else:
                results = [service_obj.translate(t, source_lang, target_lang, **kwargs) for t in texts]
        except Exception as e:
            logger.error(f"Batch translation failed with service '{service_name}': {e}")
            # Fallback to individual translations
            results = [self.translate(t, source_lang, target_lang, service, use_cache, apply_terminology, **kwargs) for t in texts]
        # Apply terminology and cache if needed
        for res in results:
            if apply_terminology:
                res.translated_text = self.terminology.apply_terminology(
                    res.original_text, res.translated_text, res.source_lang, res.target_lang)
            if use_cache:
                self.cache.store(res)
        return results

    def clear_cache(self):
        """Clear the translation cache."""
        self.cache.clear()
    
    def set_terminology_file(self, file_path: str):
        """
        Set the terminology file for the manager.
        
        Args:
            file_path: Path to the JSON file with terminology mappings
        """
        self.terminology = TerminologyManager(file_path)
    
    def add_terminology(self, source_term: str, target_term: str, lang_pair: str):
        """
        Add a terminology entry.
        
        Args:
            source_term: Term in source language
            target_term: Term in target language
            lang_pair: Language pair code (e.g., "en-de")
        """
        self.terminology.add_term(source_term, target_term, lang_pair)
    
    def detect_language(self, text: str) -> Dict[str, float]:
        """
        Detect the language of a text using the primary translation service.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping language codes to confidence scores
        """
        service = self._get_service(self.primary_service)
        if service:
            return service.detect_language(text)
        return {}
