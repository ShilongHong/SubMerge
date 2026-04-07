# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SubMerge is a Flask web app that merges multiple Clash VPN subscription sources into a single permanent subscription link. It supports remote URLs and local file uploads, with token-based config persistence, time-limited access control, and custom rule injection.

## Running

```bash
pip install -r requirements.txt
python app.py
# Access http://127.0.0.1:5000
```

No test suite exists. There is no build step for development — just run `app.py`.

## Architecture

**Single-file backend**: `app.py` (~1715 lines) contains all routing, subscription parsing, proxy parsing, merging logic, and custom rule validation. No framework beyond Flask.

**Frontend**: `templates/index.html` — Alpine.js + Tailwind CSS SPA.

**Utils**: `utils/` contains three modules:
- `cache.py` — simple in-memory TTL cache (unused by app.py; app.py has its own file-based caching in `subscription_cache/`)
- `config.py` — loads `config/config.yaml` for emoji rules, node filters, rename patterns (mostly legacy; app.py hardcodes most behavior)
- `node_utils.py` — node name processing (emoji add/remove, rename, filter, deduplicate, validate)

## Key Data Flow

1. User creates/updates config via web UI → `POST /api/create` or `PUT /api/config/<token>`
2. Uploaded files stored in `uploaded_files/{md5}.txt`, config saved to `configs/{token}.json`
3. Clash client fetches `GET /api/subscribe?token=<token>` → app downloads all remote subs, parses, merges → returns YAML

## Critical Implementation Details

### Proxy Parsing Pipeline (`app.py:208-512`)

`parse_proxy_uri()` handles URI protocols (`vless://`, `vmess://`, `ss://`, `trojan://`, etc.). `parse_uri_list()` handles lists of URIs. Subscriptions are tried in order: YAML → base64+YAML → URI list → base64+URI list.

### Merge Logic (`app.py:742` — `merge_subscriptions()`)

1. Primary subscription provides rules + proxy-group structure (exactly one required)
2. All nodes renamed as `[订阅名]_原节点名` to avoid conflicts
3. Auto-creates: `ALL` group, per-subscription groups, `其他节点` group, optional `Auto` load-balancing groups
4. `in_rules` flag controls whether nodes appear in original proxy-groups
5. Special groups injected: `下载` (dev/ML sites), `挑剔的网站` (quality-sensitive sites)
6. Custom rules injected at configurable priority position (high/medium/low)

**Node name transform order matters**: prefix → rename → emoji → filter. Changing the order breaks references.

### YAML Emoji Handling

**DO NOT** strip emojis from proxy names — `clean_yaml_text()` only removes control chars (0x00-0x1F), not Unicode emojis. Names must match exactly between `proxies`, `proxy-groups`, and `rules`.

### Subscription Downloading (`app.py:528` — `download_subscription()`)

Retries with 7 different User-Agents (Clash clients, browsers) to bypass restrictions. File-based caching in `subscription_cache/{md5}.json` prevents redundant downloads.

## API Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/create` | POST | Create/update subscription config (multipart/form-data) |
| `/api/config/<token>` | GET | Load saved config |
| `/api/config/<token>` | PUT | Update saved config |
| `/api/subscribe?token=<token>` | GET | Serve merged Clash YAML to client |
| `/subscribe` | GET | Legacy 3-sub merge (backward compat) |
| `/merge` | POST | Direct merge without persistence |
| `/` | GET | Web UI |

## Config Schema (`configs/{token}.json`)

```json
{
  "subscriptions": [{
    "name": "订阅名", "url": "远程链接", "file_md5": "MD5",
    "is_main": true, "in_rules": true, "enable_auto": false
  }],
  "custom_rules": ["DOMAIN-SUFFIX,example.com,DIRECT"],
  "custom_rules_file_md5": "MD5",
  "custom_rules_priority": "medium",
  "access_window_minutes": 5,
  "created_at": "ISO timestamp",
  "last_updated": "ISO timestamp (UTC)"
}
```

## Language

All UI text, comments, and variable names that are user-facing are in Chinese. Maintain this convention.

## Dependencies

Flask 3.0.0, PyYAML 6.0.1, requests 2.31.0, regex 2023.12.25. Python 3.13.
