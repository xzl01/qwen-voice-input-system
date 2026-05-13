# 安装/同步说明

当前仓库是版本化副本。若要把仓库内容同步到当前系统运行位置，可手动执行以下步骤。

## 同步 CustomKeyDaemon

```bash
cp src/custom_key_daemon.py <HOME>/AI/CustomKeyDaemon/custom_key_daemon.py
cp config/config.json <HOME>/AI/CustomKeyDaemon/config.json
cp scripts/run.sh <HOME>/AI/CustomKeyDaemon/run.sh
chmod +x <HOME>/AI/CustomKeyDaemon/custom_key_daemon.py <HOME>/AI/CustomKeyDaemon/run.sh
```

将 `<HOME>`、`<ASR_PROJECT>`、`<MODEL_DIR>` 等占位符替换为本机实际路径后再运行。

`scripts/run.sh` 需要以下环境变量：

```bash
export QWEN_ASR_PROJECT=<ASR_PROJECT>
export QWEN_ASR_VENV=<VENV>
```

## 安装 fcitx5 addon（可选）

如果要使用 `output.backend = "fcitx5"`，先安装 addon：

```bash
cd contrib/fcitx5-qwen-voice
./install-user.sh
./restart-fcitx5.sh
```

然后测试 D-Bus commit：

```bash
gdbus call --session \
  --dest org.qwenvoice.Fcitx5 \
  --object-path /qwenvoice \
  --method org.qwenvoice.Fcitx5.CommitText \
  'hello from qwen voice'
```

若返回失败或 fcitx5 未运行，daemon 会按配置 fallback 到 `wtype`。

## 同步 systemd user service

```bash
cp systemd/user/custom-key-daemon.service <HOME>/.config/systemd/user/custom-key-daemon.service
systemctl --user daemon-reload
systemctl --user restart custom-key-daemon.service
```

## 验证

```bash
python -m unittest discover -s tests -v
<HOME>/AI/CustomKeyDaemon/run.sh --self-test
systemctl --user status custom-key-daemon.service --no-pager
```

## 日志

```bash
journalctl --user -u custom-key-daemon.service -f
tail -f <HOME>/.cache/custom-key-daemon/daemon.log
```
