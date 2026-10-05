#!/usr/bin/env python3
"""Запускает приложение на симуляторе и снимает кадры по меткам SCREENSHOT_READY."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLUTTER = os.environ.get("FLUTTER", "flutter")


def capture(udid: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    cmd = [
        FLUTTER,
        "run",
        "--debug",
        "-d",
        udid,
        "--dart-define-from-file",
        str(ROOT / "config/prod.json"),
        "--dart-define=SCREENSHOTS=true",
        "--dart-define=SCREENSHOT_TOUR=true",
        "--dart-define=SCREENSHOT_USER=appreview",
        "--dart-define=SCREENSHOT_PASS=Review!2026Mx",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    seen: set[str] = set()
    assert proc.stdout is not None
    try:
        deadline = time.time() + 240
        for line in proc.stdout:
            if "Bearer eyJ" in line or "Authorization:" in line:
                continue
            if "SCREENSHOT_" in line or "Error" in line or "Exception" in line:
                print(line.rstrip(), flush=True)
            if time.time() > deadline:
                raise SystemExit(f"timeout on {udid}, got {sorted(seen)}")
            if "SCREENSHOT_READY:" in line:
                name = line.split("SCREENSHOT_READY:", 1)[1].strip().split()[0]
                if name in seen:
                    continue
                time.sleep(0.4)
                dest = out / f"{name}.png"
                subprocess.check_call(["xcrun", "simctl", "io", udid, "screenshot", str(dest)])
                print(f"captured {dest}", flush=True)
                seen.add(name)
            if "SCREENSHOT_TOUR:done" in line:
                break
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
    if len(seen) < 4:
        raise SystemExit(f"мало кадров на {udid}: {sorted(seen)}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: capture_screenshots.py <udid> <outdir>")
    capture(sys.argv[1], Path(sys.argv[2]))


if __name__ == "__main__":
    main()
