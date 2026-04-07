# SubMerge - AI Coding Guide

## Project Overview
SubMerge is a Flask web application that intelligently merges multiple Clash VPN subscription sources into a single permanent subscription link. It supports remote URLs and local file uploads, with persistent token-based configuration management, **time-limited access control**, and **custom rule injection**.

## Architecture

### Core Components
- **[app.py](../app.py)** (1700+ lines): Main Flask application containing all routing, subscription merging logic, proxy parsing, and **custom rule validation**
- **[utils/](../utils/)**: Modular utilities (cache, config, node processing)
- **[templates/index.html](../templates/index.html)**: Alpine.js + Tailwind CSS SPA interface (1100+ lines) with **custom rules UI**
- **Token-based storage**: `configs/*.json` stores persistent subscription configurations with **access window** and **custom rules**, `uploaded_files/*.txt` stores file content by MD5

### Data Flow
1. User creates/updates subscription via web UI → `/api/create` or `/api/config/{token}`
   - **NEW**: Validates custom rules format (DOMAIN-SUFFIX, IP-CIDR, etc.) using `validate_clash_rule()`
   - **NEW**: Stores `access_window_minutes`, `custom_rules`, `custom_rules_priority` in config
2. File content stored in `uploaded_files/{md5}.txt`, configuration saved to `configs/{token}.json` with UTC `last_updated` timestamp
3. Clash client requests `/api/subscribe?token={token}` → **checks access window** → downloads/parses all subscriptions → **loads custom rules** → merges proxies/groups/rules with priority → returns YAML
4. Caching in `subscription_cache/{md5}.json` prevents redundant downloads (MD5-based)

## Key Patterns

### Time-Limited Access Control (NEW)
[app.py](../app.py#L1520-L1545) `subscribe_with_token()` enforces configurable access windows:
- Retrieves `access_window_minutes` from config (default: 5 minutes, 0 = never expires)
- Compares current UTC time with `last_updated` timestamp
- Returns 403 error if access window exceeded
- **Backward compatible**: Falls back to `updated_at` if `last_updated` missing

All time handling uses `datetime.now(timezone.utc)` for consistency across timezones.

### Custom Rule Validation & Injection (NEW)
**Validation** ([app.py](../app.py#L30-L130)): `validate_clash_rule()` function ensures rules are Clash-compliant before storage:
- Supported types: DOMAIN, DOMAIN-SUFFIX, DOMAIN-KEYWORD, IP-CIDR, IP-CIDR6, GEOIP, SRC-IP-CIDR, SRC-PORT, DST-PORT, PROCESS-NAME, MATCH
- Uses `ipaddress` library for strict IP-CIDR validation
- Validates proxy group names are non-empty
- Returns `(is_valid, error_message)` tuple

**Injection** ([app.py](../app.py#L1070-L1120)): Custom rules inserted into `merge_subscriptions()` with configurable priority:
- **High priority**: `custom_rules + picky_site + download + original`
- **Medium priority** (default): `picky_site + custom_rules + download + original`
- **Low priority**: `picky_site + download + original + custom_rules`
- Rules validated for proxy-group existence before inclusion (same as original rules)

When modifying rule logic, preserve validation consistency between custom and original rules.

### Multi-Format Proxy Parsing
[app.py](../app.py#L150-L400) supports multiple encoding formats sequentially:
1. **YAML format** (native Clash configs)
2. **Base64-encoded YAML** (common subscription format)
3. **URI lists** (`vless://`, `vmess://`, `ss://`, `trojan://`, etc.) - parsed by `parse_proxy_uri()`
4. **Base64-encoded URI lists**

When adding new proxy protocols, extend `parse_proxy_uri()` - see VLESS/VMess examples for parameter extraction patterns.

### Subscription Merge Logic
Main merge function: `merge_subscriptions(subscriptions, custom_rules=None, custom_rules_priority='medium')` ([app.py](../app.py#L729-L1120))
1. **Primary subscription** provides rules + proxy-groups structure (exactly one required)
2. **Node prefixing**: All nodes renamed as `[订阅名]_原节点名` to avoid conflicts
3. **Automatic groups**: Creates `ALL` (all nodes), individual subscription groups, `其他节点` (non-primary nodes), and optional `Auto` load-balancing groups
4. **Rule participation**: `in_rules` flag controls whether subscription nodes appear in original proxy-groups (PROXY, YouTube, etc.)
5. **Special group injection**: `下载` group for development/ML sites (GitHub, HuggingFace, PyPI, etc.) and `挑剔的网站` for services requiring specific node quality
6. **NEW**: Custom rules injected at position determined by `custom_rules_priority` parameter

When modifying merge logic, preserve proxy-group name consistency between groups and rules to prevent broken references.

### Configuration Persistence
- **Token generation**: 32-char hex via `secrets.token_hex(16)`
- **File deduplication**: Content stored by MD5 hash to avoid duplicates across configs
- **Update workflow**: Existing token in request → loads old config → updates subscriptions → preserves `created_at`, updates `last_updated` (UTC)
- **NEW Schema fields**:
  - `access_window_minutes` (int): Access time limit in minutes, 0 = never expires
  - `custom_rules` (array): List of custom rule strings
  - `custom_rules_file_md5` (string): MD5 of uploaded custom rules file
  - `custom_rules_priority` (string): "high" | "medium" | "low"
  - `last_updated` (string): UTC ISO timestamp for access window validation

## Development Workflows

### Running Locally
```bash
pip install -r requirements.txt
python app.py
# Access: http://127.0.0.1:5000
```

### Building Executable
```batch
# Uses uv package manager + PyInstaller
build.bat  # Creates dist/SubMerge.exe (~50MB standalone)
```
Build script ([build.bat](../build.bat)) requires `.venv` with PyInstaller. Hidden imports include: `werkzeug.security`, `jinja2`, `yaml`, `requests`, `regex`, **`ipaddress`**. Data files: `templates/`, `config/`.

### Debugging Subscription Issues
- Check console logs for parsing attempts (YAML → base64+YAML → URI → base64+URI)
- Subscription download retries 7 different User-Agents (Clash clients, browsers) to bypass restrictions
- Traffic info extracted from `subscription-userinfo` HTTP header (format: `upload=X; download=Y; total=Z; expire=TIMESTAMP`)
- **NEW**: Custom rule validation errors returned in API response with line numbers

## Critical Implementation Details

### YAML Emoji Handling
**DO NOT** strip emojis from proxy names - this breaks proxy-group references in rules. Function `clean_yaml_text()` only removes control characters (0x00-0x1F), not Unicode emojis. Proxy names must match exactly between `proxies`, `proxy-groups`, and `rules`.

### Rule Validation
Before returning merged config, `merge_subscriptions()` validates all rules reference existing proxy-groups ([app.py](../app.py#L1040-L1070)). Invalid rules are logged and removed to prevent Clash errors. **Custom rules undergo the same validation** to ensure proxy-group references are valid.

### Node Name Transformations
Order matters in `merge_subscriptions()`:
1. Add prefix `[订阅名]_`
2. Apply `rename_node` rules from config
3. Add emoji via `add_emoji_to_node()` if enabled
4. Apply `filter_nodes()` for include/exclude patterns

### API Contracts
- **POST `/api/create`**: Accepts `multipart/form-data` with:
  - Subscription fields: `sub_name_N`, `sub_url_N`, `sub_file_N`, `is_main_N`, `in_rules_N`, `enable_auto_N`
  - **NEW**: `custom_rules` (JSON array string), `custom_rules_file` (file), `custom_rules_priority` (string), `access_window_minutes` (int)
  - Returns `{token, subscribe_url}` or `{error, invalid_rules: [...]}` on validation failure
- **GET `/api/subscribe?token=X`**: 
  - **NEW**: Checks access window, returns 403 if expired
  - Returns YAML with `subscription-userinfo` header for client traffic display
- **GET/PUT `/api/config/{token}`**: Load/update existing configuration with custom rules support

## Testing Considerations
- Test with mix of YAML subscriptions, base64-encoded subscriptions, and URI lists
- Verify node name conflicts resolved by prefixing
- Confirm rule references remain valid after merge
- Test file upload persistence across server restarts (MD5-based storage)
- **NEW**: Test access window expiration with various `access_window_minutes` values (0, 5, 60, etc.)
- **NEW**: Test custom rule validation with invalid rules (malformed IP-CIDR, invalid rule types, etc.)
- **NEW**: Verify custom rule priority affects final rule order correctly

## Configuration Files
- **[config/config.yaml](../config/config.yaml)**: Default emoji rules, node filters, rename patterns (not actively used in current implementation, mostly legacy)
- Subscription configs in `configs/` use JSON format with schema:
  ```json
  {
    "subscriptions": [{
      "name": "订阅名",
      "url": "远程链接",
      "file_md5": "MD5哈希",
      "is_main": true,
      "in_rules": true,
      "enable_auto": false
    }],
    "custom_rules": ["DOMAIN-SUFFIX,example.com,DIRECT"],
    "custom_rules_file_md5": "MD5哈希",
    "custom_rules_priority": "medium",
    "access_window_minutes": 5,
    "created_at": "2026-01-12T10:30:00+00:00",
    "last_updated": "2026-01-12T10:35:00+00:00"
  }
  ```

## UI Features (NEW)
[templates/index.html](../templates/index.html) includes comprehensive custom rules interface:
- **Rule Input Modes**: Text input (textarea) or file upload (.txt, .conf, .list)
- **Priority Selector**: Dropdown for high/medium/low priority with explanatory tooltips
- **Access Window**: Number input for minutes (0-525600), "永不过期" quick button
- **Validation Feedback**: Displays invalid rules with line numbers and error messages
- **Config Loading**: Auto-fills custom rules, priority, and access window from saved configs
- **Styling**: Gradient buttons with active states, drag-and-drop file upload with visual feedback
