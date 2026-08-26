import json
from datetime import date

from cloudflare.container_server import job_commands
from core import stock_data
from pipelines import earnings_archive
from pipelines.build_weekly_earnings_brief import EarningsEvent, enrich_financial_snapshots
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


def test_pre_snapshot_archives_reusable_daily_card_fields(monkeypatch):
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setenv("EARNINGS_ARCHIVE_TOKEN", "test-token")
    calls = []
    monkeypatch.setattr(earnings_archive, "_convex_request", lambda **kwargs: calls.append(kwargs) or {"ok": True})
    earnings_archive.archive_pre_earnings_snapshot(
        ticker="NVDA",
        report_date="2026-08-26",
        snap={
            "price": 210.56,
            "market_cap_b": 5099.97,
            "last_q_revenue": 81_615_000_000,
            "last_q_yoy_pct": 85.2,
            "last_q_label": "Apr 2026",
            "last_q_period_end": "2026-04-26",
            "gross_margin_pct": 74.1,
            "next_q_revenue_consensus": 92_176_624_640,
            "next_q_yoy_pct": 97.2,
            "fy_revenue_consensus": 395_728_233_370,
            "fy_yoy_pct": 83.3,
        },
    )
    assert calls[0]["path"] == "preEarningsSnapshots:upsertSnapshot"
    assert calls[0]["args"]["revenueConsensusUsd"] == 92_176_624_640
    assert calls[1]["path"] == "researchArtifacts:upsertArtifact"
    payload = json.loads(calls[1]["args"]["text"])
    assert payload["price"] == 210.56
    assert payload["market_cap_b"] == 5099.97
    assert payload["last_q_revenue"] == 81_615_000_000
    assert payload["gross_margin_pct"] == 74.1
    assert payload["next_q_revenue_consensus"] == 92_176_624_640
    assert payload["_captured_at"].startswith(date.today().isoformat())


def test_daily_enrichment_reuses_complete_convex_snapshot(monkeypatch):
    today = date.today()
    event = EarningsEvent(
        ticker="NVDA",
        company="Nvidia",
        report_date=today,
        report_time="After Close",
        sector="",
        eps_estimate="2.09",
        revenue_estimate="",
        implied_move_pct=None,
        market_cap_b=None,
        score_reasons="coverage universe",
    )
    stored = {
        "_captured_at": f"{today.isoformat()}T04:31:00",
        "price": 210.56,
        "market_cap_b": 5099.97,
        "last_q_revenue": 81_615_000_000,
        "last_q_yoy_pct": 85.2,
        "gross_margin_pct": 74.1,
        "next_q_revenue_consensus": 92_176_624_640,
        "next_q_yoy_pct": 97.2,
        "fy_revenue_consensus": 395_728_233_370,
        "fy_yoy_pct": 83.3,
    }
    monkeypatch.setattr(earnings_archive, "load_financial_snapshot_artifact", lambda **_kwargs: stored)
    monkeypatch.setattr(stock_data, "fetch_financial_snapshot", lambda _ticker: (_ for _ in ()).throw(AssertionError("live fetch should be skipped")))
    enrich_financial_snapshots([event])
    assert event.market_cap_b == 5099.97
    assert event.financial_snapshot["price"] == 210.56
    assert event.financial_snapshot["last_q_revenue"] == 81_615_000_000
    assert event.financial_snapshot["next_q_revenue_consensus"] == 92_176_624_640
