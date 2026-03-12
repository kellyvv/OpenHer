---
name: weather
description: Get current weather and forecasts for the user's location (no API key required).
trigger: tool
executor: sandbox
homepage: https://wttr.in/:help
metadata: { "openclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Weather

Query weather using wttr.in. Commands MUST be robust — always produce stdout.

## Rules for generating commands

1. **User specifies a city** → use it directly, URL-encode spaces with `+`
2. **No city specified** → use `wttr.in/` without city (auto-detect by IP)
3. **Always add `--connect-timeout 5`** to prevent hanging
4. **Always add a fallback** with `||` — if curl fails, echo an error message
5. **Never use nested `$(...)` subshells** for city detection — too fragile

## Patterns

### User specifies a city

```bash
curl -s --connect-timeout 5 "wttr.in/Beijing?format=%l:+%c+%t+%h+%w" || echo "天气查询暂时不可用，请稍后再试"
```

Multi-word city names — URL-encode spaces with `+`:

```bash
curl -s --connect-timeout 5 "wttr.in/New+York?format=%l:+%c+%t+%h+%w" || echo "天气查询暂时不可用，请稍后再试"
```

### No city specified (auto-detect)

```bash
curl -s --connect-timeout 5 "wttr.in/?format=%l:+%c+%t+%h+%w" || echo "天气查询暂时不可用，请稍后再试"
```

### Full forecast (multi-day, Chinese)

```bash
curl -s --connect-timeout 5 "wttr.in/Shanghai?1&lang=zh" || echo "天气查询暂时不可用，请稍后再试"
```

## Format codes

`%c` condition · `%t` temperature · `%h` humidity · `%w` wind · `%l` location

## Important notes

- The `|| echo "..."` fallback ensures stdout is NEVER empty — even on network errors the persona will naturally relay the failure to the user.
- Location auto-detect may show `not found` as city name when behind VPN — this is normal, weather data is still returned.
- Do NOT use `ipinfo.io` or any IP geolocation service — it is unreliable behind VPN.
