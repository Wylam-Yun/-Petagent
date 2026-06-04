# PetAgent Lightweight Chain and API Switch Implementation Plan

> Scope: remove proxy/dead voice-chain remnants, add local SiliconFlow API update UI, move the main UI upward, and stabilize kaomoji rendering. Wake-by-name/background launch is explicitly out of scope.

## Tasks

- Remove provider proxy configuration and Termux proxy supervision so API calls are direct.
- Keep the single `/api/voice/chat` ASR -> LLM -> TTS path and delete unused audio-understanding route code from `VoicePipeline` wiring.
- Add a loopback-only runtime endpoint that accepts a new SiliconFlow API key/base URL, updates process providers, and writes `.env` without exposing secrets.
- Add a frontend "更换 API" button beside "重新认识", with a small modal for entering the new SiliconFlow settings.
- Remove visible "PetAgent" / "豆豆" title text from the stage and tighten spacing so controls move upward.
- Replace long/unstable kaomoji with short, single-line expressions that render reliably on old WebView.
- Run focused backend and frontend tests; keep generated artifacts out of git.
