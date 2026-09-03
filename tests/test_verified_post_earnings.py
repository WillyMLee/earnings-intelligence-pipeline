from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.verified_post_earnings import verified_post_earnings_brief
from pipelines.run_post_earnings_deep_dive_auto import build_brief_context, delivery_context_issues, send_deep_dive


def _context(ticker: str = "SNOW") -> dict:
    brief = verified_post_earnings_brief(ticker, "2026-09-02")
    return {
        "ticker": ticker,
        "company": {"AVGO": "Broadcom Inc.", "HPE": "Hewlett Packard Enterprise", "SNOW": "Snowflake Inc."}[ticker],
        "quarter": brief["fiscal_quarter_label"],
        "brief_label": "Correction: Post-Earnings Summary",
        "report_date_label": "Reported 2026-09-02 -- After Close",
        "report_date": "2026-09-02",
        "report_time": "After Close",
        "reaction_line": "Shares moved following the print.",
        "reaction_pct": 1.0,
        "intro": brief["intro"],
        "financial_highlights": brief["financial_highlights"],
        "sections": brief["sections"],
        "key_metrics": brief["key_metrics"],
        "key_figures": brief["key_figures"],
        "official_links": brief["official_links"],
        "financials": brief["financials"],
        "qa_approved": brief["_qa_approved"],
        "qa_issues": brief["_qa_issues"],
    }


def test_verified_corrections_are_substantive_and_issuer_sourced():
    for ticker in ("AVGO", "HPE", "SNOW"):
        brief = verified_post_earnings_brief(ticker, "2026-09-02")
        assert brief["_qa_approved"] is True
        assert len(brief["financial_highlights"]) >= 3
        assert len(brief["sections"]) >= 1
        assert len(brief["key_metrics"]) >= 3
        assert brief["official_links"]["press_release"].startswith("https://")
        assert not delivery_context_issues(_context(ticker))


def test_unknown_release_date_has_no_fallback():
    assert verified_post_earnings_brief("SNOW", "2026-09-01") == {}


def test_empty_or_unreviewed_brief_is_blocked():
    issues = delivery_context_issues(
        {
            "qa_approved": False,
            "financial_highlights": [],
            "sections": [],
            "key_metrics": [],
            "official_links": {},
        }
    )
    assert "automated review did not approve the brief" in issues
    assert "fewer than three financial highlights" in issues
    assert "no substantive analysis section" in issues


def test_unapproved_model_draft_is_replaced_by_verified_fallback():
    unapproved = {
        "fiscal_quarter_label": "Q2 FY2027",
        "financial_highlights": [{"text": "Unreviewed", "children": []}],
        "sections": [{"heading": "Draft", "bullets": [{"text": "Unreviewed", "children": []}]}],
        "key_metrics": ["Unreviewed"],
        "official_links": {"press_release": "https://example.invalid"},
        "_qa_approved": False,
        "_qa_issues": ["official period unresolved"],
    }
    with patch(
        "pipelines.run_post_earnings_deep_dive_auto.fetch_financial_snapshot", return_value={}
    ), patch(
        "pipelines.run_post_earnings_deep_dive_auto.fetch_live_reaction_move",
        return_value={"ah_move_pct": 21.94, "source": "yfinance_live_postmarket"},
    ), patch(
        "pipelines.run_post_earnings_deep_dive_auto.synthesize_earnings_brief_with_review",
        return_value=unapproved,
    ):
        context = build_brief_context(
            {"ticker": "SNOW", "company": "Snowflake Inc.", "report_time": "After Close"},
            date(2026, 9, 2),
            correction=True,
        )
    assert context["qa_approved"] is True
    assert context["key_metrics"][0] == "Revenue: $1.547B, +35% YoY"
    assert not delivery_context_issues(context)


def test_draft_renders_without_archiving_or_requiring_recipient(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("DEAL_ALERT_EMAIL_TO", raising=False)
    with patch("pipelines.run_post_earnings_deep_dive_auto.archive_post_earnings_summary") as archive:
        assert send_deep_dive(_context(), tmp_path, draft_only=True)
    archive.assert_not_called()
    assert (tmp_path / "snow" / "snow_post_deep_dive.html").exists()
    assert (tmp_path / "snow" / "snow_post_deep_dive.md").exists()
