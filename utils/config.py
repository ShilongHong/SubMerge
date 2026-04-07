"""
配置文件管理模块
"""
import yaml
import os
from typing import Dict, Any, List
import re


class Config:
    """配置管理类"""
    
    def __init__(self, config_path: str = 'config/config.yaml'):
        """初始化配置"""
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            return self.get_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config if config else self.get_default_config()
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            'common': {
                'api_mode': False,
                'default_url': [],
                'exclude_remarks': [],
                'include_remarks': [],
                'cache_subscription': 300,
                'cache_config': 300
            },
            'node_pref': {
                'udp_flag': False,
                'tcp_fast_open_flag': False,
                'skip_cert_verify_flag': False,
                'sort_flag': False,
                'filter_deprecated_nodes': True,
                'rename_node': []
            },
            'emojis': {
                'add_emoji': True,
                'remove_old_emoji': True,
                'rules': []
            },
            'proxy_groups': {
                'custom_proxy_group': []
            },
            'server': {
                'host': '0.0.0.0',
                'port': 5000,
                'debug': True
            },
            'advanced': {
                'log_level': 'info',
                'max_concurrent_threads': 4,
                'enable_cache': True,
                'request_timeout': 30
            }
        }
    
    def get(self, *keys: str, default: Any = None) -> Any:
        """获取配置项"""
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value
    
    def get_exclude_remarks(self) -> List[str]:
        """获取排除规则"""
        return self.get('common', 'exclude_remarks', default=[])
    
    def get_include_remarks(self) -> List[str]:
        """获取包含规则"""
        return self.get('common', 'include_remarks', default=[])
    
    def get_rename_rules(self) -> List[Dict[str, str]]:
        """获取重命名规则"""
        return self.get('node_pref', 'rename_node', default=[])
    
    def get_emoji_rules(self) -> List[Dict[str, str]]:
        """获取 emoji 规则"""
        return self.get('emojis', 'rules', default=[])
    
    def should_add_emoji(self) -> bool:
        """是否添加 emoji"""
        return self.get('emojis', 'add_emoji', default=True)
    
    def should_remove_old_emoji(self) -> bool:
        """是否移除旧 emoji"""
        return self.get('emojis', 'remove_old_emoji', default=True)
    
    def get_custom_proxy_groups(self) -> List[Dict[str, Any]]:
        """获取自定义代理组"""
        return self.get('proxy_groups', 'custom_proxy_group', default=[])
    
    def get_cache_time(self, cache_type: str = 'subscription') -> int:
        """获取缓存时间"""
        key = f'cache_{cache_type}'
        return self.get('common', key, default=300)
    
    def get_request_timeout(self) -> int:
        """获取请求超时时间"""
        return self.get('advanced', 'request_timeout', default=30)


# 全局配置实例
config = Config()
