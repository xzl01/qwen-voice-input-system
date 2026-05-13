#!/usr/bin/env python3
"""Unified user-level key daemon for local hardware keys.

Currently handles:
  - voice input: keyd virtual keyboard code 193, hold-to-record
  - eye care:    Ideapad extra buttons code 202, press-to-toggle
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import select
import signal
import struct
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


EV_KEY = 0x01
KEY_RELEASE = 0
KEY_PRESS = 1
KEY_REPEAT = 2
EVENT_FORMAT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


@dataclasses.dataclass(frozen=True)
class VoiceConfig:
    enabled: bool
    input_device: str
    input_name: str
    trigger_code: int
    trigger_name: str
    trigger_mode: str
    recordings_dir: str
    asr_project_dir: str
    model_dir: str
    language: Optional[str]
    min_record_seconds: float
    pw_record: dict
    type_command: str
    copy_to_clipboard: bool
    type_text: bool
    output: dict
    notify: bool
    notify_timeout_ms: int
    strip_trailing_punctuation: bool


@dataclasses.dataclass(frozen=True)
class EyeCareConfig:
    enabled: bool
    input_device: str
    input_name: str
    trigger_code: int
    trigger_name: str
    trigger_on: str
    debounce_seconds: float
    command: str
    notify: bool
    notify_timeout_ms: int


@dataclasses.dataclass(frozen=True)
class Config:
    log_file: str
    voice: VoiceConfig
    eye_care: EyeCareConfig


def load_config(path: Path) -> Config:
    raw = json.loads(path.read_text(encoding="utf-8"))
    voice_raw = raw["voice"]
    if "output" not in voice_raw:
        voice_raw = {
            **voice_raw,
            "output": {
                "backend": "wtype" if voice_raw.get("type_text", True) else "none",
                "fallback": "none",
                "wtype_command": voice_raw.get("type_command", "wtype"),
            },
        }
    return Config(
        log_file=raw["log_file"],
        voice=VoiceConfig(**voice_raw),
        eye_care=EyeCareConfig(**raw["eye_care"]),
    )


def log(cfg: Config, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    log_path = Path(cfg.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_checked(args: list[str], *, input_text: str | None = None, timeout: float = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def notify(title: str, body: str = "", *, enabled: bool, timeout_ms: int, cfg: Config) -> None:
    if not enabled:
        return
    args = [
        "notify-send",
        "--app-name", "Custom Key Daemon",
        "--expire-time", str(timeout_ms),
        title,
    ]
    if body:
        args.append(body)
    try:
        result = run_checked(args, timeout=3)
        if result.returncode != 0:
            log(cfg, f"notify-send failed: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        log(cfg, "notify-send timed out")


def key_state_name(state: int) -> str:
    if state == KEY_RELEASE:
        return "UP"
    if state == KEY_PRESS:
        return "DOWN"
    if state == KEY_REPEAT:
        return "REPEAT"
    return f"VALUE_{state}"


def input_events_by_name() -> dict[str, str]:
    devices: dict[str, str] = {}
    current_name: Optional[str] = None
    proc_devices = Path("/proc/bus/input/devices")
    if not proc_devices.exists():
        return devices

    for line in proc_devices.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("N: Name="):
            current_name = line.split("=", 1)[1].strip().strip('"')
            continue
        if current_name and line.startswith("H: Handlers="):
            handlers = line.split("=", 1)[1].split()
            event_handlers = [handler for handler in handlers if handler.startswith("event")]
            if event_handlers:
                devices[current_name] = f"/dev/input/{event_handlers[-1]}"
            current_name = None
    return devices


def resolve_input_device(configured_path: str, device_name: str, cfg: Config) -> str:
    if device_name:
        by_name = input_events_by_name()
        resolved = by_name.get(device_name)
        if resolved:
            if resolved != configured_path:
                log(cfg, f"Resolved input device {device_name!r}: {configured_path} -> {resolved}")
            return resolved
        log(cfg, f"Could not resolve input device name {device_name!r}; falling back to {configured_path}")
    return configured_path


def strip_punctuation(text: str) -> str:
    return text.rstrip("。．.，,、！？!?；;：:\n\r\t ")


class QwenAsr:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        voice = cfg.voice
        project_dir = Path(voice.asr_project_dir)
        bin_dir = project_dir / "qwen_asr_gguf" / "inference" / "bin"

        os.environ.setdefault("GGML_VK_DISABLE_F16", "1")
        old_ld = os.environ.get("LD_LIBRARY_PATH", "")
        if str(bin_dir) not in old_ld.split(":"):
            os.environ["LD_LIBRARY_PATH"] = f"{bin_dir}:{old_ld}" if old_ld else str(bin_dir)

        sys.path.insert(0, str(project_dir))
        from qwen_asr_gguf.inference import ASREngineConfig, QwenASREngine

        log(cfg, f"Loading Qwen3-ASR engine: {voice.model_dir}")
        self.engine = QwenASREngine(
            config=ASREngineConfig(
                model_dir=voice.model_dir,
                onnx_provider="CPU",
                llm_use_gpu=True,
                encoder_frontend_fn="qwen3_asr_encoder_frontend.int4.onnx",
                encoder_backend_fn="qwen3_asr_encoder_backend.int4.onnx",
                enable_aligner=False,
                verbose=False,
            )
        )
        log(cfg, "Qwen3-ASR engine ready")

    def transcribe(self, audio_path: Path) -> str:
        voice = self.cfg.voice
        result = self.engine.transcribe(
            audio_file=str(audio_path),
            language=voice.language,
            context="",
            start_second=0,
            duration=None,
            temperature=0.4,
        )
        text = (result.text or "").strip()
        if voice.strip_trailing_punctuation:
            text = strip_punctuation(text)
        return text

    def shutdown(self) -> None:
        self.engine.shutdown()


class Recorder:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.proc: Optional[subprocess.Popen] = None
        self.path: Optional[Path] = None
        self.started_at: float = 0.0

    def start(self) -> None:
        if self.proc is not None:
            return
        voice = self.cfg.voice
        recordings = Path(voice.recordings_dir)
        recordings.mkdir(parents=True, exist_ok=True)
        self.path = recordings / f"voice-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.wav"
        pr = voice.pw_record
        args = [
            "pw-record",
            "--rate", str(pr.get("rate", 16000)),
            "--channels", str(pr.get("channels", 1)),
            "--format", str(pr.get("format", "s16")),
            str(self.path),
        ]
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.started_at = time.monotonic()
        log(self.cfg, f"Voice recording started: {self.path}")

    def stop(self) -> Optional[Path]:
        if self.proc is None:
            return None
        voice = self.cfg.voice
        elapsed = time.monotonic() - self.started_at
        proc = self.proc
        path = self.path
        self.proc = None
        self.path = None
        proc.send_signal(signal.SIGINT)
        try:
            _, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.terminate()
            _, stderr = proc.communicate(timeout=3)
        if proc.returncode not in (0, -signal.SIGINT, 130, None):
            log(self.cfg, f"pw-record exited with {proc.returncode}: {(stderr or '').strip()}")
        if elapsed < voice.min_record_seconds:
            log(self.cfg, f"Voice recording too short ({elapsed:.2f}s), ignored")
            return None
        if path is None or not path.exists() or path.stat().st_size < 1024:
            log(self.cfg, "Voice recording missing or too small, ignored")
            return None
        log(self.cfg, f"Voice recording stopped ({elapsed:.2f}s): {path}")
        return path


def copy_to_clipboard(cfg: Config, text: str) -> None:
    voice = cfg.voice
    if not voice.copy_to_clipboard:
        return
    try:
        cp = run_checked(["wl-copy"], input_text=text, timeout=2)
        if cp.returncode != 0:
            log(cfg, f"wl-copy failed: {cp.stderr.strip()}")
    except subprocess.TimeoutExpired:
        log(cfg, "wl-copy timed out; continuing without clipboard copy")


def output_backend_name(cfg: Config) -> str:
    return str(cfg.voice.output.get("backend", "wtype")).lower().strip()


def output_fallback_name(cfg: Config) -> str:
    return str(cfg.voice.output.get("fallback", "wtype")).lower().strip()


def commit_with_wtype(cfg: Config, text: str) -> bool:
    voice = cfg.voice
    command = str(voice.output.get("wtype_command", voice.type_command or "wtype"))
    try:
        typed = run_checked([command, text], timeout=15)
    except subprocess.TimeoutExpired:
        log(cfg, f"{command} timed out")
        return False
    if typed.returncode != 0:
        log(cfg, f"{command} failed: {typed.stderr.strip()}")
        return False
    log(cfg, f"Typed text with {command}: {text}")
    return True


def commit_with_fcitx5(cfg: Config, text: str) -> bool:
    output = cfg.voice.output
    gdbus = str(output.get("gdbus_command", "gdbus"))
    bus_name = str(output.get("fcitx5_bus_name", "org.qwenvoice.Fcitx5"))
    object_path = str(output.get("fcitx5_object_path", "/qwenvoice"))
    interface = str(output.get("fcitx5_interface", "org.qwenvoice.Fcitx5"))
    method = str(output.get("fcitx5_method", "CommitText"))
    timeout = float(output.get("fcitx5_timeout_seconds", 2.0))
    try:
        result = run_checked(
            [
                gdbus,
                "call",
                "--session",
                "--dest", bus_name,
                "--object-path", object_path,
                "--method", f"{interface}.{method}",
                text,
            ],
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log(cfg, "fcitx5 commit timed out")
        return False
    if result.returncode != 0:
        log(cfg, f"fcitx5 commit failed: {result.stderr.strip()}")
        return False
    if "false" in result.stdout.lower():
        log(cfg, f"fcitx5 commit returned false: {result.stdout.strip()}")
        return False
    log(cfg, f"Committed text with fcitx5: {text}")
    return True


def commit_text(cfg: Config, text: str, backend: str) -> bool:
    if backend in {"", "none", "off", "disabled"}:
        log(cfg, "Output backend disabled; text not inserted")
        return True
    if backend == "wtype":
        return commit_with_wtype(cfg, text)
    if backend == "fcitx5":
        return commit_with_fcitx5(cfg, text)
    if backend == "clipboard":
        original = cfg.voice.copy_to_clipboard
        if original:
            copy_to_clipboard(cfg, text)
            return True
        log(cfg, "clipboard backend requested but copy_to_clipboard is false")
        return False
    log(cfg, f"Unsupported output backend: {backend!r}")
    return False


def insert_text(cfg: Config, text: str) -> None:
    if not text:
        log(cfg, "Empty transcription, nothing to insert")
        return
    copy_to_clipboard(cfg, text)
    if not cfg.voice.type_text:
        log(cfg, f"Copied text only: {text}")
        return
    backend = output_backend_name(cfg)
    if commit_text(cfg, text, backend):
        return
    fallback = output_fallback_name(cfg)
    if fallback and fallback != backend and fallback not in {"none", "off", "disabled"}:
        log(cfg, f"Trying fallback output backend: {fallback}")
        commit_text(cfg, text, fallback)


def stop_transcribe_insert(recorder: Recorder, asr: QwenAsr, cfg: Config) -> None:
    voice = cfg.voice
    audio = recorder.stop()
    if audio is None:
        notify("语音输入已取消", "录音太短或没有音频", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
        return
    try:
        notify("正在转写…", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
        text = asr.transcribe(audio)
        log(cfg, f"Transcribed: {text}")
        notify("语音输入完成", text[:80] if text else "未识别到文字", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
        insert_text(cfg, text)
    except Exception as exc:
        log(cfg, f"Transcription failed: {exc!r}")
        notify("语音输入失败", repr(exc)[:120], enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)


def toggle_eye_care(cfg: Config) -> None:
    eye = cfg.eye_care
    log(cfg, f"Eye-care trigger: running {eye.command}")
    try:
        result = run_checked([eye.command], timeout=10)
    except subprocess.TimeoutExpired:
        log(cfg, "Eye-care command timed out")
        notify("护眼模式失败", "toggle-eye-care timeout", enabled=eye.notify, timeout_ms=eye.notify_timeout_ms, cfg=cfg)
        return
    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        log(cfg, f"Eye-care command failed: {err}")
        notify("护眼模式失败", err[:120], enabled=eye.notify, timeout_ms=eye.notify_timeout_ms, cfg=cfg)
        return
    notify("护眼模式已切换", enabled=eye.notify, timeout_ms=eye.notify_timeout_ms, cfg=cfg)


def open_device(path: str) -> int:
    return os.open(path, os.O_RDONLY | os.O_NONBLOCK)


def self_test(cfg: Config) -> int:
    checks = []
    voice = cfg.voice
    eye = cfg.eye_care
    voice_device = resolve_input_device(voice.input_device, voice.input_name, cfg) if voice.enabled else ""
    eye_device = resolve_input_device(eye.input_device, eye.input_name, cfg) if eye.enabled else ""
    if voice.enabled:
        checks.extend([
            (Path(voice_device).exists(), f"voice input device exists: {voice_device} ({voice.input_name})"),
            (os.access(voice_device, os.R_OK), f"voice input device readable: {voice_device} ({voice.input_name})"),
            (Path(voice.asr_project_dir).exists(), f"ASR project exists: {voice.asr_project_dir}"),
            (Path(voice.model_dir).exists(), f"model dir exists: {voice.model_dir}"),
            (subprocess.call(["which", "pw-record"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "pw-record available"),
            (output_backend_name(cfg) != "wtype" or subprocess.call(["which", str(voice.output.get("wtype_command", voice.type_command))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "wtype backend command available if enabled"),
            (output_backend_name(cfg) != "fcitx5" or subprocess.call(["which", str(voice.output.get("gdbus_command", "gdbus"))], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "gdbus available if fcitx5 backend enabled"),
            (not voice.copy_to_clipboard or subprocess.call(["which", "wl-copy"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "wl-copy available if enabled"),
        ])
    if eye.enabled:
        checks.extend([
            (Path(eye_device).exists(), f"eye-care input device exists: {eye_device} ({eye.input_name})"),
            (os.access(eye_device, os.R_OK), f"eye-care input device readable: {eye_device} ({eye.input_name})"),
            (Path(eye.command).exists(), f"eye-care command exists: {eye.command}"),
            (os.access(eye.command, os.X_OK), f"eye-care command executable: {eye.command}"),
        ])
    if (voice.enabled and voice.notify) or (eye.enabled and eye.notify):
        checks.append((subprocess.call(["which", "notify-send"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0, "notify-send available"))

    ok = True
    for passed, name in checks:
        print(("✅" if passed else "❌"), name)
        ok = ok and passed
    return 0 if ok else 1


def iter_events(cfg: Config):
    bindings: dict[int, tuple[str, int]] = {}
    fds: list[int] = []
    if cfg.voice.enabled:
        voice_device = resolve_input_device(cfg.voice.input_device, cfg.voice.input_name, cfg)
        fd = open_device(voice_device)
        bindings[fd] = ("voice", cfg.voice.trigger_code)
        fds.append(fd)
        log(cfg, f"Listening voice: {cfg.voice.trigger_name} code={cfg.voice.trigger_code} mode={cfg.voice.trigger_mode} on {voice_device} ({cfg.voice.input_name})")
    if cfg.eye_care.enabled:
        eye_device = resolve_input_device(cfg.eye_care.input_device, cfg.eye_care.input_name, cfg)
        fd = open_device(eye_device)
        bindings[fd] = ("eye_care", cfg.eye_care.trigger_code)
        fds.append(fd)
        log(cfg, f"Listening eye-care: {cfg.eye_care.trigger_name} code={cfg.eye_care.trigger_code} on {eye_device} ({cfg.eye_care.input_name})")

    poller = select.poll()
    for fd in fds:
        poller.register(fd, select.POLLIN)

    try:
        while True:
            for fd, _event in poller.poll():
                try:
                    data = os.read(fd, EVENT_SIZE * 16)
                except BlockingIOError:
                    continue
                name, trigger_code = bindings[fd]
                for offset in range(0, len(data), EVENT_SIZE):
                    chunk = data[offset:offset + EVENT_SIZE]
                    if len(chunk) != EVENT_SIZE:
                        continue
                    _sec, _usec, event_type, event_code, event_value = struct.unpack(EVENT_FORMAT, chunk)
                    if event_type == EV_KEY and event_code == trigger_code:
                        yield name, event_value
    finally:
        for fd in fds:
            os.close(fd)


def run_daemon(cfg: Config) -> int:
    recorder = Recorder(cfg)
    asr = QwenAsr(cfg) if cfg.voice.enabled else None
    last_eye_at = 0.0
    try:
        for name, state in iter_events(cfg):
            if name == "voice":
                voice = cfg.voice
                log(cfg, f"Voice trigger event: {key_state_name(state)} ({state})")
                mode = voice.trigger_mode.lower().strip()
                if mode == "hold":
                    if state in {KEY_PRESS, KEY_REPEAT} and recorder.proc is None:
                        recorder.start()
                        notify("正在录音…", "松开按键后转写", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
                    elif state == KEY_RELEASE:
                        notify("录音结束", "开始转写", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
                        if asr is not None:
                            stop_transcribe_insert(recorder, asr, cfg)
                elif mode == "toggle" and state == KEY_PRESS:
                    if recorder.proc is None:
                        recorder.start()
                        notify("正在录音…", "再次按键后转写", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
                    else:
                        notify("录音结束", "开始转写", enabled=voice.notify, timeout_ms=voice.notify_timeout_ms, cfg=cfg)
                        if asr is not None:
                            stop_transcribe_insert(recorder, asr, cfg)
                else:
                    log(cfg, f"Unsupported voice trigger_mode={voice.trigger_mode!r}")
            elif name == "eye_care":
                eye = cfg.eye_care
                log(cfg, f"Eye-care trigger event: {key_state_name(state)} ({state})")
                should_trigger = (
                    (eye.trigger_on == "press" and state == KEY_PRESS)
                    or (eye.trigger_on == "release" and state == KEY_RELEASE)
                )
                now = time.monotonic()
                if should_trigger and now - last_eye_at >= eye.debounce_seconds:
                    last_eye_at = now
                    toggle_eye_care(cfg)
    finally:
        if recorder.proc is not None:
            recorder.stop()
        if asr is not None:
            asr.shutdown()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified user-level custom key daemon")
    default_config = Path(__file__).resolve().parents[1] / "config" / "config.json"
    parser.add_argument("--config", default=str(default_config))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    if args.self_test:
        return self_test(cfg)
    return run_daemon(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
