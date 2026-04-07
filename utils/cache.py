"""
缓存管理模块
"""
import time
from typing import Any, Optional, Dict
import hashlib


class Cache:
    """简单的内存缓存"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key not in self._cache:
            return None
        
        item = self._cache[key]
        
        # 检查是否过期
        if item['expires_at'] < time.time():
            del self._cache[key]
            return None
        
        return item['value']
    
    def set(self, key: str, value: Any, ttl: int = 300):
        """设置缓存"""
        self._cache[key] = {
            'value': value,
            'expires_at': time.time() + ttl
        }
    
    def delete(self, key: str):
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
    
    def cleanup(self):
        """清理过期缓存"""
        current_time = time.time()
        expired_keys = [
            key for key, item in self._cache.items()
            if item['expires_at'] < current_time
        ]
        
        for key in expired_keys:
            del self._cache[key]
    
    @staticmethod
    def generate_key(*args) -> str:
        """生成缓存键"""
        content = '|'.join(str(arg) for arg in args)
        return hashlib.md5(content.encode()).hexdigest()


# 全局缓存实例
cache = Cache()
