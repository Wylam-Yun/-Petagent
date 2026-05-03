# PetAgent / Momo

PetAgent 是运行在旧安卓手机上的表情包式 AI 桌宠 runtime。第一阶段先做 Momo 的生命感闭环：大号 kaomoji 表情、触摸反馈、基础养成状态、LLM 短回复和可爱风 TTS。

## Stage 1

- 后端：FastAPI + SQLite
- 前端：React + Vite，构建后由后端静态服务托管
- LLM：`mimo-v2-omni`
- TTS：`mimo-v2.5-tts`
- 运行环境：Android Termux 手机作为 runtime，Mac 作为前端构建和开发环境

Momo 不是客服、不是普通 AI 助手，也不是女友设定。它是一只住在手机里的可爱小宠物，会根据摸头、戳脸、抱一下等事件产生短句回复、表情、动画和状态变化。

## Local Development

后端：

```bash
cd backend
../.venv/bin/python -m pytest -v
../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm test -- --run
npm run build
```

手机 runtime：

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
```

## Secrets

真实 API key 只放本地 `.env`，不要提交到 GitHub。`.env.example` 只保留空 key、base URL 和模型配置示例。
