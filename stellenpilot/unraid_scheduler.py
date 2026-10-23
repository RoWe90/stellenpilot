"""Optional Docker sidecar: one daily search at a configured local wall-clock time.

The daily marker persists in /data so a container restart cannot trigger duplicate
runs that day. The lock protects against a second scheduler sidecar. Interactive
dashboard searches are separate: do not initiate those during the daily job.
"""
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_time(value: str) -> tuple[int, int]:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise ValueError("STELLENPILOT_DAILY_TIME must be HH:MM in 24-hour time")
    return tuple(map(int, value.split(":")))


def due(now: datetime, scheduled: tuple[int, int], last_day: str) -> bool:
    return (now.hour, now.minute) >= scheduled and now.date().isoformat() != last_day


def main() -> None:
    home = Path("/data")
    scheduled = parse_time(os.environ.get("STELLENPILOT_DAILY_TIME", "08:45"))
    timezone = ZoneInfo(os.environ.get("TZ", "Europe/Berlin"))
    marker = home / ".unraid-scheduler-last-run"
    lockpath = home / ".unraid-scheduler.lock"
    print(f"Daily search enabled at {scheduled[0]:02d}:{scheduled[1]:02d} ({timezone.key})", flush=True)
    with lockpath.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another scheduler has the lock; stopping to prevent duplicates")
        while True:
            now = datetime.now(timezone)
            last_day = marker.read_text(encoding="ascii").strip() if marker.exists() else ""
            if due(now, scheduled, last_day):
                # Mark before executing, preventing retries on restart in the same day.
                marker.write_text(now.date().isoformat() + "\n", encoding="ascii")
                marker.chmod(0o600)
                print(f"Starting Stellenpilot job search at {now.isoformat()}", flush=True)
                try:
                    result = subprocess.run(["stellenpilot", "--home", str(home), "run"], check=False)
                    print(f"Search exited with code {result.returncode}", flush=True)
                except Exception as exc:
                    print(f"Search failed to start: {exc}", flush=True)
            time.sleep(30)


if __name__ == "__main__":
    main()
