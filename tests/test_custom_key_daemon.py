from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import custom_key_daemon as daemon  # noqa: E402


def make_config(**voice_overrides):
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    voice = {
        "enabled": True,
        "input_device": "/dev/input/event11",
        "input_name": "keyd virtual keyboard",
        "trigger_code": 193,
        "trigger_name": "voice",
        "trigger_mode": "hold",
        "recordings_dir": str(base / "recordings"),
        "asr_project_dir": str(base / "asr"),
        "model_dir": str(base / "model"),
        "language": "Chinese",
        "min_record_seconds": 0.25,
        "pw_record": {"rate": 16000, "channels": 1, "format": "s16"},
        "type_command": "wtype",
        "copy_to_clipboard": False,
        "type_text": True,
        "output": {
            "backend": "fcitx5",
            "fallback": "wtype",
            "wtype_command": "wtype",
            "gdbus_command": "gdbus",
            "fcitx5_bus_name": "org.qwenvoice.Fcitx5",
            "fcitx5_object_path": "/qwenvoice",
            "fcitx5_interface": "org.qwenvoice.Fcitx5",
            "fcitx5_method": "CommitText",
            "fcitx5_timeout_seconds": 2.0,
        },
        "notify": False,
        "notify_timeout_ms": 1200,
        "strip_trailing_punctuation": False,
    }
    voice.update(voice_overrides)
    cfg = daemon.Config(
        log_file=str(base / "daemon.log"),
        voice=daemon.VoiceConfig(**voice),
        eye_care=daemon.EyeCareConfig(
            enabled=True,
            input_device="/dev/input/event6",
            input_name="Ideapad extra buttons",
            trigger_code=202,
            trigger_name="eye",
            trigger_on="press",
            debounce_seconds=0.8,
            command=str(base / "toggle-eye-care"),
            notify=False,
            notify_timeout_ms=1200,
        ),
    )
    return tmp, cfg


class ConfigLoadingTests(unittest.TestCase):
    def test_load_config_adds_output_for_legacy_config(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            raw = {
                "log_file": str(Path(td) / "daemon.log"),
                "voice": {
                    "enabled": True,
                    "input_device": "/dev/input/event1",
                    "input_name": "keyboard",
                    "trigger_code": 193,
                    "trigger_name": "voice",
                    "trigger_mode": "hold",
                    "recordings_dir": str(Path(td) / "recordings"),
                    "asr_project_dir": str(Path(td) / "asr"),
                    "model_dir": str(Path(td) / "model"),
                    "language": "Chinese",
                    "min_record_seconds": 0.25,
                    "pw_record": {"rate": 16000, "channels": 1, "format": "s16"},
                    "type_command": "wtype",
                    "copy_to_clipboard": False,
                    "type_text": True,
                    "notify": False,
                    "notify_timeout_ms": 1200,
                    "strip_trailing_punctuation": False,
                },
                "eye_care": {
                    "enabled": True,
                    "input_device": "/dev/input/event2",
                    "input_name": "buttons",
                    "trigger_code": 202,
                    "trigger_name": "eye",
                    "trigger_on": "press",
                    "debounce_seconds": 0.8,
                    "command": str(Path(td) / "toggle-eye-care"),
                    "notify": False,
                    "notify_timeout_ms": 1200,
                },
            }
            path.write_text(json.dumps(raw), encoding="utf-8")

            cfg = daemon.load_config(path)

            self.assertEqual(cfg.voice.output["backend"], "wtype")
            self.assertEqual(cfg.voice.output["fallback"], "none")
            self.assertEqual(cfg.voice.output["wtype_command"], "wtype")


class InputDeviceTests(unittest.TestCase):
    def test_resolve_input_device_prefers_device_name(self):
        tmp, cfg = make_config()
        with tmp:
            with mock.patch.object(
                daemon,
                "input_events_by_name",
                return_value={"keyd virtual keyboard": "/dev/input/event8"},
            ):
                resolved = daemon.resolve_input_device(
                    "/dev/input/event11", "keyd virtual keyboard", cfg
                )

            self.assertEqual(resolved, "/dev/input/event8")

    def test_resolve_input_device_falls_back_to_configured_path(self):
        tmp, cfg = make_config()
        with tmp:
            with mock.patch.object(daemon, "input_events_by_name", return_value={}):
                resolved = daemon.resolve_input_device(
                    "/dev/input/event11", "missing keyboard", cfg
                )

            self.assertEqual(resolved, "/dev/input/event11")


class OutputBackendTests(unittest.TestCase):
    def test_wtype_backend_calls_configured_command(self):
        tmp, cfg = make_config(output={"backend": "wtype", "wtype_command": "wtype"})
        with tmp:
            completed = subprocess.CompletedProcess(["wtype"], 0, stdout="", stderr="")
            with mock.patch.object(daemon, "run_checked", return_value=completed) as run:
                ok = daemon.commit_with_wtype(cfg, "hello")

            self.assertTrue(ok)
            run.assert_called_once_with(["wtype", "hello"], timeout=15)

    def test_fcitx5_backend_calls_gdbus_commit_text(self):
        tmp, cfg = make_config()
        with tmp:
            completed = subprocess.CompletedProcess(["gdbus"], 0, stdout="(true,)\n", stderr="")
            with mock.patch.object(daemon, "run_checked", return_value=completed) as run:
                ok = daemon.commit_with_fcitx5(cfg, "你好")

            self.assertTrue(ok)
            args = run.call_args.args[0]
            self.assertEqual(args[:4], ["gdbus", "call", "--session", "--dest"])
            self.assertIn("org.qwenvoice.Fcitx5", args)
            self.assertIn("/qwenvoice", args)
            self.assertIn("org.qwenvoice.Fcitx5.CommitText", args)
            self.assertEqual(args[-1], "你好")

    def test_fcitx5_backend_false_response_fails(self):
        tmp, cfg = make_config()
        with tmp:
            completed = subprocess.CompletedProcess(["gdbus"], 0, stdout="(false,)\n", stderr="")
            with mock.patch.object(daemon, "run_checked", return_value=completed):
                self.assertFalse(daemon.commit_with_fcitx5(cfg, "hello"))

    def test_insert_text_falls_back_from_fcitx5_to_wtype(self):
        tmp, cfg = make_config()
        with tmp:
            calls: list[list[str]] = []

            def fake_run_checked(args, **kwargs):
                calls.append(args)
                if args[0] == "gdbus":
                    return subprocess.CompletedProcess(args, 1, stdout="", stderr="no service")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with mock.patch.object(daemon, "run_checked", side_effect=fake_run_checked):
                daemon.insert_text(cfg, "fallback text")

            self.assertEqual(calls[0][0], "gdbus")
            self.assertEqual(calls[1], ["wtype", "fallback text"])

    def test_clipboard_timeout_does_not_raise(self):
        tmp, cfg = make_config(copy_to_clipboard=True)
        with tmp:
            with mock.patch.object(
                daemon,
                "run_checked",
                side_effect=subprocess.TimeoutExpired(["wl-copy"], 2),
            ):
                daemon.copy_to_clipboard(cfg, "hello")


if __name__ == "__main__":
    unittest.main()
