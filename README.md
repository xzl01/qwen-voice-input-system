# Qwen Voice Input System

Arch Linux / niri 环境下的本地语音输入与自定义硬件键监听配置。

当前仓库是从正在运行的本机配置整理出来的版本化副本。它不会直接替代系统中的运行文件；实际部署位置可按需设置，例如：

```text
<HOME>/AI/CustomKeyDaemon/
<HOME>/.config/systemd/user/custom-key-daemon.service
```

## 当前功能

- 统一用户级按键监听：`custom-key-daemon.service`
- 语音输入：按住 Lenovo 语音键录音，松开后 Qwen3-ASR 转写，并通过 fcitx5 addon 或 `wtype` 上屏
- 护眼模式：按护眼键触发 `<HOME>/.local/bin/toggle-eye-care`
- 重启后按设备名动态解析 `/dev/input/event*`，避免 event 编号漂移

## 仓库结构

```text
.
├── src/
│   └── custom_key_daemon.py
├── config/
│   └── config.json
├── scripts/
│   ├── run.sh
│   └── key-listener.py
├── systemd/user/
│   └── custom-key-daemon.service
├── contrib/fcitx5-qwen-voice/
│   ├── CMakeLists.txt
│   ├── qwenvoicefcitx5.cpp
│   ├── qwenvoicefcitx5.conf
│   ├── install-user.sh
│   └── README.md
├── legacy/systemd/user/
│   ├── eye-key-listener.service
│   └── qwen-voice-input.service
└── docs/
    ├── qwen-voice-input-arch-niri.md
    ├── system-changes-summary-2026-05-12.md
    └── system-changes-summary-2026-05-12.html
```

## 当前按键配置

```text
语音输入：
  input_name: keyd virtual keyboard
  fallback:   /dev/input/event11
  code:       193
  mode:       hold

护眼模式：
  input_name: Ideapad extra buttons
  fallback:   /dev/input/event6
  code:       202
  trigger:    press
```

## 自检

在当前运行目录自检：

```bash
<HOME>/AI/CustomKeyDaemon/run.sh --self-test
```

如果要从仓库副本运行，需要先确认 `scripts/run.sh` 里的路径是否符合你的安装位置。

## 单元测试

测试使用 Python 标准库 `unittest`，不依赖 pytest：

```bash
python -m unittest discover -s tests -v
```

当前覆盖：

- 旧配置自动补齐 `output` 字段
- `input_name` 优先解析当前 `/dev/input/event*`
- fcitx5 backend 的 `gdbus CommitText` 调用参数
- fcitx5 返回失败时 fallback 到 `wtype`
- `wl-copy` 超时不会抛出异常阻断主链路

基础静态验证：

```bash
python -m py_compile src/custom_key_daemon.py scripts/key-listener.py tests/test_custom_key_daemon.py
python -m json.tool config/config.json >/dev/null
```

## 输出后端

当前支持：

```text
fcitx5    通过 fcitx5 addon 的 D-Bus CommitText 提交文字
wtype     通过 wtype 直接向当前聚焦窗口输入文字
clipboard 仅复制到剪贴板
none      不输出文字，仅保留日志
```

默认推荐：

```json
{
  "output": {
    "backend": "fcitx5",
    "fallback": "wtype"
  }
}
```

如果 fcitx5 addon 不可用，daemon 会回退到 `wtype`。

## fcitx5 addon

addon 位于：

```text
contrib/fcitx5-qwen-voice/
```

它只负责把文本提交到 fcitx5 当前输入上下文，不负责录音、ASR 或快捷键监听。

安装并重启 fcitx5：

```bash
cd contrib/fcitx5-qwen-voice
./install-user.sh
./restart-fcitx5.sh
```

手动测试：

```bash
gdbus call --session \
  --dest org.qwenvoice.Fcitx5 \
  --object-path /qwenvoice \
  --method org.qwenvoice.Fcitx5.CommitText \
  'hello from qwen voice'
```

## 服务管理

当前系统服务：

```bash
systemctl --user status custom-key-daemon.service --no-pager
journalctl --user -u custom-key-daemon.service -f
```

当前已停用的旧服务：

```text
qwen-voice-input.service
eye-key-listener.service
```

## 注意

- 本仓库不包含 Qwen3-ASR 模型文件。
- 本仓库不包含录音缓存。
- `config/config.json` 使用 `<HOME>`、`<ASR_PROJECT>`、`<MODEL_DIR>` 等占位符，部署前需要替换为本机实际路径。
- 不建议把 `/etc/keyd` 系统级配置纳入本仓库；当前最终方案不依赖修改 keyd 系统配置。
