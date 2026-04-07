"""
节点处理工具模块
"""
import re
from typing import List, Dict, Any, Optional


def remove_emoji(text: str) -> str:
    """移除文本中的 emoji"""
    # Emoji 的 Unicode 范围
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号与象形文字
        "\U0001F680-\U0001F6FF"  # 交通与地图符号
        "\U0001F1E0-\U0001F1FF"  # 国旗
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text).strip()


def add_emoji_to_node(node_name: str, emoji_rules: List[Dict[str, str]]) -> str:
    """根据规则为节点名称添加 emoji"""
    for rule in emoji_rules:
        match_pattern = rule.get('match', '')
        emoji = rule.get('emoji', '')
        
        if not match_pattern or not emoji:
            continue
        
        try:
            if re.search(match_pattern, node_name, re.IGNORECASE):
                # 如果节点名称已经有这个 emoji，不重复添加
                if not node_name.startswith(emoji):
                    return f"{emoji} {node_name}"
        except re.error:
            continue
    
    return node_name


def rename_node(node_name: str, rename_rules: List[Dict[str, str]]) -> str:
    """根据规则重命名节点"""
    result = node_name
    
    for rule in rename_rules:
        match_pattern = rule.get('match', '')
        replace_pattern = rule.get('replace', '')
        
        if not match_pattern:
            continue
        
        try:
            result = re.sub(match_pattern, replace_pattern, result, flags=re.IGNORECASE)
        except re.error:
            continue
    
    return result


def filter_nodes(nodes: List[Dict[str, Any]], 
                include_patterns: List[str] = None,
                exclude_patterns: List[str] = None) -> List[Dict[str, Any]]:
    """过滤节点"""
    if not nodes:
        return []
    
    filtered_nodes = []
    
    for node in nodes:
        node_name = node.get('name', '')
        
        # 检查排除规则
        if exclude_patterns:
            should_exclude = False
            for pattern in exclude_patterns:
                try:
                    if re.search(pattern, node_name, re.IGNORECASE):
                        should_exclude = True
                        break
                except re.error:
                    continue
            
            if should_exclude:
                continue
        
        # 检查包含规则
        if include_patterns:
            should_include = False
            for pattern in include_patterns:
                try:
                    if re.search(pattern, node_name, re.IGNORECASE):
                        should_include = True
                        break
                except re.error:
                    continue
            
            if not should_include:
                continue
        
        filtered_nodes.append(node)
    
    return filtered_nodes


def process_node_name(node: Dict[str, Any],
                      remove_old_emoji: bool = True,
                      add_emoji: bool = True,
                      emoji_rules: List[Dict[str, str]] = None,
                      rename_rules: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """处理节点名称（移除旧 emoji、重命名、添加新 emoji）"""
    node_name = node.get('name', '')
    
    # 移除旧 emoji
    if remove_old_emoji:
        node_name = remove_emoji(node_name)
    
    # 应用重命名规则
    if rename_rules:
        node_name = rename_node(node_name, rename_rules)
    
    # 添加 emoji
    if add_emoji and emoji_rules:
        node_name = add_emoji_to_node(node_name, emoji_rules)
    
    # 更新节点名称
    node['name'] = node_name
    return node


def deduplicate_node_names(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """节点名称去重（重名的添加序号）"""
    name_count = {}
    result = []
    
    for node in nodes:
        original_name = node.get('name', '')
        
        if original_name in name_count:
            name_count[original_name] += 1
            node['name'] = f"{original_name}_{name_count[original_name]}"
        else:
            name_count[original_name] = 0
        
        result.append(node)
    
    return result


def sort_nodes(nodes: List[Dict[str, Any]], 
               sort_by: str = 'name',
               reverse: bool = False) -> List[Dict[str, Any]]:
    """节点排序"""
    try:
        return sorted(nodes, key=lambda x: x.get(sort_by, ''), reverse=reverse)
    except Exception:
        return nodes


def validate_proxy(proxy: Dict[str, Any], debug: bool = False) -> bool:
    """验证节点是否有效"""
    if not proxy:
        if debug:
            print(f"   [validate] 节点为空")
        return False
    
    # 必须有名称
    if not proxy.get('name'):
        if debug:
            print(f"   [validate] 节点无名称: {proxy}")
        return False
    
    # 必须有服务器地址
    if not proxy.get('server'):
        if debug:
            print(f"   [validate] 节点无服务器: {proxy.get('name')}")
        return False
    
    # 必须有端口
    if not proxy.get('port'):
        if debug:
            print(f"   [validate] 节点无端口: {proxy.get('name')}")
        return False
    
    # 必须有类型
    proxy_type = proxy.get('type', '').lower()
    # 增加对 vless 节点类型的支持
    if proxy_type not in ['ss', 'ssr', 'vmess', 'vless', 'trojan', 'snell', 'http', 'socks5', 'hysteria', 'hysteria2']:
        if debug:
            print(f"   [validate] 节点类型不支持: {proxy.get('name')} -> {proxy_type}")
        return False
    
    return True
