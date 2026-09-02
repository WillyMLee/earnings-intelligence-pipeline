#!/usr/bin/env python3
"""Private HTTP control plane for running the Python pipelines in a Cloudflare Container."""

from __future__ import annotations

import hmac
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_LIMIT = 120_000
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WATCHLIST_RE = re.compile(r"^[A-Z0-9.,-]+$")


@dataclass
class Job:
    runId: str
    jobName: str
    status: str
    startedAt: str
    finishedAt: str | None = None
    durationMs: int | None = None
    exitCode: int | None = None
    stdoutTail: str = ""
    stderrTail: str = ""


LOCK = threading.Lock()
CURRENT_JOB: Job | None = None
LAST_JOB: Job | None = None
SHUTDOWN_TIMER: threading.Timer | None = None


def _cancel_idle_shutdown() -> None:
    global SHUTDOWN_TIMER
    if SHUTDOWN_TIMER is not None:
        SHUTDOWN_TIMER.cancel()
    SHUTDOWN_TIMER = None


def _schedule_idle_shutdown(delay_seconds: int = 60) -> None:
    global SHUTDOWN_TIMER

    def shutdown_if_idle() -> None:
        global SHUTDOWN_TIMER
        with LOCK:
            SHUTDOWN_TIMER = None
            if CURRENT_JOB is not None:
                return
        os.kill(os.getpid(), signal.SIGTERM)

    _cancel_idle_shutdown()
    SHUTDOWN_TIMER = threading.Timer(delay_seconds, shutdown_if_idle)
    SHUTDOWN_TIMER.daemon = True
    SHUTDOWN_TIMER.start()


def _python(*args: str) -> list[str]:
    return [sys.executable, *args]


def job_commands(
    job_name: str,
    *,
    for_date: str = "",
    watchlist: str = "",
    draft_only: bool = False,
    correction: bool = False,
) -> list[list[str]]:
    calendar = "data/latest_earnings_calendar.csv"
    date_args = ["--for-date", for_date] if for_date else []
    watchlist_args = ["--watchlist", watchlist] if watchlist else []
    draft_args = ["--draft-only"] if draft_only else []
    correction_args = ["--correction"] if correction else []

    refresh_calendar = _python(
        "pipelines/fetch_earnings_calendar.py",
        "--output",
        calendar,
        "--horizon",
        "3month",
        "--skip-convex-archive",
    )
    refresh_and_publish_calendar = _python(
        "pipelines/fetch_earnings_calendar.py",
        "--output",
        calendar,
        "--horizon",
        "3month",
    )
    commands: dict[str, list[list[str]]] = {
        "daily-radar": [_python("pipelines/run_earnings_radar_automation.py", "--mode", "daily", *(["--today", for_date] if for_date else []), *draft_args)],
        "weekly-radar": [_python("pipelines/run_earnings_radar_automation.py", "--mode", "weekly", *(["--today", for_date] if for_date else []), *draft_args)],
        "pre-earnings": [refresh_calendar, _python("pipelines/run_pre_earnings_deep_dive_auto.py", "--calendar-csv", calendar, *date_args, *watchlist_args, *draft_args, *correction_args)],
        "post-bmo": [refresh_calendar, _python("pipelines/run_post_earnings_deep_dive_auto.py", "--calendar-csv", calendar, "--session", "bmo", *date_args, *watchlist_args, *draft_args, *correction_args)],
        "post-amc": [refresh_calendar, _python("pipelines/run_post_earnings_deep_dive_auto.py", "--calendar-csv", calendar, "--session", "amc", *date_args, *watchlist_args, *draft_args, *correction_args)],
        "post-digest-bmo": [refresh_calendar, _python("pipelines/run_post_earnings_digest.py", "--calendar-csv", calendar, "--session", "bmo", *date_args, *watchlist_args, *draft_args)],
        "post-digest-amc": [refresh_calendar, _python("pipelines/run_post_earnings_digest.py", "--calendar-csv", calendar, "--session", "amc", *date_args, *watchlist_args, *draft_args)],
        "input-prefetch": [
            refresh_and_publish_calendar,
            _python("pipelines/backfill_earnings_inputs.py", "--calendar-csv", calendar, "--consensus", "--batch-size", "150", *watchlist_args, "--rotate-daily", "--resume-file", "/tmp/earnings-input-prefetch-state.json"),
        ],
        "transcript-cache": [
            refresh_calendar,
            _python("pipelines/backfill_earnings_inputs.py", "--calendar-csv", calendar, "--start", "2026-07-01", "--transcripts", "--batch-size", "12", "--pause-seconds", "1.0", *watchlist_args, "--rotate-daily", "--resume-file", "/tmp/earnings-transcript-cache-state.json"),
        ],
    }
    if not watchlist and job_name == "pre-earnings":
        commands[job_name].append(
            _python(
                "pipelines/run_pre_earnings_deep_dive_auto.py",
                "--calendar-csv",
                calendar,
                *date_args,
                "--dashboard-only",
            )
        )
    if not watchlist and job_name in {"post-bmo", "post-amc"}:
        commands[job_name].append(
            _python(
                "pipelines/run_post_earnings_deep_dive_auto.py",
                "--calendar-csv",
                calendar,
                "--session",
                "bmo" if job_name == "post-bmo" else "amc",
                *date_args,
                "--dashboard-only",
            )
        )
    if job_name not in commands:
        raise ValueError(f"unknown job: {job_name}")
    return commands[job_name]


def _tail(existing: str, value: str) -> str:
    combined = existing + value
    return combined[-LOG_LIMIT:]


def _run_job(job: Job, commands: list[list[str]]) -> None:
    global CURRENT_JOB, LAST_JOB
    started = time.monotonic()
    exit_code = 0
    for command in commands:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def drain(stream: Any, target: str) -> None:
            if stream is None:
                return
            for line in iter(stream.readline, ""):
                if target == "stdout":
                    job.stdoutTail = _tail(job.stdoutTail, line)
                    print(line, end="", flush=True)
                else:
                    job.stderrTail = _tail(job.stderrTail, line)
                    print(line, end="", file=sys.stderr, flush=True)
            stream.close()

        readers = [
            threading.Thread(target=drain, args=(process.stdout, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        return_code = process.wait()
        for reader in readers:
            reader.join()
        if return_code != 0:
            exit_code = return_code
            break

    job.exitCode = exit_code
    job.status = "succeeded" if exit_code == 0 else "failed"
    job.finishedAt = datetime.now(timezone.utc).isoformat()
    job.durationMs = int((time.monotonic() - started) * 1000)
    with LOCK:
        LAST_JOB = job
        CURRENT_JOB = None
    _schedule_idle_shutdown()


def _validate_body(body: dict[str, Any]) -> tuple[str, str, str, str, bool, bool]:
    job_name = str(body.get("jobName") or "")
    run_id = str(body.get("runId") or "")
    for_date = str(body.get("forDate") or "")
    watchlist = str(body.get("watchlist") or "").upper()
    draft_only = body.get("draftOnly") is True
    correction = body.get("correction") is True
    if not run_id or len(run_id) > 100:
        raise ValueError("runId is required and must be at most 100 characters")
    if for_date and not DATE_RE.fullmatch(for_date):
        raise ValueError("forDate must use YYYY-MM-DD")
    if watchlist and not WATCHLIST_RE.fullmatch(watchlist):
        raise ValueError("invalid watchlist")
    job_commands(job_name, for_date=for_date, watchlist=watchlist, draft_only=draft_only, correction=correction)
    return job_name, run_id, for_date, watchlist, draft_only, correction


class Handler(BaseHTTPRequestHandler):
    server_version = "earnings-cloudflare-container/1"

    def _json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authorized(self) -> bool:
        expected = os.environ.get("EARNINGS_ARCHIVE_TOKEN", "")
        supplied = self.headers.get("x-automation-token", "")
        return bool(expected) and hmac.compare_digest(expected, supplied)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            with LOCK:
                current = asdict(CURRENT_JOB) if CURRENT_JOB else None
                last = asdict(LAST_JOB) if LAST_JOB else None
            self._json(200, {"ok": True, "runtime": "cloudflare-container", "releaseTag": os.environ.get("RELEASE_TAG"), "currentJob": current, "lastJob": last})
            return
        if parsed.path != "/internal/job" or not self._authorized():
            self._json(401 if parsed.path == "/internal/job" else 404, {"ok": False, "reason": "unauthorized" if parsed.path == "/internal/job" else "not_found"})
            return
        run_id = parse_qs(parsed.query).get("runId", [""])[0]
        with LOCK:
            candidates = [CURRENT_JOB, LAST_JOB]
            job = next((item for item in candidates if item and item.runId == run_id), None)
        self._json(200, {"ok": True, "job": asdict(job) if job else None})

    def do_POST(self) -> None:  # noqa: N802
        global CURRENT_JOB
        if self.path != "/internal/run":
            self._json(404, {"ok": False, "reason": "not_found"})
            return
        if not self._authorized():
            self._json(401, {"ok": False, "reason": "unauthorized"})
            return
        try:
            length = min(int(self.headers.get("content-length", "0")), 32_768)
            body = json.loads(self.rfile.read(length) or b"{}")
            job_name, run_id, for_date, watchlist, draft_only, correction = _validate_body(body)
            commands = job_commands(job_name, for_date=for_date, watchlist=watchlist, draft_only=draft_only, correction=correction)
        except (ValueError, json.JSONDecodeError) as error:
            self._json(400, {"ok": False, "reason": "invalid_request", "message": str(error)})
            return

        with LOCK:
            if CURRENT_JOB and CURRENT_JOB.runId == run_id:
                self._json(200, {"ok": True, "duplicate": True, "job": asdict(CURRENT_JOB)})
                return
            if LAST_JOB and LAST_JOB.runId == run_id:
                self._json(200, {"ok": True, "duplicate": True, "job": asdict(LAST_JOB)})
                return
            if CURRENT_JOB:
                self._json(409, {"ok": False, "reason": "job_already_running", "job": asdict(CURRENT_JOB)})
                return
            job = Job(runId=run_id, jobName=job_name, status="running", startedAt=datetime.now(timezone.utc).isoformat())
            CURRENT_JOB = job

        _cancel_idle_shutdown()
        threading.Thread(target=_run_job, args=(job, commands), daemon=True).start()
        self._json(202, {"ok": True, "accepted": True, "job": asdict(job)})

    def log_message(self, message: str, *args: Any) -> None:
        print(json.dumps({"event": "http", "message": message % args}), flush=True)


def main() -> None:
    port = int(os.environ.get("CONTAINER_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(json.dumps({"event": "container_ready", "port": port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
