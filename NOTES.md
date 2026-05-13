# 设计备注

## 为什么按设备名解析 input event

重启后 `/dev/input/event*` 编号可能变化。曾出现：

```text
keyd virtual keyboard -> /dev/input/event8
keyd virtual pointer  -> /dev/input/event11
```

如果配置写死 `/dev/input/event11`，语音输入会监听到错误设备。

当前 `custom_key_daemon.py` 会先读取 `/proc/bus/input/devices`，按 `input_name` 找到真实 event 路径；找不到时才回退到 `input_device`。

## 为什么关闭 copy_to_clipboard

曾出现：

```text
Transcription failed: TimeoutExpired(['wl-copy'], 5)
```

这说明转写成功后 `wl-copy` 超时阻塞，导致 `wtype` 没有执行。当前配置：

```json
"copy_to_clipboard": false
```

## 资源占用

Python 按键监听本身资源占用低；常驻内存主要来自启动时加载 Qwen3-ASR 模型。未来可考虑懒加载 ASR。
