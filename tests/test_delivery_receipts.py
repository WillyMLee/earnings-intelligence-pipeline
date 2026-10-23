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


@pytest.mark.parametrize("dashboard_only,expected_status", [(True, "succeeded"), (False, "failed")])
def test_dashboard_failure_is_explicit_without_claiming_missing_email(monkeypatch, dashboard_only, expected_status):
    import io
    from unittest.mock import Mock
    from cloudflare import container_server as runtime
    process=Mock(stdout=io.StringIO("failed tickers: AXP\n"),stderr=io.StringIO(""))
    process.wait.return_value=1
    monkeypatch.setattr(runtime.subprocess,"Popen",Mock(return_value=process))
    monkeypatch.setattr(runtime,"_schedule_idle_shutdown",lambda:None)
    job=runtime.Job("test","post-bmo","running","now")
    command=["python","post"]+(["--dashboard-only"] if dashboard_only else [])
    runtime._run_job(job,[command])
    assert job.status == expected_status
    assert bool(job.dashboardWarning) == dashboard_only
    assert job.exitCode == (0 if dashboard_only else 1)


def test_dashboard_post_report_archives_without_email(monkeypatch,tmp_path):
    from unittest.mock import Mock
    from pipelines import run_post_earnings_deep_dive_auto as post
    monkeypatch.setattr(post,"delivery_context_issues",lambda _:[])
    monkeypatch.setattr(post,"render_deep_dive_email",lambda _:"html")
    monkeypatch.setattr(post,"render_markdown_summary",lambda _:"text")
    archive=Mock(return_value={"status":"archived"});send=Mock()
    monkeypatch.setattr(post,"archive_post_earnings_summary",archive)
    monkeypatch.setattr(post.agentmail_delivery,"send_message",send)
    monkeypatch.delenv("DEAL_ALERT_EMAIL_TO",raising=False)
    assert post.send_deep_dive({"ticker":"AXP","company":"American Express"},tmp_path,False,archive_only=True)
    archive.assert_called_once();send.assert_not_called()


def test_text_digest_contains_financial_summary_without_a_price_reaction():
    from pipelines.run_post_earnings_digest import build_digest_text
    text=build_digest_text("Recovered summary: 2026-10-22",[{"ticker":"SPOT","company":"Spotify","reaction_pct":None,"key_metrics":["Revenue EUR 4.969B","Gross margin 33.0%"]}])
    assert "Revenue EUR 4.969B" in text
    assert "Gross margin 33.0%" in text
    assert "N/A" not in text


def test_spotify_recovery_preserves_euro_currency_and_issuer_comparisons():
    from core.verified_post_earnings import verified_post_earnings_brief
    brief=verified_post_earnings_brief("SPOT","2026-10-22")
    assert brief["financials"] == {}
    assert "issuer guidance" in brief["intro"]
    assert any("€4.969" in metric for metric in brief["key_metrics"])
    assert any(section["heading"] == "Analyst Q&A" for section in brief["sections"])


def test_spotify_preview_uses_euros_and_keeps_quote_in_dollars():
    from core.pre_earnings_data_preview import build_data_preview
    from pipelines.run_pre_earnings_deep_dive_auto import _build_key_figures
    snap={"financial_currency":"EUR","next_q_revenue_consensus":5_200_000_000,"last_q_revenue":4_969_000_000,"price":583.66}
    preview=build_data_preview("SPOT","Spotify","2027-02-01",snap,2.48)
    assert "\u20ac5.20" in str(preview["financial_highlights"])
    assert "$583.66" in str(preview["financial_highlights"])
    assert preview["financials"] == {}
    figures=_build_key_figures(snap,preview)
    assert figures[0]["value"].startswith("\u20ac")


def test_native_currency_consensus_cannot_be_archived_as_usd(monkeypatch):
    from unittest.mock import Mock
    from pipelines import earnings_archive
    request=Mock();monkeypatch.setattr(earnings_archive,"_convex_request",request)
    result=earnings_archive.archive_pre_earnings_snapshot(ticker="SPOT",report_date="2027-02-01",snap={"next_q_revenue_consensus":5_200_000_000})
    assert result["status"] == "skipped"
    request.assert_not_called()


def test_dashboard_draft_still_does_not_mutate_archive(monkeypatch,tmp_path):
    from unittest.mock import Mock
    from pipelines import run_post_earnings_deep_dive_auto as post
    monkeypatch.setattr(post,"delivery_context_issues",lambda _:[])
    monkeypatch.setattr(post,"render_deep_dive_email",lambda _:"html")
    monkeypatch.setattr(post,"render_markdown_summary",lambda _:"text")
    archive=Mock();monkeypatch.setattr(post,"archive_post_earnings_summary",archive)
    assert post.send_deep_dive({"ticker":"AXP","company":"American Express"},tmp_path,True,archive_only=True)
    archive.assert_not_called()


def test_publisher_transcript_url_identifies_report_date():
    from core.research import _is_report_transcript
    item={"title":"Spotify Q3 2026 Earnings Call Transcript","url":"https://www.fool.com/earnings/call-transcripts/2026/10/22/spotify-spot-q3-2026-earnings-call-transcript/","raw_content":"Operator: Welcome\nQuestion and answer session"}
    assert _is_report_transcript(item,"2026-10-22")
    assert not _is_report_transcript(item,"2026-07-22")
