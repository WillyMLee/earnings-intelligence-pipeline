import pytest
from pipelines import agentmail_delivery as delivery


def test_sent_receipt_requires_matching_company_date_mode_and_recipient(monkeypatch):
    calls = []
    def request(key, method, path, payload=None):
        calls.append(path)
        if path.endswith("limit=100"):
            return {"messages": [{"labels": ["sent"], "timestamp": "2026-10-21T20:10:00Z", "to": ["user@example.com"], "subject": "Meta (META) Q3 FY2026 | Pre-Earnings Setup (Late Delivery)", "message_id": "m1"}]}
        return {"text": "Reports October 21, 2026 after close"}
    monkeypatch.setattr(delivery, "_request", request)
    args = dict(api_key="test", inbox_id="test", ticker="META", report_date="2026-10-21", mode="pre", recipients=["user@example.com"])
    assert delivery.find_earnings_delivery(**args)["message_id"] == "m1"
    assert delivery.find_earnings_delivery(**{**args, "mode": "post"}) == {}
    assert delivery.find_earnings_delivery(**{**args, "report_date": "2026-11-04"}) == {}
    assert delivery.find_earnings_delivery(**{**args, "recipients": ["another@example.com"]}) == {}


def test_receipt_lookup_failure_does_not_blindly_authorize_duplicate_email(monkeypatch):
    monkeypatch.setattr(delivery, "_request", lambda *_: (_ for _ in ()).throw(RuntimeError("unavailable")))
    with pytest.raises(RuntimeError):
        delivery.find_earnings_delivery(api_key="test", inbox_id="test", ticker="META", report_date="2026-10-21", mode="post", recipients=["user@example.com"])


@pytest.mark.parametrize("hour,expected", [(9, ["META"]), (16, [])])
def test_same_day_catchup_only_attempts_after_close_before_cutoff(monkeypatch, tmp_path, hour, expected):
    import sys
    from datetime import datetime as real_datetime
    from unittest.mock import Mock
    from pipelines import run_pre_earnings_deep_dive_auto as pre
    class Clock(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 21, hour, tzinfo=tz)
    monkeypatch.setattr(pre, "datetime", Clock)
    monkeypatch.setattr(sys, "argv", ["pre", "--calendar-csv", "unused.csv", "--same-day", "--for-date", "2026-10-21", "--output-dir", str(tmp_path)])
    monkeypatch.setattr(pre, "ensure_calendar_csv", lambda *_: None)
    monkeypatch.setattr(pre, "load_coverage_reporters", lambda *_: [{"ticker": "META", "report_time": "After Close"}, {"ticker": "IBM", "report_time": "Before Open"}, {"ticker": "TSLA", "report_time": "TBD"}])
    lookup=Mock(return_value={"message_id": "already-sent"})
    monkeypatch.setattr(pre.agentmail_delivery, "find_earnings_delivery", lookup)
    build=Mock()
    monkeypatch.setattr(pre, "build_brief_context", build)
    assert pre.main() == 0
    assert [c.kwargs["ticker"] for c in lookup.call_args_list] == expected
    build.assert_not_called()


def test_catchup_container_command_preserves_target_date_and_watchlist():
    from cloudflare.container_server import job_commands
    commands=job_commands("pre-catchup", for_date="2026-10-21", watchlist="META", draft_only=True)
    assert len(commands) == 2
    command=commands[1]
    assert "--same-day" in command
    assert command[command.index("--for-date")+1] == "2026-10-21"
    assert command[command.index("--watchlist")+1] == "META"
    assert "--draft-only" in command


def test_transcript_qa_survives_email_and_markdown_rendering():
    from pipelines.run_post_earnings_deep_dive_auto import analysis_sections
    from pipelines.render_pre_earnings_deep_dive_email import render_deep_dive_email, render_markdown_summary
    sections=analysis_sections({"sections": [{"heading": "Operating performance", "bullets": [{"text": "Revenue increased", "children": []}]}], "qa_highlights": [{"analyst_question": "Analyst asked about AI capacity", "answer_summary": "Management described capacity constraints"}, {"analyst_question": "Incomplete", "answer_summary": ""}]})
    assert len(sections) == 2
    assert len(sections[-1]["bullets"]) == 1
    context={"ticker": "META", "company": "Meta", "quarter": "Q3 FY2026", "sections": sections}
    for rendered in (render_deep_dive_email(context), render_markdown_summary(context)):
        assert "Earnings call Q&amp;A" in rendered or "Earnings call Q&A" in rendered
        assert "Analyst asked about AI capacity" in rendered
        assert "Management described capacity constraints" in rendered


def test_unavailable_transcript_does_not_invent_qa():
    from pipelines.run_post_earnings_deep_dive_auto import analysis_sections
    assert analysis_sections({"sections": []}) == []


def test_transcript_discovery_rejects_preview_generic_and_wrong_period():
    from core.research import _is_report_transcript
    good={"title": "META Q3 2026 Earnings Call Transcript", "url": "https://issuer.example/transcript", "text": "October 21, 2026\nOperator: Welcome to Meta earnings.\nQuestion and answer session\nAnalyst: What about spending?"}
    assert _is_report_transcript(good, "2026-10-21")
    assert not _is_report_transcript({**good, "text": good["text"].replace("October 21, 2026", "July 29, 2026")}, "2026-10-21")
    assert not _is_report_transcript({"title": "StoneX reiterates Hold ahead of earnings", "url": "https://example.com/analyst-ratings", "text": "October 21, 2026 revenue estimates"}, "2026-10-21")
    assert not _is_report_transcript({"title": "Meta Platforms - Wikipedia", "url": "https://en.wikipedia.org/wiki/Meta_Platforms", "text": good["text"]}, "2026-10-21")


def test_old_preview_cache_is_ignored(monkeypatch):
    from core import research
    monkeypatch.setattr(research, "_convex_artifact_request", lambda *args: {"title": "StoneX reiterates Hold ahead of earnings", "url": "https://example.com/analyst-ratings", "text": "Meta reports tomorrow October 21, 2026"})
    assert research._load_cached_transcript("META", "2026-10-21", 8000) == {}
