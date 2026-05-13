# Qwen Voice Input System

Arch Linux / niri 环境下的本地语音输入与自定义硬件键监听配置。

当前仓库是从正在运行的本机配置整理出来的版本化副本。它不会直接替代系统中的运行文件；实际部署位置可按需设置，例如：

```text
<HOME>/AI/CustomKeyDaemon/
<HOME>/.config/systemd/user/custom-key-daemon.service
```

## 当前功能

- 统一用户级按键监听：`custom-key-daemon.service`
- 语音输入：按住 Lenovo 语音键录音，松开后 Qwen3-ASR 转写并用 `wtype` 上屏
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
- `config/config.json` 仍含有本机绝对路径，迁移到其它机器前需要修改。
- 不建议把 `/etc/keyd` 系统级配置纳入本仓库；当前最终方案不依赖修改 keyd 系统配置。
