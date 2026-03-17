---
name: 静默
description: >
  角色选择不回复。客户端不显示任何消息气泡。
  引擎状态（drives、Hebbian）正常更新，connection frustration 自然积累，
  由 proactive 系统在合适时机自动破冰。
trigger: modality
modality: 静默
tools: []
---

# 静默

角色选择沉默。不需要生成任何内容。

输出固定 JSON：

```json
{"suppress_reply": true}
```
