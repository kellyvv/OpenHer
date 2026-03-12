---
name: weather
description: Get current weather and forecasts for the user's location (no API key required).
trigger: tool
executor: sandbox
homepage: https://wttr.in/:help
metadata: { "openclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Weather

Query weather using wttr.in (free, no API key).

## Location detection priority

1. If the user specifies a city → use it directly
2. Otherwise → auto-detect via IP geolocation:

```bash
CITY=$(curl -s --connect-timeout 3 ipinfo.io/city 2>/dev/null)
[ -z "$CITY" ] && CITY="Shanghai"
curl -s "wttr.in/${CITY}?format=%l:+%c+%t+%h+%w"
```

## Common patterns

Compact one-liner (auto-detect location):

```bash
curl -s "wttr.in/$(curl -s --connect-timeout 3 ipinfo.io/city 2>/dev/null || echo Shanghai)?format=%l:+%c+%t+%h+%w"
```

User specifies city:

```bash
curl -s "wttr.in/Beijing?format=%l:+%c+%t+%h+%w"
```

Full forecast (multi-day):

```bash
curl -s "wttr.in/$(curl -s --connect-timeout 3 ipinfo.io/city 2>/dev/null || echo Shanghai)?T&lang=zh"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:
- URL-encode spaces: `wttr.in/New+York`
- Chinese output: add `&lang=zh`
- Today only: `?1` · Current only: `?0`
