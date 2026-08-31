import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pipelines import build_weekly_earnings_brief as brief_builder
from pipelines import earnings_archive
from pipelines import render_weekly_earnings_email as email_renderer


def coverage_event(**overrides):
    values = {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "report_date": date(2026, 9, 2),
        "report_time": "After Close",
        "score_reasons": "coverage universe",
        "market_cap_b": 4_100.0,
        "implied_move_pct": None,
        "financial_snapshot": {},
        "what_matters": "AI infrastructure demand remains the central read-through.",
        "newsletter_digest": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_convex_request_converts_non_finite_numbers_to_null():
    response = MagicMock()
    response.read.return_value = b'{"status":"success","value":{"ok":true}}'
    response.__enter__.return_value = response

    with patch("urllib.request.urlopen", return_value=response) as open_url:
        result = earnings_archive._convex_request(
            convex_url="https://example.convex.cloud",
            kind="mutation",
            path="preEarningsSnapshots:upsertSnapshot",
            args={"valid": 12.5, "nan": float("nan"), "nested": [float("inf"), -float("inf")]},
        )

    body = json.loads(open_url.call_args.args[0].data.decode("utf-8"))
    assert result == {"ok": True}
    assert body["args"] == {"valid": 12.5, "nan": None, "nested": [None, None]}


def test_financial_enrichment_uses_report_date_consensus_cache():
    event = coverage_event(market_cap_b=None)
    with (
        patch("pipelines.earnings_archive.load_financial_snapshot_artifact", return_value={}),
        patch(
            "pipelines.earnings_archive.fetch_pre_earnings_snapshot",
            return_value={
                "revenueConsensusUsd": 2_555_302_330,
                "revenueConsensusYoyPct": 110.7,
                "fyRevenueConsensusUsd": 12_627_718_540,
                "fyRevenueConsensusYoyPct": 146.1,
                "epsConsensus": 6.42,
            },
        ) as cached_fetch,
        patch("pipelines.earnings_archive.archive_pre_earnings_snapshot"),
        patch("core.stock_data.fetch_financial_snapshot", return_value={"market_cap_b": 50.11}),
    ):
        brief_builder.enrich_financial_snapshots([event])

    cached_fetch.assert_called_once_with("NVDA", "2026-09-02")
    assert event.financial_snapshot["next_q_revenue_consensus"] == 2_555_302_330
    assert event.financial_snapshot["fy_yoy_pct"] == 146.1
    assert event.financial_snapshot["eps_consensus"] == 6.42


def test_metric_quality_does_not_count_market_cap_alone():
    quality = brief_builder.financial_snapshot_quality(
        [coverage_event(financial_snapshot={"market_cap_b": 50.11})]
    )
    assert quality["events_with_company_metrics"] == 0
    assert quality["missing_tickers"] == ["NVDA"]


def test_weekly_signal_grid_omits_na_and_promotes_cached_estimates():
    event = coverage_event(
        financial_snapshot={
            "next_q_revenue_consensus": 2_555_302_330,
            "next_q_yoy_pct": 110.7,
            "fy_revenue_consensus": 12_627_718_540,
            "fy_yoy_pct": 146.1,
        }
    )

    html = email_renderer._render_event_block(event)

    assert "N/A" not in html
    assert "Mkt Cap" in html
    assert "Next Qtr Est (YoY)" in html
    assert "FY Est (YoY)" in html
