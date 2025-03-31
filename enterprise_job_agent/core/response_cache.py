"""Caching system for LLM responses to minimize API calls."""

import json
import hashlib
import os
import time
import logging
from typing import Any, Dict, Optional, Union
import asyncio

logger = logging.getLogger(__name__)

class ResponseCache:
    """Cache for storing and retrieving API responses."""
    
    def __init__(self, cache_dir: str = ".cache", ttl: int = 3600):
        """
        Initialize the response cache.
        
        Args:
            cache_dir: Directory to store cache files
            ttl: Time-to-live for cache entries in seconds (default: 1 hour)
        """
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.memory_cache = {}
        self._ensure_cache_dir()
        logger.info(f"Response cache initialized with TTL {ttl}s")
        
    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
            logger.debug(f"Created cache directory: {self.cache_dir}")
            
    def _get_cache_key(self, prompt: str) -> str:
        """
        Generate a cache key from a prompt.
        
        Args:
            prompt: The prompt to generate a key for
            
        Returns:
            A hash string to use as the cache key
        """
        # Create a hash of the prompt for the cache key
        prompt_hash = hashlib.md5(prompt.encode('utf-8')).hexdigest()
        return prompt_hash
    
    def _get_cache_path(self, key: str) -> str:
        """
        Get the file path for a cache key.
        
        Args:
            key: The cache key
            
        Returns:
            Path to the cache file
        """
        return os.path.join(self.cache_dir, f"{key}.json")
    
    async def get(self, prompt: str) -> Optional[Any]:
        """
        Get a response from the cache if it exists and is not expired.
        
        Args:
            prompt: The prompt to get a cached response for
            
        Returns:
            The cached response or None if not found or expired
        """
        key = self._get_cache_key(prompt)
        
        # Check memory cache first
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if time.time() < entry["expires_at"]:
                logger.debug(f"Cache hit (memory): {key[:8]}...")
                return entry["response"]
            else:
                # Expired, remove from memory cache
                del self.memory_cache[key]
        
        # Check file cache
        cache_path = self._get_cache_path(key)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    entry = json.load(f)
                
                # Check if expired
                if time.time() < entry["expires_at"]:
                    # Add to memory cache for faster access next time
                    self.memory_cache[key] = entry
                    logger.debug(f"Cache hit (file): {key[:8]}...")
                    return entry["response"]
                else:
                    # Expired, remove cache file
                    os.remove(cache_path)
                    logger.debug(f"Removed expired cache: {key[:8]}...")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Invalid cache file {cache_path}: {e}")
                # Remove invalid cache file
                if os.path.exists(cache_path):
                    os.remove(cache_path)
        
        logger.debug(f"Cache miss: {key[:8]}...")
        return None
    
    async def store(self, prompt: str, response: Any, custom_ttl: Optional[int] = None) -> None:
        """
        Store a response in the cache.
        
        Args:
            prompt: The prompt the response is for
            response: The response to cache
            custom_ttl: Optional custom TTL in seconds
        """
        ttl = custom_ttl if custom_ttl is not None else self.ttl
        key = self._get_cache_key(prompt)
        expires_at = time.time() + ttl
        
        entry = {
            "prompt": prompt,
            "response": response,
            "cached_at": time.time(),
            "expires_at": expires_at
        }
        
        # Store in memory cache
        self.memory_cache[key] = entry
        
        # Store in file cache
        cache_path = self._get_cache_path(key)
        
        # Use asyncio to write to file so we don't block
        await asyncio.to_thread(self._write_cache_file, cache_path, entry)
        
        logger.debug(f"Stored in cache: {key[:8]}...")
    
    def _write_cache_file(self, cache_path: str, entry: Dict[str, Any]) -> None:
        """
        Write a cache entry to a file.
        
        Args:
            cache_path: Path to write the cache file to
            entry: The cache entry to write
        """
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to write cache file {cache_path}: {e}")
    
    async def invalidate(self, prompt: str) -> None:
        """
        Invalidate a cached response.
        
        Args:
            prompt: The prompt to invalidate
        """
        key = self._get_cache_key(prompt)
        
        # Remove from memory cache
        if key in self.memory_cache:
            del self.memory_cache[key]
        
        # Remove from file cache
        cache_path = self._get_cache_path(key)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception as e:
                logger.error(f"Failed to remove cache file {cache_path}: {e}")
                
        logger.debug(f"Invalidated cache: {key[:8]}...")
    
    async def clear(self) -> None:
        """Clear all cached responses."""
        # Clear memory cache
        self.memory_cache = {}
        
        # Clear file cache
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                try:
                    os.remove(os.path.join(self.cache_dir, filename))
                except Exception as e:
                    logger.error(f"Failed to remove cache file {filename}: {e}")
                    
        logger.info("Cache cleared") 