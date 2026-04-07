# utils/ — Agent Guide

## Status: Disconnected from app.py

`app.py` does NOT import these modules — it has its own inline implementations. These utilities exist as standalone code but are not part of the active runtime.

Do not assume calling or modifying these files affects subscription merging behavior.

---

## Module Reference

### `cache.py` — TTL In-Memory Cache
`class TTLCache(maxsize, ttl)`: dict-backed cache with per-entry expiry.
- `get(key)` → value or `None` if missing/expired
- `set(key, value)` → stores with current-time TTL
- `delete(key)`, `clear()`
- No thread-safety guarantees (no locks)

### `config.py` — Legacy Config Loader
Loads `config/config.yaml` into a `AppConfig` dataclass:
- `emoji_rules`: list of `(pattern, emoji)` tuples
- `node_filters`: include/exclude regex patterns
- `rename_rules`: list of `(from_pattern, to_pattern)` substitutions
- `default_subscriptions`: pre-configured subscription entries

`get_config()` returns singleton `AppConfig`. File path resolved relative to `config/config.yaml`.

### `node_utils.py` — Node Name Processing
Standalone functions for node name manipulation:

| Function | Behavior |
|---|---|
| `add_emoji_to_node(name, rules)` | Prepend emoji based on regex match against name |
| `rename_node(name, rules)` | Apply regex substitution rules sequentially |
| `filter_nodes(nodes, filters)` | Include/exclude nodes by pattern |
| `validate_proxy_name(name)` | Returns `(bool, error_str)` — rejects empty, >100 chars, control chars |
| `clean_proxy_name(name)` | Strips leading/trailing whitespace only |

**These functions do NOT strip emojis** — consistent with app.py's critical constraint.

---

## If You Use These Modules

Import from `utils`:
```python
from utils.cache import TTLCache
from utils.config import get_config
from utils.node_utils import add_emoji_to_node, filter_nodes
```

`validate_proxy_name` and `clean_proxy_name` are safe to use — they do not mutate emoji or Unicode.
