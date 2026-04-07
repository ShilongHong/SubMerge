from flask import Flask, render_template, request, jsonify, Response
import requests
import yaml
import base64
from datetime import datetime
import re
import hashlib
import secrets
import json
import os
from werkzeug.utils import secure_filename
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传文件大小为16MB

# 配置存储目录
CONFIGS_DIR = 'configs'
if not os.path.exists(CONFIGS_DIR):
    os.makedirs(CONFIGS_DIR)

# 文件内容存储目录
FILES_DIR = 'uploaded_files'
if not os.path.exists(FILES_DIR):
    os.makedirs(FILES_DIR)

# 订阅缓存目录
CACHE_DIR = 'subscription_cache'
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def get_file_md5(content):
    """计算内容的 MD5"""
    if isinstance(content, str):
        content = content.encode('utf-8')
    return hashlib.md5(content).hexdigest()

def save_uploaded_file(content):
    """保存上传的文件内容，返回 MD5"""
    md5 = get_file_md5(content)
    file_path = os.path.join(FILES_DIR, f"{md5}.txt")
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    return md5

def load_uploaded_file(md5):
    """根据 MD5 加载文件内容"""
    file_path = os.path.join(FILES_DIR, f"{md5}.txt")
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def get_subscription_cache_key(url):
    """生成订阅缓存的键（使用URL的MD5）"""
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def save_subscription_cache(url, content_dict, userinfo=''):
    """保存订阅到本地缓存"""
    try:
        cache_key = get_subscription_cache_key(url)
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        cache_data = {
            'url': url,
            'content': content_dict,
            'userinfo': userinfo,
            'cached_at': datetime.now().isoformat(),
            'cached_timestamp': datetime.now().timestamp()
        }
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        print(f"   ✅ 订阅已缓存到本地: {cache_file}")
        return True
    except Exception as e:
        print(f"   ⚠️ 缓存保存失败: {e}")
        return False

def load_subscription_cache(url):
    """从本地缓存加载订阅"""
    try:
        cache_key = get_subscription_cache_key(url)
        cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
        
        if not os.path.exists(cache_file):
            return None, None
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        cached_time = cache_data.get('cached_at', '未知时间')
        print(f"   📦 使用本地缓存（缓存时间: {cached_time}）")
        
        return cache_data.get('content'), cache_data.get('userinfo', '')
    except Exception as e:
        print(f"   ⚠️ 缓存加载失败: {e}")
        return None, None

def parse_traffic_info(userinfo):
    """
    解析流量信息
    userinfo 格式: upload=123456; download=789012; total=10737418240; expire=1234567890
    返回: 格式化的文本
    """
    if not userinfo:
        return "♻️ 余量获取"
    
    try:
        # 解析各个字段
        info_dict = {}
        for item in userinfo.split(';'):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=', 1)
                info_dict[key.strip()] = value.strip()
        
        # 安全地解析数值，处理空字符串情况
        def safe_int(value, default=0):
            if not value or value == '':
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        upload = safe_int(info_dict.get('upload', '0'))
        download = safe_int(info_dict.get('download', '0'))
        total = safe_int(info_dict.get('total', '0'))
        expire_str_raw = info_dict.get('expire', '').strip()
        
        # 计算剩余流量
        used = upload + download
        remaining = total - used if total > used else 0
        
        # 转换为 GB
        def bytes_to_gb(bytes_val):
            return round(bytes_val / (1024**3), 2)
        
        remaining_gb = bytes_to_gb(remaining)
        total_gb = bytes_to_gb(total)
        
        # 转换过期时间
        if expire_str_raw and expire_str_raw != '':
            expire = safe_int(expire_str_raw)
            if expire > 0:
                expire_date = datetime.fromtimestamp(expire)
                expire_str = expire_date.strftime('%Y-%m-%d')
            else:
                expire_str = '永久'
        else:
            expire_str = '永久'
        
        # 生成节点名
        return f"♻️ 剩余{remaining_gb}G/总{total_gb}G | 到期{expire_str}"
        
    except Exception as e:
        print(f"解析流量信息失败: {e}")
        return "♻️ 余量获取"

def get_config_file_path(token):
    """获取配置文件路径"""
    return os.path.join(CONFIGS_DIR, f"{token}.json")

def load_config(token):
    """加载指定token的配置"""
    config_file = get_config_file_path(token)
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def save_config(token, config):
    """保存指定token的配置"""
    config_file = get_config_file_path(token)
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False

def delete_config(token):
    """删除指定token的配置"""
    config_file = get_config_file_path(token)
    if os.path.exists(config_file):
        try:
            os.remove(config_file)
            return True
        except:
            return False
    return False

def list_all_tokens():
    """列出所有token"""
    tokens = []
    if os.path.exists(CONFIGS_DIR):
        for filename in os.listdir(CONFIGS_DIR):
            if filename.endswith('.json'):
                tokens.append(filename[:-5])  # 去掉.json后缀
    return tokens

def parse_proxy_uri(uri):
    """
    解析单个代理 URI（如 vless://, vmess://, ss://, trojan:// 等）
    返回 Clash 格式的代理配置字典，失败返回 None
    """
    import urllib.parse
    
    uri = uri.strip()
    if not uri:
        return None
    
    try:
        # VMess 协议（base64 编码的 JSON）
        if uri.startswith('vmess://'):
            try:
                encoded = uri[8:]
                # 处理可能的 padding 问题
                padding = 4 - len(encoded) % 4
                if padding != 4:
                    encoded += '=' * padding
                decoded = base64.b64decode(encoded).decode('utf-8')
                vmess_config = json.loads(decoded)
                
                proxy = {
                    'name': vmess_config.get('ps', vmess_config.get('remarks', 'VMess节点')),
                    'type': 'vmess',
                    'server': vmess_config.get('add', ''),
                    'port': int(vmess_config.get('port', 443)),
                    'uuid': vmess_config.get('id', ''),
                    'alterId': int(vmess_config.get('aid', 0)),
                    'cipher': vmess_config.get('scy', 'auto'),
                }
                
                # 传输层设置
                net = vmess_config.get('net', 'tcp')
                if net == 'ws':
                    proxy['network'] = 'ws'
                    proxy['ws-opts'] = {
                        'path': vmess_config.get('path', '/'),
                        'headers': {'Host': vmess_config.get('host', '')}
                    }
                elif net == 'grpc':
                    proxy['network'] = 'grpc'
                    proxy['grpc-opts'] = {
                        'grpc-service-name': vmess_config.get('path', '')
                    }
                
                # TLS
                if vmess_config.get('tls') == 'tls':
                    proxy['tls'] = True
                    sni = vmess_config.get('sni', vmess_config.get('host', ''))
                    if sni:
                        proxy['servername'] = sni
                
                return proxy
            except Exception as e:
                print(f"   解析 VMess 失败: {e}")
                return None
        
        # VLESS 协议
        elif uri.startswith('vless://'):
            try:
                # vless://uuid@server:port?params#name
                parsed = urllib.parse.urlparse(uri)
                uuid = parsed.username or ''
                server = parsed.hostname or ''
                port = parsed.port or 443
                name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'VLESS节点'
                
                # 解析查询参数
                params = dict(urllib.parse.parse_qsl(parsed.query))
                
                proxy = {
                    'name': name,
                    'type': 'vless',
                    'server': server,
                    'port': port,
                    'uuid': uuid,
                    'udp': True,
                }
                
                # 传输层
                network = params.get('type', 'tcp')
                if network == 'ws':
                    proxy['network'] = 'ws'
                    proxy['ws-opts'] = {
                        'path': params.get('path', '/'),
                        'headers': {'Host': params.get('host', server)}
                    }
                elif network == 'grpc':
                    proxy['network'] = 'grpc'
                    proxy['grpc-opts'] = {
                        'grpc-service-name': params.get('serviceName', '')
                    }
                
                # TLS / Reality
                security = params.get('security', '')
                if security == 'tls':
                    proxy['tls'] = True
                    if params.get('sni'):
                        proxy['servername'] = params['sni']
                    if params.get('alpn'):
                        proxy['alpn'] = params['alpn'].split(',')
                elif security == 'reality':
                    proxy['tls'] = True
                    proxy['reality-opts'] = {
                        'public-key': params.get('pbk', ''),
                        'short-id': params.get('sid', '')
                    }
                    if params.get('sni'):
                        proxy['servername'] = params['sni']
                    if params.get('fp'):
                        proxy['client-fingerprint'] = params['fp']
                
                # Flow（用于 XTLS）
                if params.get('flow'):
                    proxy['flow'] = params['flow']
                
                return proxy
            except Exception as e:
                print(f"   解析 VLESS 失败: {e}")
                return None
        
        # SS 协议
        elif uri.startswith('ss://'):
            try:
                # ss://base64(method:password)@server:port#name
                # 或 ss://base64(method:password@server:port)#name
                uri_part = uri[5:]
                name = 'SS节点'
                if '#' in uri_part:
                    uri_part, name = uri_part.rsplit('#', 1)
                    name = urllib.parse.unquote(name)
                
                # 尝试解析 SIP002 格式
                if '@' in uri_part:
                    user_info, server_info = uri_part.rsplit('@', 1)
                    # user_info 可能是 base64 编码的
                    try:
                        padding = 4 - len(user_info) % 4
                        if padding != 4:
                            user_info += '=' * padding
                        decoded_user = base64.b64decode(user_info).decode('utf-8')
                        method, password = decoded_user.split(':', 1)
                    except:
                        method, password = user_info.split(':', 1)
                    
                    server, port = server_info.rsplit(':', 1)
                else:
                    # 旧格式：整个都是 base64
                    padding = 4 - len(uri_part) % 4
                    if padding != 4:
                        uri_part += '=' * padding
                    decoded = base64.b64decode(uri_part).decode('utf-8')
                    method_pass, server_port = decoded.rsplit('@', 1)
                    method, password = method_pass.split(':', 1)
                    server, port = server_port.rsplit(':', 1)
                
                proxy = {
                    'name': name,
                    'type': 'ss',
                    'server': server,
                    'port': int(port),
                    'cipher': method,
                    'password': password,
                }
                return proxy
            except Exception as e:
                print(f"   解析 SS 失败: {e}")
                return None
        
        # Trojan 协议
        elif uri.startswith('trojan://'):
            try:
                # trojan://password@server:port?params#name
                parsed = urllib.parse.urlparse(uri)
                password = parsed.username or ''
                server = parsed.hostname or ''
                port = parsed.port or 443
                name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'Trojan节点'
                
                params = dict(urllib.parse.parse_qsl(parsed.query))
                
                proxy = {
                    'name': name,
                    'type': 'trojan',
                    'server': server,
                    'port': port,
                    'password': password,
                    'udp': True,
                }
                
                # SNI
                if params.get('sni'):
                    proxy['sni'] = params['sni']
                
                # 跳过证书验证
                if params.get('allowInsecure') == '1':
                    proxy['skip-cert-verify'] = True
                
                # 传输层
                network = params.get('type', 'tcp')
                if network == 'ws':
                    proxy['network'] = 'ws'
                    proxy['ws-opts'] = {
                        'path': params.get('path', '/'),
                        'headers': {'Host': params.get('host', server)}
                    }
                elif network == 'grpc':
                    proxy['network'] = 'grpc'
                    proxy['grpc-opts'] = {
                        'grpc-service-name': params.get('serviceName', '')
                    }
                
                return proxy
            except Exception as e:
                print(f"   解析 Trojan 失败: {e}")
                return None
        
        # Hysteria2 协议
        elif uri.startswith('hysteria2://') or uri.startswith('hy2://'):
            try:
                prefix_len = 12 if uri.startswith('hysteria2://') else 6
                parsed = urllib.parse.urlparse(uri)
                password = parsed.username or ''
                server = parsed.hostname or ''
                port = parsed.port or 443
                name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'Hysteria2节点'
                
                params = dict(urllib.parse.parse_qsl(parsed.query))
                
                proxy = {
                    'name': name,
                    'type': 'hysteria2',
                    'server': server,
                    'port': port,
                    'password': password,
                }
                
                if params.get('sni'):
                    proxy['sni'] = params['sni']
                if params.get('insecure') == '1':
                    proxy['skip-cert-verify'] = True
                
                return proxy
            except Exception as e:
                print(f"   解析 Hysteria2 失败: {e}")
                return None
    
    except Exception as e:
        print(f"   解析代理 URI 失败: {e}")
    
    return None


def parse_uri_list(text):
    """
    解析 URI 列表格式的订阅内容
    返回 Clash 格式的配置字典，失败返回 None
    """
    lines = text.strip().split('\n')
    proxies = []
    
    print(f"   URI列表共 {len(lines)} 行")
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 打印前几个 URI 的类型
        if i < 5:
            proto = line.split('://')[0] if '://' in line else 'unknown'
            print(f"   第{i+1}行协议: {proto}")
        
        proxy = parse_proxy_uri(line)
        if proxy:
            proxies.append(proxy)
            if i < 5:
                print(f"      ✅ 解析成功: {proxy.get('name', 'unnamed')}")
        else:
            if i < 5:
                print(f"      ❌ 解析失败")
    
    if not proxies:
        print(f"   ⚠️ 没有成功解析任何节点")
        return None
    
    print(f"   解析到 {len(proxies)} 个节点（URI格式）")
    
    # 构建基础 Clash 配置
    config = {
        'proxies': proxies,
        'proxy-groups': [
            {
                'name': '节点选择',
                'type': 'select',
                'proxies': [p['name'] for p in proxies] + ['DIRECT']
            }
        ],
        'rules': ['MATCH,节点选择']
    }
    
    return config


def clean_yaml_text(text):
    """
    清理 YAML 文本中可能导致解析问题的特殊字符
    注意：不再清理 emoji，因为这会导致代理组名称和规则引用不一致
    只清理可能导致 YAML 解析失败的控制字符
    """
    import re
    
    # 只移除可能导致 YAML 解析问题的控制字符（保留换行和制表符）
    # 不移除 emoji，保持代理组名称一致性
    control_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
    return control_pattern.sub('', text)


def download_subscription(url, use_cache=True):
    """下载订阅内容，返回 (content, userinfo)"""
    headers = {
        'User-Agent': 'clash-verge/v2.4.6',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }

    try:
        print(f"下载订阅: {url[:60]}...")
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.raise_for_status()

        userinfo = response.headers.get('subscription-userinfo', '') or response.headers.get('Subscription-Userinfo', '')
        if userinfo:
            print(f"   获取到流量信息: {userinfo[:50]}...")

        raw_text = response.text

        # 1. YAML
        try:
            cleaned_text = clean_yaml_text(raw_text)
            content = yaml.safe_load(cleaned_text)
            if content and isinstance(content, dict) and ('proxies' in content or 'proxy-groups' in content):
                print("[OK] YAML")
                if use_cache:
                    save_subscription_cache(url, content, userinfo)
                return content, userinfo
        except Exception as e:
            print(f"   YAML: {e}")

        # 2. base64
        try:
            b64_text = ''.join(c for c in raw_text.strip() if ord(c) < 128)
            missing_padding = len(b64_text) % 4
            if missing_padding:
                b64_text += '=' * (4 - missing_padding)
            decoded = base64.b64decode(b64_text).decode('utf-8')

            try:
                content = yaml.safe_load(decoded)
                if content and isinstance(content, dict) and ('proxies' in content or 'proxy-groups' in content):
                    print("[OK] base64+YAML")
                    if use_cache:
                        save_subscription_cache(url, content, userinfo)
                    return content, userinfo
            except:
                try:
                    cleaned_decoded = clean_yaml_text(decoded)
                    content = yaml.safe_load(cleaned_decoded)
                    if content and isinstance(content, dict) and ('proxies' in content or 'proxy-groups' in content):
                        print("[OK] base64+YAML(cleaned)")
                        if use_cache:
                            save_subscription_cache(url, content, userinfo)
                        return content, userinfo
                except:
                    pass

            if any(proto in decoded for proto in ['vless://', 'vmess://', 'ss://', 'trojan://', 'hysteria2://', 'hy2://']):
                content = parse_uri_list(decoded)
                if content:
                    print("[OK] base64+URI")
                    if use_cache:
                        save_subscription_cache(url, content, userinfo)
                    return content, userinfo
        except Exception as e:
            print(f"   base64: {e}")

        # 3. URI
        if any(proto in raw_text for proto in ['vless://', 'vmess://', 'ss://', 'trojan://', 'hysteria2://', 'hy2://']):
            content = parse_uri_list(raw_text)
            if content:
                print("[OK] URI")
                if use_cache:
                    save_subscription_cache(url, content, userinfo)
                return content, userinfo

        print(f"   [WARN] unrecognized, first 100: {raw_text[:100]}")
        return None, userinfo

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else 'Unknown'
        print(f"[ERROR] HTTP {status_code}")
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        print(f"[ERROR] network: {e}")
    except Exception as e:
        print(f"[ERROR] {e}")

    if use_cache:
        print("   trying cache...")
        cached_content, cached_userinfo = load_subscription_cache(url)
        if cached_content:
            print("[OK] cache hit")
            return cached_content, cached_userinfo
        print("   no cache")

    return None, None


def parse_local_subscription(content):
    """
    解析本地上传的订阅内容
    支持YAML、base64编码的内容和URI列表
    """
    # 1. 先清理 emoji，尝试解析为 YAML
    try:
        cleaned_content = clean_yaml_text(content)
        config = yaml.safe_load(cleaned_content)
        if config and isinstance(config, dict) and ('proxies' in config or 'proxy-groups' in config):
            print(f"   ✅ 本地内容解析成功（YAML格式）")
            return config
    except Exception as e:
        print(f"   本地 YAML 解析失败: {e}")
    
    # 2. 尝试 base64 解码后解析
    try:
        # 只保留 ASCII 字符进行 base64 解码
        b64_text = ''.join(c for c in content.strip() if ord(c) < 128)
        missing_padding = len(b64_text) % 4
        if missing_padding:
            b64_text += '=' * (4 - missing_padding)
        decoded = base64.b64decode(b64_text).decode('utf-8')
        
        # 2.1 清理后尝试 YAML
        try:
            cleaned_decoded = clean_yaml_text(decoded)
            config = yaml.safe_load(cleaned_decoded)
            if config and isinstance(config, dict) and ('proxies' in config or 'proxy-groups' in config):
                print(f"   ✅ 本地内容解析成功（base64 + YAML）")
                return config
        except Exception as e:
            print(f"   base64解码后 YAML 解析失败: {e}")
        
        # 2.2 尝试 URI 列表格式
        if any(proto in decoded for proto in ['vless://', 'vmess://', 'ss://', 'trojan://', 'hysteria2://', 'hy2://']):
            config = parse_uri_list(decoded)
            if config:
                print(f"   ✅ 本地内容解析成功（base64 + URI列表）")
                return config
                
    except Exception as e:
        print(f"   base64 解码失败: {e}")
    
    # 3. 直接尝试 URI 列表格式
    if any(proto in content for proto in ['vless://', 'vmess://', 'ss://', 'trojan://', 'hysteria2://', 'hy2://']):
        config = parse_uri_list(content)
        if config:
            print(f"   ✅ 本地内容解析成功（URI列表）")
            return config
    
    print(f"   ❌ 本地内容无法解析，前100字符: {content[:100]}")
    return None

def merge_subscriptions(subscriptions):
    """
    合并多个订阅
    subscriptions: [{'url': '...', 'name': '订阅1', 'is_main': True, 'in_rules': True}, ...]
    返回: (merged_config, error, userinfo_list)
    """
    # 下载所有订阅（本地同步处理，远程并行下载）
    downloaded_subs = []
    userinfo_list = []
    main_sub = None
    main_sub_index = 0
    primary_userinfo = ''

    # 1. 处理本地订阅（同步，很快）
    remote_subs = []
    for idx, sub_info in enumerate(subscriptions):
        sub_content = sub_info.get('content', '')
        sub_name = sub_info['name']
        is_main = sub_info.get('is_main', False)

        if sub_content:
            print(f"处理本地订阅: {sub_name}")
            sub = parse_local_subscription(sub_content)
            if not sub:
                return None, f"{sub_name} 解析失败（本地内容格式错误）", []
            downloaded_subs.append({
                'data': sub, 'name': sub_name,
                'is_main': is_main,
                'in_rules': sub_info.get('in_rules', True),
                'enable_auto': sub_info.get('enable_auto', False),
                'userinfo': '', 'index': idx
            })
            userinfo_list.append({'name': sub_name, 'userinfo': '', 'is_local': True})
            if is_main:
                main_sub = sub
                main_sub_index = idx
        else:
            remote_subs.append((idx, sub_info))

    # 2. 并行下载远程订阅
    if remote_subs:
        def _download_one(args):
            idx, sub_info = args
            return idx, sub_info, download_subscription(sub_info['url'])

        print(f"并行下载 {len(remote_subs)} 个远程订阅...")
        with ThreadPoolExecutor(max_workers=min(len(remote_subs), 4)) as executor:
            futures = {executor.submit(_download_one, args): args for args in remote_subs}
            for future in as_completed(futures):
                idx, sub_info, (sub, userinfo) = future.result()
                sub_name = sub_info['name']
                is_main = sub_info.get('is_main', False)

                if not sub:
                    if is_main:
                        return None, f"{sub_name}（主订阅）下载失败", []
                    print(f"[WARN] 跳过失败的订阅: {sub_name}")
                    continue

                print(f"[OK] {sub_name} 下载完成")
                userinfo_list.append({'name': sub_name, 'userinfo': userinfo, 'is_local': False})
                if userinfo and not primary_userinfo:
                    primary_userinfo = userinfo

                downloaded_subs.append({
                    'data': sub, 'name': sub_name,
                    'is_main': is_main,
                    'in_rules': sub_info.get('in_rules', True),
                    'enable_auto': sub_info.get('enable_auto', False),
                    'userinfo': userinfo, 'index': idx
                })
                if is_main:
                    main_sub = sub
                    main_sub_index = idx

    if not downloaded_subs:
        return None, "所有订阅均下载失败", []
    
    # 如果没有指定主订阅，使用第一个
    if not main_sub:
        main_sub = downloaded_subs[0]['data']
        downloaded_subs[0]['is_main'] = True
        main_sub_index = 0
    
    # 基础配置使用主订阅的
    merged_config = {
        'port': main_sub.get('port', 7890),
        'socks-port': main_sub.get('socks-port', 7891),
        'allow-lan': main_sub.get('allow-lan', False),
        'mode': main_sub.get('mode', 'Rule'),
        'log-level': main_sub.get('log-level', 'info'),
        'external-controller': main_sub.get('external-controller', '127.0.0.1:9090'),
        'dns': main_sub.get('dns', {}),
    }
    
    # 复制主订阅的其他配置
    for key in main_sub:
        if key not in merged_config and key not in ['proxies', 'proxy-groups', 'rules']:
            merged_config[key] = main_sub[key]
    
    # 合并所有订阅的节点
    all_proxies = []
    proxy_names_by_sub = {}  # {sub_name: [node_names]}
    proxy_names_all = []
    used_names = set()
    
    # 处理所有订阅的节点
    for sub_info in downloaded_subs:
        sub_data = sub_info['data']
        sub_name = sub_info['name']
        proxies = sub_data.get('proxies', [])
        proxy_names_by_sub[sub_name] = []
        
        # 统计节点类型
        type_count = {}
        for proxy in proxies:
            ptype = proxy.get('type', 'unknown')
            type_count[ptype] = type_count.get(ptype, 0) + 1
        print(f"   [{sub_name}] 节点类型统计: {type_count}")
        
        for proxy in proxies:
            if proxy.get('name'):
                original_name = proxy['name']
                new_name = f"[{sub_name}]_{original_name}"
                
                # 避免重名
                counter = 1
                final_name = new_name
                while final_name in used_names:
                    final_name = f"{new_name}_{counter}"
                    counter += 1
                
                proxy['name'] = final_name
                all_proxies.append(proxy)
                proxy_names_by_sub[sub_name].append(final_name)
                proxy_names_all.append(final_name)
                used_names.add(final_name)
    
    # 创建节点信息虚拟节点（显示流量和到期信息）
    info_proxies = []
    for info in userinfo_list:
        if info.get('is_local'):
            # 本地上传的订阅不显示流量信息
            continue
        
        userinfo = info.get('userinfo', '')
        sub_name = info.get('name', '未知订阅')
        
        if userinfo:
            # 解析流量信息
            info_text = parse_traffic_info(userinfo)
            # 在信息文本前加上订阅组名称
            info_text = f"{sub_name}_{info_text}"
        else:
            info_text = f"{sub_name}_无流量信息"
        
        # 如果节点信息名称已存在，跳过（只保留第一个）
        if info_text in used_names:
            continue
        
        # 创建虚拟节点（使用 ss 类型，但不会实际连接）
        info_node = {
            'name': info_text,
            'type': 'ss',
            'server': '127.0.0.1',
            'port': 1,
            'cipher': 'aes-128-gcm',
            'password': 'info-node'
        }
        info_proxies.append(info_node)
        all_proxies.append(info_node)
        used_names.add(info_text)
    
    merged_config['proxies'] = all_proxies
    
    # 创建额外的代理组
    proxy_groups = []
    
    # 收集所有 Auto 组（稍后添加到最后）
    auto_groups = []
    auto_group_names = []
    
    # 1. 为每个订阅创建单独的代理组（select，可选 auto）
    for sub_info in downloaded_subs:
        sub_name = sub_info['name']
        sub_nodes = proxy_names_by_sub.get(sub_name, []) or []
        enable_auto = sub_info.get('enable_auto', False)  # 是否启用自动选择组
        
        # 创建 select 手动选择组
        sub_proxies = []
        
        # 如果启用了 auto 且有节点，创建 auto 自动测速组（稍后添加）
        if enable_auto and sub_nodes:
            auto_group_name = f"{sub_name}_Auto"
            auto_group = {
                'name': auto_group_name,
                'type': 'url-test',
                'proxies': sub_nodes.copy(),
                'url': 'http://www.gstatic.com/generate_204',
                'interval': 300
            }
            auto_groups.append(auto_group)
            auto_group_names.append(auto_group_name)
            sub_proxies.append(auto_group_name)  # 在 select 组中添加 auto 组引用
        
        sub_proxies.extend(sub_nodes)  # 所有节点
        
        if not sub_proxies:  # 没有节点
            sub_proxies.append('DIRECT')
        
        sub_group = {
            'name': sub_name,
            'type': 'select',
            'proxies': sub_proxies
        }
        proxy_groups.append(sub_group)
    
    # 收集所有订阅组名称（在创建节点信息组之前准备好）
    new_group_names = [s['name'] for s in downloaded_subs]
    
    # 2. 创建"节点信息"代理组（显示订阅流量信息，不参与规则）
    if info_proxies:
        info_group = {
            'name': '节点信息',
            'type': 'select',
            'proxies': [node['name'] for node in info_proxies]
        }
        proxy_groups.append(info_group)
    
    # 处理主订阅的相关信息（需要在创建代理组前准备好）
    main_sub_name = downloaded_subs[main_sub_index]['name']
    main_proxy_names = proxy_names_by_sub.get(main_sub_name, [])
    main_in_rules = downloaded_subs[main_sub_index].get('in_rules', True)  # 主订阅是否参与规则
    
    # 收集参与规则的所有节点（在创建代理组前准备好）
    rule_proxy_names = []
    for sub_info in downloaded_subs:
        if sub_info.get('in_rules', True):  # 如果订阅参与规则
            sub_nodes = proxy_names_by_sub.get(sub_info['name'], [])
            # 如果是主订阅，根据 main_in_rules 决定是否添加
            if sub_info['name'] == main_sub_name:
                if main_in_rules:
                    rule_proxy_names.extend(sub_nodes)
            else:
                rule_proxy_names.extend(sub_nodes)
    
    download_group = {
        'name': '下载',
        'type': 'select',
        'proxies': ['DIRECT']  # 第一个是直连
    }
    # 添加所有订阅组（手动切换）
    for group_name in new_group_names:
        if group_name not in download_group['proxies']:
            download_group['proxies'].append(group_name)
    # 添加 Auto 组到下载组
    for auto_name in auto_group_names:
        if auto_name not in download_group['proxies']:
            download_group['proxies'].append(auto_name)
    proxy_groups.append(download_group)
    
    # 添加"挑剔的网站"代理组（用于 Google Scholar、Copilot、Cursor等）
    picky_sites_group = {
        'name': '挑剔的网站',
        'type': 'select',
        'proxies': ['DIRECT']  # 默认第一个是直连
    }
    # 添加所有订阅组
    for group_name in new_group_names:
        if group_name not in picky_sites_group['proxies']:
            picky_sites_group['proxies'].append(group_name)
    # 添加 Auto 组到挑剔的网站组
    for auto_name in auto_group_names:
        if auto_name not in picky_sites_group['proxies']:
            picky_sites_group['proxies'].append(auto_name)
    # 添加所有参与规则的节点
    for node_name in rule_proxy_names:
        if node_name not in picky_sites_group['proxies']:
            picky_sites_group['proxies'].append(node_name)
    proxy_groups.append(picky_sites_group)
    
    # 添加所有 Auto 组
    proxy_groups.extend(auto_groups)
    
    # 添加 "TikTok解锁" 代理组
    tiktok_unlock_group = {
        'name': 'TikTok解锁',
        'type': 'select',
        'proxies': ['DIRECT']  # 第一个是直连
    }
    # 添加所有订阅组
    for group_name in new_group_names:
        if group_name not in tiktok_unlock_group['proxies']:
            tiktok_unlock_group['proxies'].append(group_name)
    # 添加 Auto 组
    for auto_name in auto_group_names:
        if auto_name not in tiktok_unlock_group['proxies']:
            tiktok_unlock_group['proxies'].append(auto_name)
    # 添加所有参与规则的节点
    for node_name in rule_proxy_names:
        if node_name not in tiktok_unlock_group['proxies']:
            tiktok_unlock_group['proxies'].append(node_name)
    proxy_groups.append(tiktok_unlock_group)
    
    # 添加 "屏蔽视频广告" 代理组
    video_ad_block_group = {
        'name': '屏蔽视频广告',
        'type': 'select',
        'proxies': ['REJECT', 'DIRECT']  # 默认拒绝，也可以选择直连
    }
    proxy_groups.append(video_ad_block_group)
    
    # 添加 "常见广告域名" 代理组
    common_ad_group = {
        'name': '常见广告域名',
        'type': 'select',
        'proxies': ['REJECT', 'DIRECT']  # 默认拒绝，也可以选择直连
    }
    proxy_groups.append(common_ad_group)
    
    # 处理主订阅的代理组，将新增的代理组添加到每个代理组中
    original_groups = main_sub.get('proxy-groups', [])
    
    for group in original_groups:
        new_group = group.copy()
        
        # 如果代理组有 proxies 列表
        if 'proxies' in new_group:
            # 保存原有规则组的第一个节点（默认选中的节点）
            original_default = new_group['proxies'][0] if len(new_group['proxies']) > 0 else None
            
            # 处理默认选中的节点（可能需要加前缀）
            processed_default = None
            if original_default:
                # 检查是否是主订阅的原始节点名（需要加前缀）
                prefixed_default = f"[{main_sub_name}]_{original_default}"
                if prefixed_default in main_proxy_names:
                    # 只有当主订阅参与规则时，才保留主订阅的原始节点引用
                    if main_in_rules:
                        processed_default = prefixed_default
                # 保留代理组引用和其他特殊值
                elif (original_default in [g['name'] for g in original_groups] or 
                      original_default in used_names or 
                      original_default in ['DIRECT', 'REJECT'] or
                      original_default in new_group_names or
                      original_default in auto_group_names):
                    processed_default = original_default
            
            # 构建新的代理列表
            new_proxies = []
            
            # 1. 第一个始终是 DIRECT
            new_proxies.append('DIRECT')
            
            # 2. 第二个开始是新增的代理组引用（订阅组）
            for group_name in new_group_names:
                if group_name not in new_proxies:
                    new_proxies.append(group_name)
            
            # 3. 添加所有 Auto 组引用（跳过已添加的）
            for auto_name in auto_group_names:
                if auto_name not in new_proxies:
                    new_proxies.append(auto_name)
            
            # 4. 保留原有的其他代理引用（跳过第一个已处理的默认节点）
            for idx, proxy_ref in enumerate(new_group['proxies']):
                if idx == 0 and processed_default:  # 跳过已处理的第一个节点
                    continue
                    
                if proxy_ref not in new_proxies:
                    # 检查是否是主订阅的原始节点名（需要加前缀）
                    prefixed_ref = f"[{main_sub_name}]_{proxy_ref}"
                    if prefixed_ref in main_proxy_names:
                        # 只有当主订阅参与规则时，才保留主订阅的原始节点引用
                        if main_in_rules:
                            proxy_ref = prefixed_ref
                        else:
                            # 主订阅不参与规则，跳过这个节点
                            continue
                    
                    # 保留代理组引用和其他特殊值
                    if (proxy_ref in [g['name'] for g in original_groups] or 
                        proxy_ref in used_names or 
                        proxy_ref in ['DIRECT', 'REJECT']):
                        new_proxies.append(proxy_ref)
            
            # 5. 添加所有参与规则的节点（跳过已添加的）
            for node_name in rule_proxy_names:
                if node_name not in new_proxies:
                    new_proxies.append(node_name)
            
            new_group['proxies'] = new_proxies
        
        proxy_groups.append(new_group)
    
    merged_config['proxy-groups'] = proxy_groups
    
    # 使用主订阅的规则
    original_rules = main_sub.get('rules', [])
    
    # 添加默认的下载规则（在原有规则之前）
    download_rules = [
        'DOMAIN-SUFFIX,huggingface.co,下载',
        'DOMAIN-SUFFIX,hf.co,下载',
        'DOMAIN-SUFFIX,huggingface-cdn.com,下载',
        'DOMAIN-SUFFIX,pytorch.org,下载',
        'DOMAIN-SUFFIX,tensorflow.org,下载',
        'DOMAIN-SUFFIX,kaggle.com,下载',
        'DOMAIN-KEYWORD,github,下载',
        'DOMAIN-SUFFIX,github.blog,下载',
        'DOMAIN-SUFFIX,github.com,下载',
        'DOMAIN-SUFFIX,githubusercontent.com,下载',
        'DOMAIN-SUFFIX,github.io,下载',
        'DOMAIN-SUFFIX,githubassets.com,下载',
        'DOMAIN-SUFFIX,rawgithub.com,下载',
        'DOMAIN-SUFFIX,githubapp.com,下载',
        'DOMAIN-SUFFIX,npmjs.org,下载',
        'DOMAIN-SUFFIX,npmjs.com,下载',
        'DOMAIN-SUFFIX,pypi.org,下载',
        'DOMAIN-SUFFIX,python.org,下载',
        'DOMAIN-SUFFIX,anaconda.org,下载',
        'DOMAIN-SUFFIX,conda.io,下载',
        'DOMAIN-SUFFIX,docker.com,下载',
        'DOMAIN-SUFFIX,docker.io,下载',
        'DOMAIN-SUFFIX,dockerhub.com,下载',
        'DOMAIN-SUFFIX,amazonaws.com,下载',
        'DOMAIN-SUFFIX,cloudfront.net,下载',
        'DOMAIN-SUFFIX,googleapis.com,下载',
        'DOMAIN-SUFFIX,gstatic.com,下载',
        'DOMAIN-SUFFIX,stackoverflow.com,下载',
        'DOMAIN-SUFFIX,arxiv.org,下载',
        'DOMAIN-SUFFIX,sourceforge.net,下载',
        'DOMAIN-SUFFIX,gitlab.com,下载',
        'DOMAIN-SUFFIX,bitbucket.org,下载',
        'DOMAIN-SUFFIX,ubuntu.com,下载',
        'DOMAIN-SUFFIX,debian.org,下载',
        'DOMAIN-SUFFIX,archlinux.org,下载',
        'DOMAIN-SUFFIX,centos.org,下载',
        'DOMAIN-SUFFIX,jetbrains.com,下载',
        'DOMAIN-SUFFIX,visualstudio.com,下载',
        'DOMAIN-SUFFIX,code.visualstudio.com,下载',
        'DOMAIN-SUFFIX,maven.org,下载',
        'DOMAIN-SUFFIX,gradle.org,下载',
        'DOMAIN-SUFFIX,usercontent.google.com,下载'
    ]
    
    # 挑剔的网站规则（Google Scholar、Copilot、Cursor等）
    picky_site_rules = [
        'DOMAIN-SUFFIX,scholar.google.com,挑剔的网站',
        'DOMAIN-KEYWORD,copilot,挑剔的网站',
        'DOMAIN-SUFFIX,aicursor.com,挑剔的网站',
        'DOMAIN-SUFFIX,cursor.sh,挑剔的网站',
        'DOMAIN-SUFFIX,openrouter.ai,挑剔的网站'
    ]
    
    # TikTok 解锁规则
    tiktok_unlock_rules = [
        'DOMAIN-SUFFIX,musical.ly,TikTok解锁',
        'DOMAIN-SUFFIX,pstatp.com,TikTok解锁',
        'DOMAIN-SUFFIX,tiktokv.com,TikTok解锁'
    ]
    
    # 常见广告域名规则
    common_ad_rules = [
        'DOMAIN-KEYWORD,admarvel,常见广告域名',
        'DOMAIN-KEYWORD,admaster,常见广告域名',
        'DOMAIN-KEYWORD,adsage,常见广告域名',
        'DOMAIN-KEYWORD,adsmogo,常见广告域名',
        'DOMAIN-KEYWORD,adsrvmedia,常见广告域名',
        'DOMAIN-KEYWORD,adwords,常见广告域名',
        'DOMAIN-KEYWORD,adservice,常见广告域名',
        'DOMAIN-SUFFIX,appsflyer.com,常见广告域名',
        'DOMAIN-KEYWORD,domob,常见广告域名',
        'DOMAIN-SUFFIX,doubleclick.net,常见广告域名',
        'DOMAIN-KEYWORD,duomeng,常见广告域名',
        'DOMAIN-KEYWORD,dwtrack,常见广告域名',
        'DOMAIN-KEYWORD,guanggao,常见广告域名',
        'DOMAIN-KEYWORD,lianmeng,常见广告域名',
        'DOMAIN-SUFFIX,mmstat.com,常见广告域名',
        'DOMAIN-KEYWORD,mopub,常见广告域名',
        'DOMAIN-KEYWORD,omgmta,常见广告域名',
        'DOMAIN-KEYWORD,openx,常见广告域名',
        'DOMAIN-KEYWORD,partnerad,常见广告域名',
        'DOMAIN-KEYWORD,pingfore,常见广告域名',
        'DOMAIN-KEYWORD,supersonicads,常见广告域名',
        'DOMAIN-KEYWORD,uedas,常见广告域名',
        'DOMAIN-KEYWORD,umeng,常见广告域名',
        'DOMAIN-KEYWORD,usage,常见广告域名',
        'DOMAIN-SUFFIX,vungle.com,常见广告域名',
        'DOMAIN-KEYWORD,wlmonitor,常见广告域名',
        'DOMAIN-KEYWORD,zjtoolbar,常见广告域名'
    ]
    
    # 屏蔽视频广告规则
    video_ad_block_rules = [
        # 爱奇艺
        'DOMAIN-SUFFIX,a.ckm.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ad.m.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,afp.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,api.cupid.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,c.uaa.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,cloudpush.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,cm.passport.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,emoticon.sns.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,gamecenter.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,hotchat-im.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ifacelog.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,mbdlog.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,msg.video.qiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,msg2.video.qiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,msga.cupid.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,policy.video.iqiyi.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,yuedu.iqiyi.com,屏蔽视频广告',
        # 湖南TV
        'DOMAIN-SUFFIX,click.hunantv.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,da.mgtv.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,da.hunantv.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,res.hunantv.com,屏蔽视频广告',
        # 优酷
        'DOMAIN-SUFFIX,actives.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ad.api.3g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ad.api.mobile.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ad.mobile.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,a-dxk.play.api.3g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,b.smartvideo.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,c.yes.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,das.api.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,das.mobile.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,dev-push.m.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,dl.g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,dmapp.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,e.stat.ykimg.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,gamex.mobile.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,hudong.pl.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,huodong.pl.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,huodong.vip.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,hz.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,iyes.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,l.ykimg.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,lstat.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,mobilemsg.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,msg.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,myes.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,p-log.ykimg.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,p.l.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,passport-log.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,p-log.ykimg.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,sdk.m.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,stat.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,statis.api.3g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,store.tv.api.3g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,store.xl.api.3g.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,tdrec.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,test.ott.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,test.sdk.m.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,urchin.lstat.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ykatr.youku.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,ykrec.youku.com,屏蔽视频广告',
        # 腾讯视频
        'DOMAIN-SUFFIX,ad.video.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,a.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,c.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,d.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,e.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,mi.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,q.i.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,sd.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,t.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,btrace.video.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,monitor.uu.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,pingma.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,pingtcss.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,report.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,tajs.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,v.gdt.qq.com,屏蔽视频广告',
        'DOMAIN-SUFFIX,omgmta.qq.com,屏蔽视频广告'
    ]
    
    # 收集所有有效的代理组名称
    valid_group_names = set([g['name'] for g in proxy_groups])
    valid_group_names.add('DIRECT')
    valid_group_names.add('REJECT')
    
    # 规则的额外参数（不是代理组名称）
    rule_extra_params = {'no-resolve', 'no-resolve,', 'extended-match', 'src'}
    
    # 验证规则，移除引用不存在代理组的规则
    valid_rules = []
    for rule in original_rules:
        # 解析规则格式: 
        # TYPE,VALUE,GROUP 或 TYPE,VALUE,GROUP,no-resolve 或 MATCH,GROUP
        parts = rule.split(',')
        if len(parts) >= 2:
            # 找到代理组名称（排除 no-resolve 等参数）
            group_name = None
            for i in range(len(parts) - 1, 0, -1):  # 从后往前找
                part = parts[i].strip()
                if part.lower() not in rule_extra_params:
                    group_name = part
                    break
            
            if group_name is None:
                group_name = parts[-1].strip()
            
            if group_name in valid_group_names:
                valid_rules.append(rule)
            else:
                print(f"   ⚠️ 移除无效规则 (代理组不存在): {rule} -> 找不到组: [{group_name}]")
                # 调试：打印有效组名
                # print(f"      有效组名: {list(valid_group_names)[:5]}...")
        else:
            valid_rules.append(rule)  # 保留格式不对的规则
    
    # 合并规则：TikTok解锁 + 常见广告域名 + 屏蔽视频广告 + 挑剔的网站规则在最前 + 下载规则 + 有效的原有规则
    merged_config['rules'] = tiktok_unlock_rules + common_ad_rules + video_ad_block_rules + picky_site_rules + download_rules + valid_rules
    
    return merged_config, None, userinfo_list

@app.route('/')
def index():
    """首页"""
    return render_template('index.html')

@app.route('/merge', methods=['POST'])
def merge():
    """合并订阅的API"""
    data = request.get_json()
    
    # 新格式：支持任意数量的订阅
    subscriptions = data.get('subscriptions', [])
    
    # 兼容旧格式
    if not subscriptions:
        sub1_url = data.get('sub1_url', '').strip()
        sub2_url = data.get('sub2_url', '').strip()
        sub3_url = data.get('sub3_url', '').strip()
        
        if not all([sub1_url, sub2_url, sub3_url]):
            return jsonify({'error': '请提供订阅信息'}), 400
        
        sub1_name = data.get('sub1_name', '订阅1').strip()
        sub2_name = data.get('sub2_name', '订阅2').strip()
        sub3_name = data.get('sub3_name', '订阅3').strip()
        
        subscriptions = [
            {'url': sub1_url, 'name': sub1_name, 'is_main': True, 'in_rules': True},
            {'url': sub2_url, 'name': sub2_name, 'is_main': False, 'in_rules': True},
            {'url': sub3_url, 'name': sub3_name, 'is_main': False, 'in_rules': True}
        ]
    
    if not subscriptions:
        return jsonify({'error': '请至少一个订阅'}), 400
    
    # 合并订阅
    merged_config, error, userinfo_list = merge_subscriptions(subscriptions)
    
    if error:
        return jsonify({'error': error}), 500
    
    # 转换为YAML
    try:
        yaml_content = yaml.dump(merged_config, allow_unicode=True)
        return jsonify({
            'success': True,
            'config': yaml_content,
            'stats': {
                'total_proxies': len(merged_config.get('proxies', [])),
                'proxy_groups': len(merged_config.get('proxy-groups', [])),
                'rules': len(merged_config.get('rules', []))
            }
        })
    except Exception as e:
        return jsonify({'error': f'生成配置失败: {str(e)}'}), 500

@app.route('/api/config/<token>', methods=['GET'])
def get_config(token):
    """查询订阅配置"""
    config = load_config(token)
    if not config:
        return jsonify({'error': '无效的Token'}), 404
    
    return jsonify({
        'success': True,
        'token': token,
        'config': config
    })

@app.route('/api/config/<token>', methods=['PUT'])
def update_config(token):
    """更新订阅配置"""
    existing_config = load_config(token)
    if not existing_config:
        return jsonify({'error': '无效的Token,请先创建'}), 404
    
    try:
        # 检查是否是文件上传
        if request.content_type and 'multipart/form-data' in request.content_type:
            # 处理表单数据
            subscriptions = []
            
            # 获取订阅数量
            sub_count = 0
            for key in request.form.keys():
                if key.startswith('sub_name_'):
                    sub_count += 1
            
            # 处理每个订阅
            for i in range(sub_count):
                sub_name = request.form.get(f'sub_name_{i}', '').strip()
                sub_url = request.form.get(f'sub_url_{i}', '').strip()
                is_main = request.form.get(f'is_main_{i}') == 'true'
                in_rules = request.form.get(f'in_rules_{i}') == 'true'
                enable_auto = request.form.get(f'enable_auto_{i}') == 'true'
                old_file_md5 = request.form.get(f'file_md5_{i}', '').strip()  # 获取旧的 MD5
                
                # 检查是否有上传文件
                file_key = f'sub_file_{i}'
                sub_content = ''
                file_md5 = ''
                
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename:
                        sub_content = file.read().decode('utf-8')
                        # 计算新文件的 MD5
                        new_md5 = get_file_md5(sub_content)
                        # 对比 MD5，有变化才保存
                        if new_md5 != old_file_md5:
                            file_md5 = save_uploaded_file(sub_content)
                            print(f"   文件内容已更新: {sub_name}, MD5: {file_md5}")
                        else:
                            file_md5 = old_file_md5
                            print(f"   文件内容未变化: {sub_name}, MD5: {file_md5}")
                elif old_file_md5:
                    # 没有新上传文件，使用旧的 MD5
                    file_md5 = old_file_md5
                
                # URL和文件至少有一个
                if sub_name and (sub_url or file_md5):
                    subscriptions.append({
                        'name': sub_name,
                        'url': sub_url,
                        'file_md5': file_md5,  # 保存文件的 MD5
                        'is_main': is_main,
                        'in_rules': in_rules,
                        'enable_auto': enable_auto
                    })
        else:
            # JSON格式
            data = request.get_json()
            subscriptions = data.get('subscriptions', [])
        
        if not subscriptions:
            return jsonify({'error': '请提供订阅信息'}), 400
        
        # 更新配置
        config_data = {
            'subscriptions': subscriptions,
            'updated_at': datetime.now().isoformat(),
            'created_at': existing_config.get('created_at', datetime.now().isoformat())
        }
        save_config(token, config_data)
        
        return jsonify({
            'success': True,
            'message': '配置更新成功',
            'token': token
        })
    except Exception as e:
        return jsonify({'error': f'更新失败: {str(e)}'}), 500

@app.route('/api/create', methods=['POST'])
def create_subscription():
    """创建订阅配置并生成Token"""
    try:
        # 检查是否提供了现有token（用于更新）
        existing_token = None
        if request.content_type and 'multipart/form-data' in request.content_type:
            existing_token = request.form.get('token', '').strip()
        else:
            data = request.get_json()
            existing_token = data.get('token', '').strip() if data else None
        
        # 如果提供了token且存在,则更新
        if existing_token and load_config(existing_token):
            return update_config(existing_token)
        
        # 检查是否是文件上传
        if request.content_type and 'multipart/form-data' in request.content_type:
            # 处理表单数据
            subscriptions = []
            
            # 获取订阅数量
            sub_count = 0
            for key in request.form.keys():
                if key.startswith('sub_name_'):
                    sub_count += 1
            
            # 处理每个订阅
            for i in range(sub_count):
                sub_name = request.form.get(f'sub_name_{i}', '').strip()
                sub_url = request.form.get(f'sub_url_{i}', '').strip()
                is_main = request.form.get(f'is_main_{i}') == 'true'
                in_rules = request.form.get(f'in_rules_{i}') == 'true'
                enable_auto = request.form.get(f'enable_auto_{i}') == 'true'
                
                # 检查是否有上传文件
                file_key = f'sub_file_{i}'
                sub_content = ''
                file_md5 = ''
                
                if file_key in request.files:
                    file = request.files[file_key]
                    if file and file.filename:
                        sub_content = file.read().decode('utf-8')
                        # 保存文件并获取 MD5
                        file_md5 = save_uploaded_file(sub_content)
                        print(f"   新建订阅文件: {sub_name}, MD5: {file_md5}")
                
                # URL和文件内容至少有一个
                if sub_name and (sub_url or file_md5):
                    subscriptions.append({
                        'name': sub_name,
                        'url': sub_url,
                        'content': sub_content,  # 用于合并，但不保存到配置
                        'file_md5': file_md5,    # 保存 MD5 用于持久化
                        'is_main': is_main,
                        'in_rules': in_rules,
                        'enable_auto': enable_auto
                    })
        else:
            # JSON格式
            data = request.get_json()
            subscriptions = data.get('subscriptions', [])
        
        if not subscriptions:
            return jsonify({'error': '请提供订阅信息'}), 400
        
        # 生成唯一token
        token = secrets.token_hex(16)
        
        # 保存配置（保存 file_md5 而不是 content）
        save_subscriptions_config = []
        for sub in subscriptions:
            save_sub = {
                'name': sub['name'],
                'url': sub.get('url', ''),
                'file_md5': sub.get('file_md5', ''),  # 保存文件的 MD5
                'is_main': sub.get('is_main', False),
                'in_rules': sub.get('in_rules', True),
                'enable_auto': sub.get('enable_auto', False)
            }
            save_subscriptions_config.append(save_sub)
        
        config_data = {
            'subscriptions': save_subscriptions_config,
            'created_at': datetime.now().isoformat()
        }
        save_config(token, config_data)
        
        # 生成订阅链接
        subscribe_url = f"{request.host_url}api/subscribe?token={token}"
        
        return jsonify({
            'success': True,
            'token': token,
            'subscribe_url': subscribe_url
        })
    except Exception as e:
        return jsonify({'error': f'创建失败: {str(e)}'}), 500

@app.route('/api/subscribe')
def subscribe_with_token():
    """通过Token获取订阅"""
    ua = request.headers.get('User-Agent', 'unknown')
    print(f"[Client UA] {ua}")
    token = request.args.get('token', '')
    
    if not token:
        return Response('缺少token参数', status=400)
    
    config = load_config(token)
    if not config:
        return Response('无效的Token', status=403)
    subscriptions = config['subscriptions']
    
    # 对于有 file_md5 的订阅，从本地文件加载内容
    for sub in subscriptions:
        file_md5 = sub.get('file_md5', '')
        if file_md5 and not sub.get('content'):
            content = load_uploaded_file(file_md5)
            if content:
                sub['content'] = content
                print(f"   从本地加载文件: {sub['name']}, MD5: {file_md5}")
            else:
                print(f"   ⚠️ 文件不存在: {sub['name']}, MD5: {file_md5}")
    
    try:
        # 合并订阅
        merged_config, error, userinfo_list = merge_subscriptions(subscriptions)
        
        if error:
            print(f"❌ 合并订阅失败: {error}")
            return Response(f'错误: {error}', status=500)
        
        print(f"✅ 合并完成，共 {len(merged_config.get('proxies', []))} 个节点")
        
        # 合并所有订阅的流量信息（优先使用主订阅的，如果没有则使用第一个）
        subscription_userinfo = ''
        if userinfo_list:
            # 优先使用有流量信息的订阅
            for info in userinfo_list:
                if info and isinstance(info, dict) and info.get('userinfo'):
                    subscription_userinfo = info['userinfo']
                    print(f"使用 {info.get('name', '未知')} 的流量信息")
                    break
        
        if not subscription_userinfo:
            print("⚠️ 没有获取到流量信息，将不显示余量")
        
        # 转换为YAML
        print("正在生成 YAML...")
        yaml_content = yaml.dump(merged_config, allow_unicode=True)
        print(f"✅ YAML 生成成功，长度: {len(yaml_content)}")
        
        response_headers = {
            'Content-Disposition': f'attachment; filename=clash_config_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml',
        }
        if subscription_userinfo:
            response_headers['subscription-userinfo'] = subscription_userinfo
        
        return Response(
            yaml_content,
            mimetype='text/yaml',
            headers=response_headers
        )
    except Exception as e:
        import traceback
        print(f"❌ 订阅处理异常: {e}")
        traceback.print_exc()
        return Response(f'生成配置失败: {str(e)}', status=500)

@app.route('/subscribe')
def subscribe():
    """兼容旧版订阅链接"""
    sub1_url = request.args.get('sub1', '')
    sub2_url = request.args.get('sub2', '')
    sub3_url = request.args.get('sub3', '')
    
    # 获取自定义订阅名称
    sub1_name = request.args.get('sub1_name', '订阅1')
    sub2_name = request.args.get('sub2_name', '订阅2')
    sub3_name = request.args.get('sub3_name', '订阅3')
    
    if not all([sub1_url, sub2_url, sub3_url]):
        return Response('缺少必要的订阅参数', status=400)
    
    subscriptions = [
        {'url': sub1_url, 'name': sub1_name, 'is_main': True, 'in_rules': True},
        {'url': sub2_url, 'name': sub2_name, 'is_main': False, 'in_rules': True},
        {'url': sub3_url, 'name': sub3_name, 'is_main': False, 'in_rules': True}
    ]
    
    # 合并订阅
    merged_config, error, userinfo_list = merge_subscriptions(subscriptions)
    
    if error:
        return Response(f'错误: {error}', status=500)
    
    # 合并所有订阅的流量信息
    subscription_userinfo = ''
    if userinfo_list:
        for info in userinfo_list:
            if info and isinstance(info, dict) and info.get('userinfo'):
                subscription_userinfo = info['userinfo']
                break
    
    # 转换为YAML
    try:
        yaml_content = yaml.dump(merged_config, allow_unicode=True)
        response_headers = {
            'Content-Disposition': f'attachment; filename=clash_config_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml',
        }
        if subscription_userinfo:
            response_headers['subscription-userinfo'] = subscription_userinfo
        
        return Response(
            yaml_content,
            mimetype='text/yaml',
            headers=response_headers
        )
    except Exception as e:
        return Response(f'生成配置失败: {str(e)}', status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
