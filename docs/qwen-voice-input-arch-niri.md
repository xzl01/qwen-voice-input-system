# Qwen3-ASR 语音输入工具（脱敏版）

本文是 Arch Linux / niri / Wayland 环境下本地语音输入方案的脱敏说明。所有个人路径、用户名、精确会话变量和临时设备号均已改为占位符。

## 当前方案

- ASR：Qwen3-ASR-GGUF 1.7B，本地推理。
- GPU：通过 GGUF/Vulkan 路线加速。
- 触发：用户级 evdev 监听器读取硬件键事件。
- 输入：按住语音键录音，松开后转写，并通过 fcitx5 addon 或 `wtype` 上屏。
- 屏幕提示：`notify-send`。
- 剪贴板复制：默认关闭，避免 `wl-copy` 超时阻塞上屏。

## 目录约定

本文档使用以下占位符：

```text
<HOME>        用户家目录
<REPO_DIR>    本仓库目录，例如 <HOME>/AI/qwen-voice-input-system
<ASR_PROJECT> Qwen3-ASR-GGUF 项目目录
<MODEL_DIR>   Qwen3-ASR-GGUF 1.7B 模型目录
<VENV>        Python 虚拟环境目录
<UID>         当前用户 UID
<eventN>      当前系统启动后的 /dev/input/event* 编号
```

## 关键文件

```text
src/custom_key_daemon.py             统一用户级按键监听器
config/config.json                   监听键、模型路径、输出方式配置
scripts/run.sh                       启动脚本
scripts/key-listener.py              evdev 按键调试脚本
systemd/user/custom-key-daemon.service
contrib/fcitx5-qwen-voice/           可选 fcitx5 commit addon
```

## 统一监听器

当前推荐使用统一服务：

```text
custom-key-daemon.service
```

它统一处理：

```text
语音输入：按住 -> 录音；松开 -> 转写并上屏
护眼模式：按下 -> 执行护眼模式切换脚本
```

## 设备解析策略

不要长期依赖固定 `/dev/input/eventN` 编号，因为重启后 event 编号可能变化。

统一 daemon 会优先通过 `/proc/bus/input/devices` 按设备名解析实际 event 路径：

```json
{
  "input_name": "keyd virtual keyboard",
  "input_device": "/dev/input/eventN"
}
```

其中 `input_device` 只是 fallback；真实监听路径以启动日志中的解析结果为准。

## 运行

```bash
scripts/run.sh --self-test
scripts/run.sh
```

系统服务：

```bash
systemctl --user status custom-key-daemon.service --no-pager
journalctl --user -u custom-key-daemon.service -f
```

## 调试按键

```bash
scripts/key-listener.py
scripts/key-listener.py /dev/input/<eventN>
```

按下目标键时应看到：

```text
code=<KEY_CODE> DOWN
code=<KEY_CODE> REPEAT
code=<KEY_CODE> UP
```

## 语音输入自检

单元测试：

```bash
python -m unittest discover -s tests -v
```

```bash
scripts/run.sh --self-test
```

应检查：

```text
voice input device exists/readable
ASR project exists
model dir exists
pw-record available
wtype available
notify-send available
```

## 手动录音与转写测试

```bash
pw-record --rate 16000 --channels 1 --format s16 /tmp/qwen-test.wav
scripts/run.sh --transcribe-file /tmp/qwen-test.wav
```

如果录音和转写能单独跑通，但按键触发失败，优先检查 `input_name` 和当前 `/dev/input/event*` 映射。

## fcitx5 输出后端

可选安装 `contrib/fcitx5-qwen-voice`，让 daemon 通过 D-Bus 调用 fcitx5 addon：

```text
org.qwenvoice.Fcitx5 /qwenvoice CommitText(text) -> bool
```

推荐配置：

```json
"output": {
  "backend": "fcitx5",
  "fallback": "wtype"
}
```

如果 addon 不可用，daemon 会回退到 `wtype`。

## 已知踩坑

### event 编号会漂移

重启后同一个物理/虚拟设备的 `/dev/input/eventN` 可能改变。解决方式是按 `input_name` 动态解析。

### `wl-copy` 可能阻塞

曾遇到 `wl-copy` 超时阻塞，导致转写成功但没有执行 `wtype`。当前默认：

```json
"copy_to_clipboard": false
```

### Python 常驻内存

Python evdev 监听本身占用很低；常驻内存主要来自启动时加载 ASR 模型。若需要降低空闲内存，可改为 ASR 懒加载。
