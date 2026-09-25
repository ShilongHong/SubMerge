# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SubMerge is a Flask app that merges several Clash subscriptions (remote URLs or uploaded files) into one permanent, token-addressed subscription URL. One saved config can be served in two output flavors: v1 (rules from the main subscription) and v2 (the same nodes with a frozen rule template).

## Commands

Run everything from the repo root. `app.py` resolves `configs/`, `uploaded_files/`, `subscription_cache/` and `templates_storage/` relative to the CWD, and creates the first three at import time.

```bash
pip install -r requirements.txt
python app.py        # http://127.0.0.1:5000
```

`__main__` reads `SUBMERGE_HOST` (default `0.0.0.0`), `SUBMERGE_PORT` (`5000`), `SUBMERGE_DEBUG` (off) and `SUBMERGE_RELOAD` (on).

Tests use `unittest` (pytest also works). They do `import app`, so run them from the repo root:

```bash
python -m unittest discover -s tests
python -m unittest tests.test_v2_proxy_groups.V2FrozenRulesTest.test_supersub_first_and_rules_frozen
```

Tests isolate storage by pointing `app.CONFIGS_DIR`, `FILES_DIR` and `CACHE_DIR` at a temp dir. They pass subscriptions in as uploaded YAML through `app.test_client()`, so no network is needed (see `setUp` in `tests/test_v2_proxy_groups.py`). Some assertions depend on the contents of `templates_storage/default.json` and `templates_storage/v2_rules.json`.

`static/tailwind.css` is a committed, minified build used only by `templates/index.html`. Rebuild it after changing Tailwind classes. Its inputs (`package.json`, `tailwind.config.js`, `tailwind-input.css`) are gitignored local files:

```bash
npx tailwindcss -i tailwind-input.css -o static/tailwind.css --minify
```

There is no lint config. `ruff check app.py` runs with defaults and reports a handful of pre-existing warnings (unused imports, bare `except`).

## Architecture

The backend is the single file `app.py`, in roughly this order: storage/cache helpers → proxy URI parsing → subscription download/parse → V2 template builder → `merge_subscriptions()` → Flask routes. `app.py` does **not** import `utils/` or `config/config.yaml`, so editing them has no runtime effect.

### One merge core, two outputs

Every subscribe endpoint does the same setup first. It loads `configs/{token}.json` and enforces the legacy `access_window_minutes` if it is set (403 once that many minutes have passed since `last_updated`). Then it calls `merge_subscriptions()`:

| Endpoint | Pipeline |
|---|---|
| `/api/subscribe` (v1) | `merge_subscriptions(prefer_cache=False)`: always downloads, and uses the cache only as a fallback when a download fails |
| `/api/subscribe/v2` | v1 merge with `prefer_cache=True` → `build_v2_config()`, which replaces `proxy-groups` and `rules` |

v2 is built on the v1 merge, so any change to `merge_subscriptions()` affects both. Keep v1 output backward compatible, because deployed Clash clients poll that URL. The legacy `/merge` (stateless POST) and `/subscribe?sub1=&sub2=&sub3=` routes also call the v1 merge. V3 (the rule workbench, `/v3`, `/api/v3/*`, `/api/subscribe/v3`) has been removed; old configs may still carry a `v3` block, `schema_version` and subscription `id`s, which are ignored.

`prefer_cache=True` means stale-while-revalidate:

- A cache entry up to 15 minutes old is served as is.
- An entry up to 14 days old is served while a background refresh runs.
- Anything older is downloaded synchronously.

Add `?refresh=1` to a v2 URL to force a download. `subscription_cache/{md5(url)}.json` stores the *parsed* dict, not the raw text.

### `merge_subscriptions()` (v1 core)

- Local (`file_md5`) subscriptions are parsed synchronously. Remote ones download in parallel with a single `clash-verge/v2.4.6` User-Agent.
- If the main subscription fails, the whole merge fails. Failures in other subscriptions are skipped. If no subscription has `is_main`, the first one is used as main.
- The main subscription supplies `proxy-groups`, `rules` and every other top-level key (dns etc.).
- Every node is renamed `[订阅名]_原节点名`, with `_1`, `_2`… added on collision. Downstream tooling and users rely on this prefix, so don't change the format.
- Traffic info becomes fake `ss` nodes at `127.0.0.1:1` in the `节点信息` group; v2 leaves them out of `SuperSub`. `is_traffic_main` picks which subscription's `subscription-userinfo` header is passed through.
- Injected groups:
  - one `select` group per subscription, plus `{name}_Auto` when `enable_auto` is set
  - `节点信息`, `下载`, `挑剔的网站`, `TikTok解锁`, `屏蔽视频广告`, `常见广告域名`, `BLOCK`, `🌏 学术网站`

  Main-subscription groups whose names collide with these get a `_group` suffix, and their rules are rewritten to match.
- `in_rules` controls whether a subscription's nodes are added to the main subscription's groups and to the injected business groups. Without it, they appear only in their own subscription group.
- Final rules are the injected rule lists (TikTok, ads, video ads, academic, picky, download), followed by the main subscription's rules. Main-subscription rules whose target group doesn't exist are dropped. The injected lists are hardcoded inline, except the academic rules, which are the `🌏 学术网站` rules picked out of `templates_storage/default.json`.

Content is parsed in this order in both `download_subscription` and `parse_local_subscription`: YAML → base64→YAML → base64→URI list → raw URI list. `parse_proxy_uri()` handles vless, vmess, ss, trojan and hysteria2/hy2. A new scheme has to be added there and to the scheme-detection lists in both parse functions.

### V2 frozen rules (`build_v2_config`)

v2 keeps v1's proxies, subscription groups, `_Auto` groups, `节点信息`, top-level keys and `subscription-userinfo`, and swaps in `templates_storage/v2_rules.json` for everything rule-related. That file was generated from the 2026-09-25 v1 output of the TAG-main token, with TAG's own `🙂 TAGSS` group replaced by `SuperSub`. The main subscription's groups and rules are not used.

- Group order: `SuperSub`, then the subscription groups, the `_Auto` groups, `节点信息`, and the template groups. Template groups keep their order in `v2_rules.json`, which is hand-ordered: frequently adjusted proxy groups first, then `🐟 漏网之鱼`, then direct/block groups. All template group names start with an emoji, and v2 renamed v1's `下载`, `挑剔的网站`, `TikTok解锁`, `屏蔽视频广告` and `常见广告域名` accordingly (v1 keeps the plain names).
- `SuperSub` is a select group listing the subscription groups and `_Auto` groups first (so the default is the first subscription group), then **every** real node from every subscription, including those with `in_rules` off.
- Each template group lists its leading refs (`proxies`), and the first one is the default. Every group then gets `SuperSub`, `DIRECT`, `REJECT`, `PASS` (only when `v2_client_supports_pass(User-Agent)` matches a mihomo-based client, since older Clash cores reject unknown policies), the subscription groups, the `_Auto` groups and the `in_rules` nodes, the same participation as v1.
- `Ⓜ️ 微软服务` and `🍎 苹果服务` default to `DIRECT`. DIRECT/REJECT-style groups (`🎯 绕过代理`, `🚧 屏蔽访问`, `🛑 广告过滤` and the ad groups) keep their original defaults.
- A template group whose name collides with a subscription name is skipped. Rules whose target doesn't exist are dropped.

To change v2's rules, edit `v2_rules.json` directly. Every rule target must be a template group, `SuperSub`, `DIRECT`, `REJECT` or `PASS`.

### Persistence

Runtime data is gitignored and written atomically (temp file + `os.replace`):

- `configs/{token}.json`, where the token is `secrets.token_hex(16)`
- `uploaded_files/{md5}.txt`
- `subscription_cache/`

Subscription fields are `name`, `url`, `file_md5`, `is_main`, `in_rules`, `enable_auto` and `is_traffic_main`. Older configs may also carry `id`, `enable_region_groups` and `pool` from the removed V3/pool features; nothing reads them. `PUT /api/config/<token>` keeps unknown top-level keys, so legacy fields survive edits. `POST /api/create` with an existing token goes through the same update path.

A new per-subscription option has to be wired through several places:

- `templates/index.html`: `loadConfig()`, `collectSubscriptions()` and the `formData.append` block (form fields are indexed, e.g. `in_rules_N`)
- `app.py`: form parsing in both `create_subscription()` and `update_config()`, plus the saved dict in `create_subscription()`

### Frontend

- `templates/index.html` is the config page. It is plain DOM JS plus the prebuilt Tailwind CSS; Alpine.js (CDN) only drives the dark-mode toggle.
- `.impeccable.md` is the design brief (audience, tone, responsive master-detail layout, accessibility requirements). Follow it for UI work.

## Conventions and invariants

- **Never strip emoji or other Unicode from proxy or group names.** `clean_yaml_text()` removes only control characters. Names must match exactly across `proxies`, `proxy-groups` and `rules`, so any rename has to update every reference.
- User-facing text, log messages and comments are in Chinese. Keep it that way.
- Print through `log()`. Subscription URLs contain credentials, so log them only via `safe_url_label(url)`.
- Use timezone-aware UTC timestamps (`datetime.now(timezone.utc)`).
- `AGENTS.md`, `utils/AGENTS.md` and `.github/copilot-instructions.md` are outdated. They describe custom-rule injection, `validate_clash_rule`, multi-User-Agent retries and a PyInstaller `build.bat`/`build.spec`, and none of these exist. README's packaging section also references the missing `build.spec`. Trust the code.
