# PetAgent / Momo

PetAgent 是运行在旧安卓手机上的表情包式 AI 桌宠 runtime。当前阶段已经具备 Momo 的生命感闭环和按住说话闭环：大号 kaomoji 表情、触摸反馈、基础养成状态、语音理解、LLM 短回复和可爱风 TTS。

## Stage 1

- 后端：FastAPI + SQLite
- 前端：React + Vite，构建后由后端静态服务托管
- LLM：`mimo-v2-omni`
- TTS：`mimo-v2.5-tts`
- 运行环境：Android Termux 手机作为 runtime，Mac 作为前端构建和开发环境

Momo 不是客服、不是普通 AI 助手，也不是女友设定。它是一只住在手机里的可爱小宠物，会根据摸头、戳脸、抱一下等事件产生短句回复、表情、动画和状态变化。

## Stage 2

- 语音：浏览器按住说话，前端优先用 Web Audio 录成 `audio/wav`，后端仍兼容 `audio/webm` / `audio/mpeg` / `audio/mp4`
- 音频理解：`mimo-v2-omni` 直接理解语音内容、语气和情绪
- 激活：前台页面内支持 `hi momo` 唤醒和 `momo休息吧` 退出
- 兜底：静音、过短、低置信度或 provider 失败时返回 `uncertain`，Momo 不胡编
- 体验：UI 有 `listening` / `thinking` / `speaking` / `error` 状态

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

## Voice Testing Notes

浏览器麦克风需要安全上下文。Mac Chrome 打开 `http://手机局域网IP:8000/` 时，页面可以显示，但通常不会允许麦克风。

Mac 上测试语音链路可以走 SSH 本地端口转发：

```bash
ssh -N -L 8000:127.0.0.1:8000 nubia
```

然后在 Mac 打开 `http://127.0.0.1:8000/`。这会使用 Mac 的麦克风。

手机本机测试要在 nubia 的浏览器打开：

```text
http://127.0.0.1:8000/
```

Android 6 时代的浏览器不一定支持现代 ES module，所以前端构建包含 legacy bundle，避免旧浏览器只看到空白页。

Via 等轻量浏览器会依赖系统 WebView。旧 WebView 产出的 `webm/opus` 可能能上传但不能被 MiMo 稳定理解，所以网页录音会优先封装成标准 WAV 再上传。

## Secrets

真实 API key 只放本地 `.env`，不要提交到 GitHub。`.env.example` 只保留空 key、base URL 和模型配置示例。
