---
name: weather
description: 查询中国城市天气（免费，无需API密钥）。支持城市名查天气。
trigger: tool
executor: sandbox
metadata: { "openclaw": { "emoji": "🌤️", "requires": { "bins": ["curl"] } } }
---

# Weather

使用 t.weather.sojson.com 免费 API 查询天气。返回 JSON，包含温度、湿度、风向等。

## 城市代码映射

常用城市代码（citykey）：
- 北京: 101010100
- 上海: 101020100
- 广州: 101280101
- 深圳: 101280601
- 杭州: 101210101
- 成都: 101270101
- 武汉: 101200101
- 南京: 101190101
- 重庆: 101040100
- 西安: 101110101
- 天津: 101030100
- 苏州: 101190401
- 长沙: 101250101
- 厦门: 101230201

## Rules for generating commands

1. **User specifies a city** → 查找对应的 citykey，使用 API 查询
2. **No city specified** → 默认使用北京 (101010100)
3. **Always add `--connect-timeout 5`** to prevent hanging
4. **Always add a fallback** with `||` — if curl fails, echo an error message
5. **用 jq 或 python 提取关键数据**（如没有 jq，直接返回原始 JSON 也可以）

## Patterns

### 基本查询（返回精简数据）

```bash
curl -s --connect-timeout 5 "http://t.weather.sojson.com/api/weather/city/101010100" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('status')==200:
    ci=d['cityInfo']
    t=d['data']
    f=t['forecast'][0]
    print(f\"{ci['city']} {f['ymd']} {f['week']}\")
    print(f\"天气: {f['type']} | {f['low']}~{f['high']}\")
    print(f\"湿度: {t['shidu']} | 风: {f['fx']}{f['fl']}\")
    print(f\"PM2.5: {t['pm25']} 空气: {t['quality']}\")
    print(f\"提示: {t['ganmao']}\")
else:
    print('天气查询失败')
" || echo "天气查询暂时不可用，请稍后再试"
```

### 上海天气

```bash
curl -s --connect-timeout 5 "http://t.weather.sojson.com/api/weather/city/101020100" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if d.get('status')==200:
    ci=d['cityInfo']
    t=d['data']
    f=t['forecast'][0]
    print(f\"{ci['city']} {f['ymd']} {f['week']}\")
    print(f\"天气: {f['type']} | {f['low']}~{f['high']}\")
    print(f\"湿度: {t['shidu']} | 风: {f['fx']}{f['fl']}\")
    print(f\"PM2.5: {t['pm25']} 空气: {t['quality']}\")
    print(f\"提示: {t['ganmao']}\")
else:
    print('天气查询失败')
" || echo "天气查询暂时不可用，请稍后再试"
```

## Important notes

- API 免费，无需注册和密钥
- 返回中文数据，适合中文 persona 直接使用
- 如果用户说的城市不在上面的列表中，用最接近的大城市代替，或直接告诉用户暂不支持该城市
- `|| echo "..."` 确保 stdout 不为空
