# fcitx5-qwen-voice

Small fcitx5 addon that exposes a session D-Bus method for committing transcribed text into the focused input context.

It intentionally does **not** record audio, run ASR, or capture hotkeys. Those remain in `src/custom_key_daemon.py`.

## D-Bus API

```text
Bus name:    org.qwenvoice.Fcitx5
Object path: /qwenvoice
Interface:   org.qwenvoice.Fcitx5
Method:      CommitText(string text) -> bool
```

## Build and install for current user

```bash
./install-user.sh
./restart-fcitx5.sh
```

Required development packages vary by distro, but usually include:

```text
cmake
pkg-config
fcitx5 development headers / Fcitx5Core / Fcitx5Utils / Fcitx5Module
```

## Manual test

```bash
gdbus call --session \
  --dest org.qwenvoice.Fcitx5 \
  --object-path /qwenvoice \
  --method org.qwenvoice.Fcitx5.CommitText \
  'hello from qwen voice'
```

Expected result:

```text
(true,)
```
