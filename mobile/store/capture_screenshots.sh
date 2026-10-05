#!/bin/bash
set -euo pipefail
# Снимает кадры App Store с симулятора, пока приложение пишет SCREENSHOT_READY.
# Usage: capture_screenshots.sh <udid> <outdir>

UDID=$1
OUT=$2
mkdir -p "$OUT"
python3 - <<'PY' "$UDID" "$OUT"
import subprocess, sys, time
from pathlib import Path

udid, out = sys.argv[1], Path(sys.argv[2])
proc = subprocess.Popen(
    ["xcrun", "simctl", "spawn", udid, "log", "stream", "--style", "compact", "--predicate", 'eventMessage CONTAINS "SCREENSHOT_"'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
)
seen = set()
deadline = time.time() + 180
assert proc.stdout is not None
for line in proc.stdout:
    if time.time() > deadline:
        break
    if "SCREENSHOT_READY:" not in line:
        if "SCREENSHOT_TOUR:done" in line:
            break
        continue
    name = line.split("SCREENSHOT_READY:", 1)[1].strip().split()[0]
    if name in seen:
        continue
    seen.add(name)
    dest = out / f"{name}.png"
    subprocess.check_call(["xcrun", "simctl", "io", udid, "screenshot", str(dest)])
    print(f"captured {dest}", flush=True)
    if name == "04-tasks":
        break
proc.kill()
print("names", sorted(seen), flush=True)
if len(seen) < 4:
    sys.exit(2)
PY
