from datetime import date

from cloudflare.container_server import job_commands
from pipelines.run_earnings_radar_automation import resolve_recipient
from pipelines.run_pre_earnings_deep_dive_auto import _next_business_day


def test_pre_earnings_targets_monday_from_friday():
    assert _next_business_day(date(2026, 8, 21)) == date(2026, 8, 24)
    assert _next_business_day(date(2026, 8, 20)) == date(2026, 8, 21)


def test_weekly_recipient_falls_back_to_daily(monkeypatch):
    monkeypatch.delenv("WEEKLY_BRIEFING_EMAIL_TO", raising=False)
    monkeypatch.setenv("DEAL_ALERT_EMAIL_TO", "analyst@example.com")
    assert resolve_recipient("weekly") == "analyst@example.com"


def test_input_prefetch_rotates_and_every_job_has_a_command():
    prefetch = job_commands("input-prefetch")
    assert "--rotate-daily" in prefetch[1]
    for name in (
        "daily-radar",
        "weekly-radar",
        "pre-earnings",
        "post-bmo",
        "post-amc",
        "post-digest-bmo",
        "post-digest-amc",
        "input-prefetch",
        "transcript-cache",
    ):
        assert job_commands(name)


def test_walmart_backfill_arguments_are_scoped():
    commands = job_commands("post-bmo", for_date="2026-08-20", watchlist="WMT")
    assert "fetch_earnings_calendar.py" in commands[0][1]
    command = commands[1]
    assert command[-4:] == ["--for-date", "2026-08-20", "--watchlist", "WMT"]


def test_post_correction_is_explicitly_labeled():
    commands = job_commands("post-bmo", for_date="2026-08-20", watchlist="WMT", correction=True)
    assert "--correction" in commands[1]
