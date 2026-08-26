from datetime import date

from cloudflare.container_server import job_commands
from pipelines import earnings_archive
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


def test_only_input_prefetch_publishes_the_calendar_to_convex():
    publishing = job_commands("input-prefetch")[0]
    assert "--skip-convex-archive" not in publishing
    for name in (
        "pre-earnings",
        "post-bmo",
        "post-amc",
        "post-digest-bmo",
        "post-digest-amc",
        "transcript-cache",
    ):
        assert "--skip-convex-archive" in job_commands(name)[0]


def test_scheduled_deep_dives_analyze_site_only_names_without_email():
    for name in ("pre-earnings", "post-bmo", "post-amc"):
        commands = job_commands(name)
        assert "--dashboard-only" in commands[-1]
        assert "--dashboard-only" not in commands[1]

    targeted = job_commands("post-bmo", watchlist="WMT")
    assert len(targeted) == 2
    assert "--dashboard-only" not in targeted[-1]


def test_calendar_archive_hash_is_stable_across_provider_order(monkeypatch):
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setenv("EARNINGS_ARCHIVE_TOKEN", "test-token")
    calls = []

    def fake_request(**kwargs):
        calls.append(kwargs)
        if kwargs["kind"] == "query":
            return []
        return {"ok": True}

    monkeypatch.setattr(earnings_archive, "_convex_request", fake_request)
    rows = [
        {"Ticker": "MSFT", "Company Name": "Microsoft", "Report Date": "2026-10-20", "Report Time": "AMC"},
        {"Ticker": "WMT", "Company Name": "Walmart", "Report Date": "2026-11-19", "Report Time": "BMO"},
    ]
    earnings_archive.archive_earnings_calendar(rows)
    earnings_archive.archive_earnings_calendar(reversed(rows))

    mutation_calls = [call for call in calls if call["kind"] == "mutation"]
    midpoint = len(mutation_calls) // 2
    first_archive = mutation_calls[:midpoint]
    second_archive = mutation_calls[midpoint:]
    assert len(first_archive) == len(second_archive)
    assert len(first_archive) > 1
    assert all("contentHash" not in call["args"] for call in mutation_calls)
    assert all(
        (date.fromisoformat(call["args"]["windowEnd"]) - date.fromisoformat(call["args"]["windowStart"])).days < 7
        for call in mutation_calls
    )
    first_events = [event for call in first_archive for event in call["args"]["events"]]
    second_events = [event for call in second_archive for event in call["args"]["events"]]
    assert [event["ticker"] for event in first_events] == ["MSFT", "WMT"]
    assert first_events == second_events


def test_calendar_archive_preserves_tracked_history_and_removes_untracked_rows(monkeypatch):
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setenv("EARNINGS_ARCHIVE_TOKEN", "test-token")
    calls = []

    def fake_request(**kwargs):
        calls.append(kwargs)
        if kwargs["kind"] == "query":
            return [
                {"ticker": "MSFT", "company": "Microsoft", "reportDate": "2026-07-30", "reportTime": "AMC"},
                {"ticker": "NOTREAL", "company": "Legacy Name", "reportDate": "2026-07-30", "reportTime": "AMC"},
            ]
        return {"ok": True}

    monkeypatch.setattr(earnings_archive, "_convex_request", fake_request)
    earnings_archive.archive_earnings_calendar(
        [{"Ticker": "WMT", "Company Name": "Walmart", "Report Date": "2026-11-19", "Report Time": "BMO"}]
    )
    archived = [
        event
        for call in calls
        if call["kind"] == "mutation"
        for event in call["args"]["events"]
    ]
    assert {event["ticker"] for event in archived} == {"MSFT", "WMT"}


def test_daily_and_weekly_email_fetches_do_not_depend_on_convex_calendar_archive():
    source = (earnings_archive.PROJECT_ROOT / "pipelines" / "run_earnings_radar_automation.py").read_text(encoding="utf-8")
    assert '"--skip-convex-archive"' in source


def test_walmart_backfill_arguments_are_scoped():
    commands = job_commands("post-bmo", for_date="2026-08-20", watchlist="WMT")
    assert "fetch_earnings_calendar.py" in commands[0][1]
    command = commands[1]
    assert command[-4:] == ["--for-date", "2026-08-20", "--watchlist", "WMT"]


def test_post_correction_is_explicitly_labeled():
    commands = job_commands("post-bmo", for_date="2026-08-20", watchlist="WMT", correction=True)
    assert "--correction" in commands[1]


def test_pre_correction_is_explicitly_labeled():
    commands = job_commands("pre-earnings", for_date="2026-08-25", watchlist="NVDA", correction=True)
    assert "--correction" in commands[1]
