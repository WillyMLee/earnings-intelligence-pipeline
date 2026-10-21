import sys
from datetime import date
from unittest.mock import Mock

import pytest

from core.earnings_universe import EMAIL_DEEP_DIVE_TICKERS
from core.official_earnings_calendar import parse_announcement, reconcile_official_events, VERIFIED_EVENTS as ALL_VERIFIED_EVENTS
from pipelines import run_post_earnings_digest as digest
from pipelines import run_weekly_earnings_workflow as radar
from pipelines.run_pre_earnings_deep_dive_auto import load_coverage_reporters
VERIFIED_EVENTS = [event for event in ALL_VERIFIED_EVENTS if event["Report Date"] == "2026-10-20"]


def test_confirmed_date_replaces_estimate_and_restores_missing_reporter(tmp_path):
    rows = [{"Ticker": "SPCX", "Report Date": "2026-11-03", "Report Time": "TBD", "EPS Estimate": "0.11"}]
    reconciled = reconcile_official_events(rows, VERIFIED_EVENTS)
    assert [(r["Ticker"], r["Report Date"]) for r in reconciled] == [("NFLX", "2026-10-20"), ("SPCX", "2026-10-20")]
    assert "EPS Estimate" not in next(r for r in reconciled if r["Ticker"] == "SPCX")
    from pipelines.fetch_earnings_calendar import write_rows
    path = tmp_path / "calendar.csv"
    write_rows(str(path), reconciled)
    assert {r["ticker"] for r in load_coverage_reporters(str(path), date(2026, 10, 20), EMAIL_DEEP_DIVE_TICKERS)} == {"NFLX", "SPCX"}


@pytest.mark.parametrize("ticker,text", [
    ("SPCX", "October 16, 2026. SpaceX will post financial and operational results for the third quarter of 2026 after market close on Tuesday, October 20, 2026."),
    ("NFLX", "Sep 14, 2026. Netflix announced it will post its third quarter 2026 financial results on Tuesday October 20th, 2026, at approximately 1:01 p.m. Pacific Time."),
])
def test_announcement_uses_event_date_not_publication_date(ticker, text):
    event = parse_announcement(ticker, "https://issuer.example/announcement", text)
    assert event["Report Date"] == "2026-10-20"
    assert event["Report Time"] == "After Close"


def test_unconfirmed_or_past_results_are_not_announcement_dates():
    assert parse_announcement("SPCX", "https://issuer.example", "SpaceX reported earnings October 20, 2026.") is None


def test_confirmed_archive_removes_old_estimate_without_erasing_previous_quarter(monkeypatch):
    from pipelines import earnings_archive
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setenv("EARNINGS_ARCHIVE_TOKEN", "test")
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        if kwargs["kind"] == "query":
            return [{"ticker": "SPCX", "reportDate": day} for day in ["2026-08-04", "2026-11-03"]]
        return {"ok": True}
    monkeypatch.setattr(earnings_archive, "_convex_request", request)
    earnings_archive.archive_earnings_calendar(VERIFIED_EVENTS)
    archived = [e for c in calls if c["kind"] == "mutation" for e in c["args"]["events"]]
    assert {(e["ticker"], e["reportDate"]) for e in archived} == {("SPCX", "2026-08-04"), ("SPCX", "2026-10-20"), ("NFLX", "2026-10-20")}


def test_late_consensus_cannot_overwrite_a_pre_report_snapshot(monkeypatch):
    from pipelines import earnings_archive
    request = Mock()
    monkeypatch.setattr(earnings_archive, "_convex_request", request)
    result = earnings_archive.archive_pre_earnings_snapshot(ticker="NFLX", report_date="2026-10-20", captured_at="2026-10-21T10:00:00-04:00", snap={"next_q_revenue_consensus": 13_400_000_000})
    assert result["status"] == "skipped"
    request.assert_not_called()


def test_late_consensus_is_rejected_when_reading_legacy_records(monkeypatch):
    from pipelines import earnings_archive
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setattr(earnings_archive, "_convex_request", Mock(return_value={"capturedAt": "2026-10-21T10:00:00", "revenueConsensusUsd": 13_400_000_000}))
    assert earnings_archive.fetch_pre_earnings_snapshot("NFLX", "2026-10-20") == {}


def test_late_financial_artifact_cannot_be_reused_as_pre_report_input(monkeypatch):
    from pipelines import earnings_archive
    import json
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setattr(earnings_archive, "_convex_request", Mock(return_value={"text": json.dumps({"_captured_at": "2026-10-21T10:00:00", "next_q_revenue_consensus": 13_400_000_000})}))
    assert earnings_archive.load_financial_snapshot_artifact(ticker="NFLX", report_date="2026-10-20") == {}


@pytest.mark.parametrize("ticker", ["NFLX", "SPCX"])
def test_october_recovery_briefs_are_substantive_and_source_verified(ticker):
    from core.verified_post_earnings import verified_post_earnings_brief
    from pipelines.run_post_earnings_deep_dive_auto import delivery_context_issues
    brief = verified_post_earnings_brief(ticker, "2026-10-20")
    context = {**brief, "qa_approved": brief["_qa_approved"]}
    assert not delivery_context_issues(context)
    assert brief["financials"]["revenue_actual_usd"] == {"NFLX": 12_874_000_000, "SPCX": 14_575_000_000}[ticker]


@pytest.mark.parametrize("amount,supported", [("19.6", True), ("19.59", True), ("29.6", False)])
def test_capex_check_accepts_rounded_millions_but_blocks_wrong_amount(amount, supported):
    from core.synthesis import _sanity_check_brief
    brief = {"financials": {"revenue_actual_usd": 14_575_000_000}, "key_metrics": [f"Capital Expenditures: ${amount} billion"], "sections": []}
    issues = _sanity_check_brief(brief, facts={"official_release_source_text": "$, in millions. Capex Space $1,606 Connectivity 1,543 SI 16,444 Total $19,593"})
    assert (not any("CapEx amount" in issue for issue in issues)) == supported


def test_annual_revenue_outlook_is_not_compared_to_quarterly_segment_revenue():
    from core.synthesis import _sanity_check_brief
    brief = {"financials": {"revenue_actual_usd": 14_575_000_000}, "sections": [{"heading": "Outlook", "bullets": [{"text": "Annual revenue outlook: $100.0 billion."}]}]}
    assert not any("EXCEEDS" in issue for issue in _sanity_check_brief(brief))
    brief["sections"][0]["bullets"][0]["text"] = "Connectivity revenue for the quarter: $100.0 billion."
    assert any("EXCEEDS" in issue for issue in _sanity_check_brief(brief))


def test_next_quarter_revenue_guide_is_not_treated_as_current_actual():
    from core.synthesis import _sanity_check_brief
    brief = {"financials": {"revenue_actual_usd": 12_874_000_000}}
    issues = _sanity_check_brief(brief, facts={"official_release_source_text": "Revenue grew 12% to $12.9B. In Q4, we expect revenue of $13.4 billion."})
    assert not any("revenue_actual_usd conflicts" in issue for issue in issues)


def test_fiscal_year_proxy_is_labeled_consistently_in_email():
    from pipelines.render_pre_earnings_deep_dive_email import _valuation_reference_html
    item = {"cy_revenue": "$19.31B FY2027 proxy", "basis": "Fiscal-year proxy; no CY estimate available", "ev_cy_revenue": "6.8x"}
    rendered = _valuation_reference_html(item)
    assert "FY revenue estimate" in rendered
    assert "EV / FY revenue" in rendered
    assert "EV / CY revenue" not in rendered


def test_rejected_narrative_becomes_sourced_data_preview(monkeypatch):
    from pipelines import run_pre_earnings_deep_dive_auto as pre
    monkeypatch.setattr(pre, "fetch_financial_snapshot", Mock(return_value={"next_q_revenue_consensus": 4_500_000_000, "last_q_revenue": 3_747_000_000, "gross_margin_pct": 48.9, "price": 200.0}))
    monkeypatch.setattr(pre, "archive_pre_earnings_snapshot", Mock(return_value={"status": "skipped"}))
    monkeypatch.setattr(pre, "synthesize_earnings_brief_with_review", Mock(return_value={"sections": [{"heading": "Untrusted", "bullets": [{"text": "Rejected claim"}]}], "_qa_approved": False, "_qa_issues": ["Unverified claim"]}))
    context = pre.build_brief_context({"ticker": "WDC", "company": "Western Digital", "eps_estimate": "3.97", "report_time": "After Close"}, date(2026, 10, 22))
    assert context["brief_label"] == "Pre-Earnings Data Preview"
    assert context["quarter"] == "Upcoming report"
    assert len(context["financial_highlights"]) >= 3
    assert "Rejected claim" not in str(context)
    assert "4.50 billion" in str(context)
    assert "$3.97" in str(context)
    assert "finance.yahoo.com" in str(context)


def test_data_preview_requires_actual_captured_inputs():
    from core.pre_earnings_data_preview import build_data_preview
    assert build_data_preview("NFLX", "Netflix", "2027-01-20", {}) == {}
    assert build_data_preview("NFLX", "Netflix", "2027-01-20", {"next_q_revenue_consensus": float("nan"), "price": float("inf")}) == {}


@pytest.mark.parametrize("session", ["bmo", "amc", "all"])
def test_empty_digest_does_not_render_or_send(monkeypatch, session):
    monkeypatch.setattr(sys, "argv", ["digest", "--calendar-csv", "unused.csv", "--for-date", "2026-10-21", "--session", session])
    monkeypatch.setattr(digest, "ensure_calendar_csv", lambda *_: None)
    monkeypatch.setattr(digest, "load_coverage_reporters", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(digest, "load_amc_items_for_date", lambda *_: [])
    render, send = Mock(), Mock()
    monkeypatch.setattr(digest, "render_post_earnings_digest_email", render)
    monkeypatch.setattr(digest.agentmail_delivery, "send_message", send)
    assert digest.main() == 0
    render.assert_not_called()
    send.assert_not_called()


def test_nonempty_digest_still_sends(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["digest", "--calendar-csv", "unused.csv", "--for-date", "2026-10-20", "--session", "amc"])
    monkeypatch.setattr(digest, "ensure_calendar_csv", lambda *_: None)
    monkeypatch.setattr(digest, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(digest, "load_amc_items_for_date", lambda *_: [{"ticker": "NFLX", "company": "Netflix", "reaction_pct": -5.0, "key_metrics": ["Revenue $12.87B"]}])
    monkeypatch.setenv("DEAL_ALERT_EMAIL_TO", "test@example.com")
    monkeypatch.setenv("AGENTMAIL_API_KEY", "test")
    monkeypatch.setattr(digest.agentmail_delivery, "ensure_inbox", Mock(return_value={"inbox_id": "test"}))
    send = Mock(return_value={"message_id": "test"})
    monkeypatch.setattr(digest.agentmail_delivery, "send_message", send)
    assert digest.main() == 0
    send.assert_called_once()


@pytest.mark.parametrize("daily", [False, True])
def test_empty_radar_preserves_archive_without_email(monkeypatch, tmp_path, daily):
    path = tmp_path / "calendar.csv"
    path.write_text("Ticker,Company Name,Report Date,Report Time\nIBM,IBM,2026-10-21,After Close\n")
    argv = ["radar", "--calendar-csv", str(path), "--week-start", "2026-10-21", "--week-end", "2026-10-21", "--watchlist", "NFLX,SPCX", "--output-dir", str(tmp_path), "--send-email", "--email-to", "test@example.com"]
    if daily:
        argv.append("--daily")
    monkeypatch.setattr(sys, "argv", argv)
    for name in ("enrich_market_caps", "enrich_financial_snapshots", "enrich_notable_what_matters"):
        monkeypatch.setattr(radar, name, lambda *_: None)
    archive = Mock(return_value={"status": "archived"})
    send = Mock()
    monkeypatch.setattr(radar, "archive_weekly_brief", archive)
    monkeypatch.setattr(radar.agentmail_delivery, "send_message", send)
    result = radar.run_workflow(radar.parse_args())
    assert result["delivery"]["status"] == "skipped"
    assert result["delivery"]["reason"] == "no_covered_earnings"
    send.assert_not_called()
    archive.assert_called_once()


def test_meta_passive_announcement_uses_confirmed_date():
    event = parse_announcement("META", "https://issuer.example/announcement", "September 22, 2026. Meta financial results will be released after market close on Wednesday, October 21, 2026.")
    assert event["Report Date"] == "2026-10-21"
    assert event["Report Time"] == "After Close"
