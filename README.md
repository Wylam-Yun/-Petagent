# Petagent

Petagent 是一个情绪感知型小桌宠原型项目。

当前阶段先聚焦声音交互：

- 使用 `mimo-v2-omni` 做语音理解、情绪判断和意图识别
- 暂时不接入摄像头、屏幕共享或画面理解
- 后续会加入小a的人格、对话策略、语音回复和桌宠状态表现

## 当前目标

先把手机 Termux 作为可长期运行的开发与测试环境，跑通：

1. 麦克风音频输入
2. 分段语音理解
3. 情绪与意图判断
4. 小a的语音回复
5. 后续再扩展到桌面宠物表现层

## Runtime

项目目前初始化在 Android Termux 环境中：

- Python 3.8
- Git
- GitHub remote: `https://github.com/Wylam-Yun/-Petagent.git`

## Notes

这是早期原型。当前优先保证链路简单、稳定、容易调试，再逐步加复杂能力。
