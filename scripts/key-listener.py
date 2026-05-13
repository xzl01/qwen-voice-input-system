#!/usr/bin/env python3
"""Listen to Linux evdev keyboard key events.

Usage:
  ./key-listener.py
  ./key-listener.py /dev/input/event6
  ./key-listener.py /dev/input/event3 /dev/input/event6

This works on Wayland/niri because it reads /dev/input/event* directly.
You need read permission for the input devices, usually via the `input` group.
"""

from __future__ import annotations

import glob
import os
import select
import struct
import sys
from dataclasses import dataclass
from datetime import datetime


EV_KEY = 0x01
EVENT_FORMAT = "llHHI"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)


KEY_NAMES = {
    1: "KEY_ESC",
    2: "KEY_1",
    3: "KEY_2",
    4: "KEY_3",
    5: "KEY_4",
    6: "KEY_5",
    7: "KEY_6",
    8: "KEY_7",
    9: "KEY_8",
    10: "KEY_9",
    11: "KEY_0",
    14: "KEY_BACKSPACE",
    15: "KEY_TAB",
    16: "KEY_Q",
    17: "KEY_W",
    18: "KEY_E",
    19: "KEY_R",
    20: "KEY_T",
    21: "KEY_Y",
    22: "KEY_U",
    23: "KEY_I",
    24: "KEY_O",
    25: "KEY_P",
    28: "KEY_ENTER",
    29: "KEY_LEFTCTRL",
    30: "KEY_A",
    31: "KEY_S",
    32: "KEY_D",
    33: "KEY_F",
    34: "KEY_G",
    35: "KEY_H",
    36: "KEY_J",
    37: "KEY_K",
    38: "KEY_L",
    42: "KEY_LEFTSHIFT",
    44: "KEY_Z",
    45: "KEY_X",
    46: "KEY_C",
    47: "KEY_V",
    48: "KEY_B",
    49: "KEY_N",
    50: "KEY_M",
    54: "KEY_RIGHTSHIFT",
    56: "KEY_LEFTALT",
    57: "KEY_SPACE",
    58: "KEY_CAPSLOCK",
    97: "KEY_RIGHTCTRL",
    100: "KEY_RIGHTALT",
    102: "KEY_HOME",
    103: "KEY_UP",
    104: "KEY_PAGEUP",
    105: "KEY_LEFT",
    106: "KEY_RIGHT",
    107: "KEY_END",
    108: "KEY_DOWN",
    109: "KEY_PAGEDOWN",
    110: "KEY_INSERT",
    111: "KEY_DELETE",
    125: "KEY_LEFTMETA",
    126: "KEY_RIGHTMETA",
    164: "KEY_PLAYPAUSE",
    165: "KEY_PREVIOUSSONG",
    166: "KEY_STOPCD",
    193: "KEY_193 / Lenovo voice input candidate",
    163: "KEY_NEXTSONG",
    113: "KEY_MUTE",
    114: "KEY_VOLUMEDOWN",
    115: "KEY_VOLUMEUP",
    364: "KEY_FAVORITES / XF86Favorites / Lenovo SuperStart",
}


@dataclass(frozen=True)
class Device:
    path: str
    file: object


def key_name(code: int) -> str:
    return KEY_NAMES.get(code, f"KEY_{code}")


def key_state(value: int) -> str:
    if value == 0:
        return "UP"
    if value == 1:
        return "DOWN"
    if value == 2:
        return "REPEAT"
    return f"VALUE_{value}"


def default_devices() -> list[str]:
    return sorted(glob.glob("/dev/input/event*"))


def open_devices(paths: list[str]) -> list[Device]:
    devices: list[Device] = []
    for path in paths:
        try:
            file = open(path, "rb", buffering=0)
        except PermissionError:
            print(f"skip: no permission: {path}", file=sys.stderr)
            continue
        except FileNotFoundError:
            print(f"skip: not found: {path}", file=sys.stderr)
            continue
        except OSError as exc:
            print(f"skip: cannot open {path}: {exc}", file=sys.stderr)
            continue
        devices.append(Device(path=path, file=file))
    return devices


def listen(devices: list[Device]) -> None:
    file_to_device = {device.file: device for device in devices}
    print("Listening. Press Ctrl+C to stop.")
    for device in devices:
        print(f"  {device.path}")

    while True:
        readable, _, _ = select.select(list(file_to_device), [], [])
        for file in readable:
            data = file.read(EVENT_SIZE)
            if len(data) != EVENT_SIZE:
                continue

            sec, usec, event_type, code, value = struct.unpack(EVENT_FORMAT, data)
            if event_type != EV_KEY:
                continue

            timestamp = datetime.fromtimestamp(sec + usec / 1_000_000).strftime(
                "%H:%M:%S.%f"
            )[:-3]
            device = file_to_device[file]
            print(
                f"{timestamp} {device.path} code={code:<4} "
                f"{key_name(code):<42} {key_state(value)}",
                flush=True,
            )


def main() -> int:
    paths = sys.argv[1:] or default_devices()
    if not paths:
        print("No /dev/input/event* devices found.", file=sys.stderr)
        return 1

    devices = open_devices(paths)
    if not devices:
        print(
            "No readable input devices. Try a specific device, e.g. "
            "./key-listener.py /dev/input/event6, or make sure your user can read input devices.",
            file=sys.stderr,
        )
        return 1

    try:
        listen(devices)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        for device in devices:
            device.file.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
