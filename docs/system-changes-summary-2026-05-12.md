# 系统更改汇总（脱敏版）

本文记录本地语音输入与自定义硬件键监听相关改动。个人用户名、绝对路径、精确 input event 编号和图形会话变量已脱敏。

## 总体结果

- 建立了本地 Qwen3-ASR-GGUF 语音输入方案。
- 将语音听写按键监听和护眼模式按键监听合并为一个用户级服务。
- 统一服务名称：`custom-key-daemon.service`。
- 旧的单独语音输入服务和旧的护眼监听服务保留为 legacy，但默认停用。
- 新增了按键调试脚本和运维文档。

## 目录占位符

```text
<HOME>        用户家目录
<REPO_DIR>    本仓库目录
<ASR_PROJECT> Qwen3-ASR-GGUF 项目目录
<MODEL_DIR>   Qwen3-ASR-GGUF 模型目录
<VENV>        Python 虚拟环境目录
<UID>         当前用户 UID
<eventN>      当前启动中的 /dev/input/event* 编号
```

## 仓库内容

```text
src/custom_key_daemon.py
config/config.json
scripts/run.sh
scripts/key-listener.py
systemd/user/custom-key-daemon.service
legacy/systemd/user/qwen-voice-input.service
legacy/systemd/user/eye-key-listener.service
docs/
```

## 统一服务

```text
custom-key-daemon.service enabled / active
```

常用命令：

```bash
systemctl --user status custom-key-daemon.service --no-pager
systemctl --user restart custom-key-daemon.service
journalctl --user -u custom-key-daemon.service -f
```

## 语音输入

功能：

```text
按住语音键 -> pw-record 录音
松开语音键 -> Qwen3-ASR-GGUF 转写 -> wtype 上屏
```

关键配置示例：

```json
{
  "voice": {
    "enabled": true,
    "input_name": "keyd virtual keyboard",
    "input_device": "/dev/input/eventN",
    "trigger_code": 193,
    "trigger_mode": "hold",
    "asr_project_dir": "<ASR_PROJECT>",
    "model_dir": "<MODEL_DIR>",
    "type_command": "wtype",
    "copy_to_clipboard": false,
    "notify": true
  }
}
```

## 护眼模式

功能：

```text
按下护眼键 -> 执行 toggle-eye-care
```

关键配置示例：

```json
{
  "eye_care": {
    "enabled": true,
    "input_name": "Ideapad extra buttons",
    "input_device": "/dev/input/eventN",
    "trigger_code": 202,
    "trigger_on": "press",
    "debounce_seconds": 0.8,
    "command": "<HOME>/.local/bin/toggle-eye-care"
  }
}
```

## keyd / niri 分工

- keyd：只做底层重映射，不建议把应用逻辑放进 keyd。
- niri：只保留窗口管理器快捷键。
- custom-key-daemon：处理需要按键状态机的用户级硬件键逻辑。

## 调试脚本

```bash
scripts/key-listener.py
scripts/key-listener.py /dev/input/<eventN>
```

用于确认按键是否产生 `DOWN`、`REPEAT`、`UP` 事件，以及实际 key code。

## 运行环境

`scripts/run.sh` 设置：

```bash
export GGML_VK_DISABLE_F16=1
export LD_LIBRARY_PATH="<ASR_PROJECT>/qwen_asr_gguf/inference/bin:${LD_LIBRARY_PATH:-}"
exec <VENV>/bin/python3 src/custom_key_daemon.py "$@"
```

## 已知决策

- 默认关闭剪贴板复制，避免 `wl-copy` 超时影响 `wtype` 上屏。
- 通过设备名解析 event，避免重启后 `/dev/input/eventN` 漂移。
- 旧服务保留在 `legacy/` 下用于回退参考。
- 不把模型文件、录音文件、日志文件纳入仓库。

## 验证命令

```bash
scripts/run.sh --self-test
python -m py_compile src/custom_key_daemon.py scripts/key-listener.py
```
