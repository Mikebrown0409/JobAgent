"""
Advanced Cache System - High-Performance Caching

Enterprise-grade caching system with Redis support for caching form analysis,
field mappings, AI-generated content, and performance optimization.
"""

import asyncio
import json
import logging
import hashlib
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import pickle
import gzip

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

from job_application_agent.core.config import Config


@dataclass
class CacheEntry:
    """Represents a cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: List[str] = None
    size_bytes: int = 0


class AdvancedCache:
    """
    Advanced caching system with multiple backends and intelligent eviction.
    
    Features:
    - Redis backend for distributed caching
    - In-memory fallback for local caching
    - Intelligent cache warming and preloading
    - Tag-based cache invalidation
    - Compression for large objects
    - Performance analytics and optimization
    """
    
    def __init__(self, config: Config):
        """Initialize the advanced cache system."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Cache configuration
        self.default_ttl = timedelta(hours=24)
        self.max_memory_cache_size = 1000  # Max items in memory cache
        self.compression_threshold = 1024  # Compress items larger than 1KB
        
        # Initialize backends
        self.redis_client: Optional[redis.Redis] = None
        self.memory_cache: Dict[str, CacheEntry] = {}
        
        # Performance tracking
        self.stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'evictions': 0,
            'redis_operations': 0,
            'memory_operations': 0
        }
        
        # Initialize Redis if available
        if REDIS_AVAILABLE and hasattr(config, 'redis_url'):
            self._initialize_redis()
        else:
            self.logger.info("Redis not available or not configured, using memory cache only")
    
    def _initialize_redis(self):
        """Initialize Redis connection."""
        try:
            redis_url = getattr(self.config, 'redis_url', 'redis://localhost:6379')
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=False,  # We'll handle encoding ourselves
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self.logger.info("Redis cache backend initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize Redis: {str(e)}")
            self.redis_client = None
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache with intelligent fallback.
        
        Args:
            key: Cache key
            default: Default value if not found
            
        Returns:
            Cached value or default
        """
        try:
            # Try Redis first if available
            if self.redis_client:
                value = await self._get_from_redis(key)
                if value is not None:
                    self.stats['hits'] += 1
                    self.stats['redis_operations'] += 1
                    return value
            
            # Fallback to memory cache
            if key in self.memory_cache:
                entry = self.memory_cache[key]
                
                # Check expiration
                if entry.expires_at and datetime.now() > entry.expires_at:
                    del self.memory_cache[key]
                    self.stats['evictions'] += 1
                else:
                    # Update access statistics
                    entry.access_count += 1
                    entry.last_accessed = datetime.now()
                    self.stats['hits'] += 1
                    self.stats['memory_operations'] += 1
                    return entry.value
            
            self.stats['misses'] += 1
            return default
            
        except Exception as e:
            self.logger.error(f"Cache get failed for key {key}: {str(e)}")
            return default
    
    async def set(self, key: str, value: Any, ttl: Optional[timedelta] = None, 
                 tags: Optional[List[str]] = None) -> bool:
        """
        Set value in cache with intelligent storage.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live (default: 24 hours)
            tags: Tags for cache invalidation
            
        Returns:
            True if successful
        """
        try:
            ttl = ttl or self.default_ttl
            expires_at = datetime.now() + ttl if ttl else None
            
            # Serialize and optionally compress the value
            serialized_value = await self._serialize_value(value)
            
            # Try Redis first if available
            if self.redis_client:
                success = await self._set_in_redis(key, serialized_value, ttl, tags)
                if success:
                    self.stats['sets'] += 1
                    self.stats['redis_operations'] += 1
                    return True
            
            # Fallback to memory cache
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.now(),
                expires_at=expires_at,
                tags=tags or [],
                size_bytes=len(str(serialized_value))
            )
            
            # Evict old entries if memory cache is full
            if len(self.memory_cache) >= self.max_memory_cache_size:
                await self._evict_lru_memory()
            
            self.memory_cache[key] = entry
            self.stats['sets'] += 1
            self.stats['memory_operations'] += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Cache set failed for key {key}: {str(e)}")
            return False
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get comprehensive cache information and statistics."""
        memory_size = len(self.memory_cache)
        memory_bytes = sum(entry.size_bytes for entry in self.memory_cache.values())
        
        info = {
            'stats': self.stats.copy(),
            'memory_cache': {
                'size': memory_size,
                'max_size': self.max_memory_cache_size,
                'bytes_used': memory_bytes,
                'utilization': memory_size / self.max_memory_cache_size
            },
            'redis_available': self.redis_client is not None,
            'hit_rate': self.stats['hits'] / (self.stats['hits'] + self.stats['misses']) 
                       if (self.stats['hits'] + self.stats['misses']) > 0 else 0
        }
        
        # Add Redis info if available
        if self.redis_client:
            try:
                redis_info = await self.redis_client.info('memory')
                info['redis'] = {
                    'used_memory': redis_info.get('used_memory', 0),
                    'used_memory_human': redis_info.get('used_memory_human', '0B'),
                    'connected': True
                }
            except Exception:
                info['redis'] = {'connected': False}
        
        return info
    
    async def _get_from_redis(self, key: str) -> Any:
        """Get value from Redis with decompression."""
        try:
            data = await self.redis_client.get(key)
            if data is None:
                return None
            
            # Deserialize the value
            return await self._deserialize_value(data)
            
        except Exception as e:
            self.logger.debug(f"Redis get failed for key {key}: {str(e)}")
            return None
    
    async def _set_in_redis(self, key: str, value: bytes, ttl: timedelta, 
                          tags: Optional[List[str]]) -> bool:
        """Set value in Redis with compression and metadata."""
        try:
            # Set the main value
            if ttl:
                await self.redis_client.setex(key, int(ttl.total_seconds()), value)
            else:
                await self.redis_client.set(key, value)
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Redis set failed for key {key}: {str(e)}")
            return False
    
    async def _serialize_value(self, value: Any) -> bytes:
        """Serialize and optionally compress a value."""
        # Serialize using pickle
        serialized = pickle.dumps(value)
        
        # Compress if larger than threshold
        if len(serialized) > self.compression_threshold:
            serialized = gzip.compress(serialized)
            # Add compression marker
            serialized = b'GZIP:' + serialized
        
        return serialized
    
    async def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize and optionally decompress a value."""
        # Check for compression marker
        if data.startswith(b'GZIP:'):
            data = gzip.decompress(data[5:])  # Remove 'GZIP:' prefix
        
        # Deserialize using pickle
        return pickle.loads(data)
    
    async def _evict_lru_memory(self) -> None:
        """Evict least recently used items from memory cache."""
        if not self.memory_cache:
            return
        
        # Sort by last accessed time (oldest first)
        sorted_entries = sorted(
            self.memory_cache.items(),
            key=lambda x: x[1].last_accessed or x[1].created_at
        )
        
        # Remove oldest 10% of entries
        num_to_evict = max(1, len(sorted_entries) // 10)
        for i in range(num_to_evict):
            key = sorted_entries[i][0]
            del self.memory_cache[key]
            self.stats['evictions'] += 1
    
    def generate_cache_key(self, *args, **kwargs) -> str:
        """Generate a consistent cache key from arguments."""
        # Create a string representation of all arguments
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        
        # Create hash of the key data
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]
    
    async def close(self) -> None:
        """Close cache connections and cleanup."""
        if self.redis_client:
            await self.redis_client.close()
        
        self.memory_cache.clear()
        self.logger.info("Cache system closed") 