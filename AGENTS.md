# SubMerge — Agent Guide

## Project Identity
Flask web app that merges multiple Clash VPN subscriptions into a single permanent link. Single-file monolith (`app.py`, 1715 lines) with Alpine.js + Tailwind SPA frontend.

**Run**: `python app.py` → `http://127.0.0.1:5000`
**Build**: `build.bat` → `dist/SubMerge.exe` (PyInstaller, standalone)
**Stack**: Python 3.13, Flask 3.0.0, PyYAML 6.0.1, requests, regex, ipaddress

---

## File Map

| Path | Role |
|---|---|
| `app.py` | ALL logic: routing, parsing, merging, caching, validation |
| `templates/index.html` | Alpine.js + Tailwind SPA (1100+ lines) |
| `configs/{token}.json` | Persistent per-token config (subscriptions, custom rules, access window) |
| `uploaded_files/{md5}.txt` | Uploaded file content, deduplicated by MD5 |
| `subscription_cache/{md5}.json` | Downloaded subscription cache, deduplicated by MD5 |
| `templates_storage/default.json` | Default Clash proxy-group template |
| `config/config.yaml` | Legacy emoji/filter config — **not actively used** |
| `utils/` | Utility modules — **mostly not imported by app.py** (inline equivalents exist) |

---

## Data Flow

```
UI → POST /api/create  →  configs/{token}.json
                              ↓
Clash client → GET /api/subscribe?token=X
  → check access_window_minutes (403 if expired)
  → load subscriptions + uploaded files (by file_md5)
  → merge_subscriptions() → YAML
  → Response(yaml, headers={subscription-userinfo})
```

---

## API Surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/` | GET | SPA index |
| `/api/create` | POST | Create config, get token + subscribe_url |
| `/api/config/<token>` | GET | Load existing config |
| `/api/config/<token>` | PUT | Update existing config |
| `/api/subscribe` | GET | `?token=X` → Clash YAML file |
| `/merge` | POST | Legacy stateless merge (no token) |
| `/subscribe` | GET | Legacy query-param subscribe (3 fixed subs) |

**POST `/api/create`** accepts `multipart/form-data`:
- `sub_name_N`, `sub_url_N`, `sub_file_N`, `is_main_N`, `in_rules_N`, `enable_auto_N`
- `custom_rules` (JSON array string), `custom_rules_file`, `custom_rules_priority`, `access_window_minutes`
- Returns `{token, subscribe_url}` or `{error, invalid_rules:[...]}` on validation failure

---

## Config Schema (`configs/{token}.json`)

```json
{
  "subscriptions": [{
    "name": "订阅名", "url": "...", "file_md5": "...",
    "is_main": true, "in_rules": true, "enable_auto": false
  }],
  "custom_rules": ["DOMAIN-SUFFIX,example.com,DIRECT"],
  "custom_rules_file_md5": "...",
  "custom_rules_priority": "medium",
  "access_window_minutes": 5,
  "created_at": "2026-01-12T10:30:00+00:00",
  "last_updated": "2026-01-12T10:35:00+00:00"
}
```

---

## Merge Logic (`merge_subscriptions()`)

1. **Primary sub** (`is_main=True`) provides rules + proxy-groups structure
2. Node prefixing: all nodes renamed `[订阅名]_原节点名`
3. Duplicate name resolution: numeric suffix (`HK_1`, `HK_2`)
4. Auto-injected groups: `ALL`, per-subscription groups, `其他节点`
5. Optional `Auto` load-balancing group per sub (`enable_auto=True`)
6. `in_rules` flag: controls whether sub's nodes appear in PROXY/YouTube/etc. groups
7. Special injected groups: `下载` (GitHub/HuggingFace/PyPI), `挑剔的网站` (Scholar/Copilot/Cursor), `TikTok解锁`, `屏蔽视频广告`, `节点信息`
8. Custom rules injected by priority: high=before picky, medium=after picky, low=after all original rules
9. All rules validated against existing proxy-group names before output; invalid rules removed

**Supported proxy protocols**: VMess, VLESS, SS, Trojan, Hysteria2/hy2

**Multi-format parsing order**: YAML → base64+YAML → URI list → base64+URI list

**Subscription download**: 7 User-Agents tried (Clash clients → browsers) to bypass restrictions

---

## ⚠️ Critical Rules

**NEVER strip emojis from proxy names.** Emojis are part of names referenced in `proxy-groups` and `rules`. Breaking this causes invalid Clash configs.
- `clean_yaml_text()` strips control chars (0x00-0x1F) ONLY — not Unicode

**Proxy name must match exactly** across `proxies`, `proxy-groups`, and `rules`.

**Time handling**: always `datetime.now(timezone.utc)` — never naive datetimes.

**`utils/` modules are NOT used by `app.py`** — app.py has its own inline implementations. Do not assume `utils/node_utils.py` functions are called during merge.

**Custom rule validation** (`validate_clash_rule()`): supports DOMAIN, DOMAIN-SUFFIX, DOMAIN-KEYWORD, IP-CIDR, IP-CIDR6, GEOIP, SRC-IP-CIDR, SRC-PORT, DST-PORT, PROCESS-NAME, MATCH. Uses `ipaddress` for strict IP-CIDR validation.

---

## Access Window

`access_window_minutes` (0 = never expires): enforced in `subscribe_with_token()`. Compares `datetime.now(timezone.utc)` against `last_updated` (falls back to `updated_at` for backward compat). Returns HTTP 403 if expired.

---

## Build Notes

`build.bat` uses uv + PyInstaller. Required hidden imports: `werkzeug.security`, `jinja2`, `yaml`, `requests`, `regex`, `ipaddress`. Data files: `templates/`, `config/`.

Runtime directories created automatically on first run: `configs/`, `uploaded_files/`, `subscription_cache/`.
