# OpenHer Web

Standalone browser client for OpenHer. It does not modify the Python backend or persona engine.

## Run

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173` and keep the OpenHer backend running at `http://localhost:8000`.

The backend URL can be changed in the web settings panel. The value is stored in browser `localStorage`.

## Build

```bash
npm run build
```

The production output is written to `web/dist`.

## Protocol Coverage

- `GET /api/status`
- `GET /api/personas`
- `GET /api/chat/history/{persona_id}?client_id=...`
- `GET /api/persona/{persona_id}/media/{front|face|awakening|awakened}`
- `WebSocket /ws/chat`
- WebSocket events: `chat_start`, `chat_chunk`, `chat_end`, `silence`, `proactive`, `tts_audio`, `error`, `persona_switched`
