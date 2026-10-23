import json
from unittest.mock import Mock

import pytest

from core import reporting_currency as fx


def rate(currency="EUR", value=1.12, day="2026-10-22"):
    return fx._valid_rate(currency, day, day, value, "ECB test reference", fx.ECB_URL)


@pytest.fixture
def fixed_fx(monkeypatch):
    def get(currency, day):
        return rate(currency, {"USD": 1, "EUR": 1.12, "KRW": 0.0008}[currency])
    monkeypatch.setattr(fx, "get_usd_rate", get)


def test_eur_report_converts_amounts_ranges_and_eps_but_not_growth_or_usd_quotes(fixed_fx):
    native = {"intro": "Revenue €4.969 billion; guidance €5.0–5.2 billion; EPS €2.48; growth 16%; margin 33%; stock $583.66.", "financials": {"revenue_actual_usd": 4_969_000_000, "eps_actual": 2.48, "revenue_yoy_pct": 16}, "key_metrics": ["Revenue €4.969B"], "key_figures": [{"label": "Revenue (EUR)", "value": "€4.969B"}]}
    result = fx.normalize_brief("SPOT", native, "EUR", "2026-10-22")
    assert "$5.57B (€4.969 billion)" in result["intro"]
    assert "$5.60B–$5.82B" in result["intro"]
    assert "$2.78 (€2.48)" in result["intro"]
    assert "16%" in result["intro"] and "33%" in result["intro"]
    assert "$583.66" in result["intro"]
    assert result["financials"]["revenue_actual_usd"] == pytest.approx(5_565_280_000)
    assert result["financials"]["eps_actual"] == pytest.approx(2.7776)
    assert result["financials"]["revenue_yoy_pct"] == 16
    assert result["key_figures"][0]["label"] == "Revenue (USD)"
    assert "2026-10-22" in result["key_metrics"][0]
    assert result["currency_normalization"]["native_financials"] == native["financials"]
    assert native["intro"].startswith("Revenue €")
    assert fx.normalize_brief("SPOT", result, "EUR", "2026-10-23") == result


def test_won_trillions_suffixes_and_eps_keep_the_correct_scale(fixed_fx):
    native = {"intro": "Revenue KRW 17.57 trillion; net income 4.2 trillion won; guidance ₩16–17 trillion; EPS KRW 25,000.", "financials": {"revenue_actual_usd": 17.57e12, "eps_actual": 25000}}
    result = fx.normalize_brief("000660.KS", native, "KRW", "2026-10-22")
    assert "$14.06B" in result["intro"]
    assert "$3.36B" in result["intro"]
    assert "$12.80B–$13.60B" in result["intro"]
    assert "$20.00" in result["intro"]
    assert result["financials"]["revenue_actual_usd"] == pytest.approx(14.056e9)
    assert fx.financial_currency("000660.KS") == "KRW"
    assert fx.financial_currency("SK Hynix") == "KRW"


def test_quotes_and_financials_use_their_separate_currency(fixed_fx):
    spot = fx.normalize_snapshot("SPOT", {"financial_currency": "EUR", "quote_currency": "USD", "last_q_revenue": 4.969e9, "price": 583.66, "market_cap_b": 120}, "2026-10-22")
    assert spot["price"] == 583.66
    assert spot["market_cap_b"] == 120
    assert spot["last_q_revenue"] == pytest.approx(5.56528e9)
    hynix = fx.normalize_snapshot("000660.KS", {"financial_currency": "KRW", "quote_currency": "KRW", "last_q_revenue": 17.57e12, "price": 250000, "market_cap_b": 180000}, "2026-10-22")
    assert hynix["price"] == 200
    assert hynix["market_cap_b"] == 144
    assert hynix["currency_normalization"]["native_snapshot"]["price"] == 250000
    assert fx.normalize_snapshot("000660.KS", hynix, "2026-10-23") == hynix


def test_ecb_cross_rate_direction_and_weekend_selection(monkeypatch):
    fx.get_usd_rate.cache_clear()
    monkeypatch.setattr(fx, "_ecb_days", lambda: (("2020-03-16", {"USD": 2, "KRW": 1000}), ("2020-03-13", {"USD": 1.12, "KRW": 1400})))
    result = fx.get_usd_rate("KRW", "2020-03-15")
    assert result["usd_per_unit"] == pytest.approx(0.0008)
    assert result["rate_date"] == "2020-03-13"
    assert result["source_url"] == fx.ECB_URL
    fx.get_usd_rate.cache_clear()


def test_usd_is_identity_and_does_not_need_an_fx_provider(monkeypatch):
    fx.get_usd_rate.cache_clear()
    monkeypatch.setattr(fx, "_fetch", Mock(side_effect=AssertionError("USD must not use network")))
    assert fx.get_usd_rate("USD", "2020-03-15")["usd_per_unit"] == 1
    native = {"intro": "Revenue $10B", "financials": {"revenue_actual_usd": 10e9}}
    assert fx.normalize_brief("AAPL", native, "USD", "2020-03-15") == native
    fx.get_usd_rate.cache_clear()


def test_missing_stale_and_future_rates_cannot_relabel_amounts(monkeypatch):
    for day in ["2020-03-01", "2020-03-16"]:
        with pytest.raises(ValueError): fx._valid_rate("EUR", "2020-03-15", day, 1.1, "test", "https://source.example")
    fx.get_usd_rate.cache_clear()
    monkeypatch.setattr(fx, "_ecb_days", lambda: ())
    monkeypatch.setattr(fx, "_fetch", lambda _: b"[]")
    with pytest.raises(ValueError): fx.normalize_brief("SPOT", {"intro": "Revenue €10B"}, "EUR", "2020-03-15")
    fx.get_usd_rate.cache_clear()


def test_foreign_consensus_archive_stores_usd_and_native_audit_record(monkeypatch, fixed_fx):
    from pipelines import earnings_archive as archive
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setenv("EARNINGS_ARCHIVE_TOKEN", "test")
    calls = []
    monkeypatch.setattr(archive, "_convex_request", lambda **kwargs: calls.append(kwargs) or {"ok": True})
    result = archive.archive_pre_earnings_snapshot(ticker="SPOT", report_date="2026-10-22", captured_at="2026-10-21T08:00:00-04:00", snap={"financial_currency": "EUR", "next_q_revenue_consensus": 5e9}, eps_consensus=2.5)
    assert result["status"] == "archived"
    assert calls[0]["args"]["revenueConsensusUsd"] == pytest.approx(5.6e9)
    assert calls[0]["args"]["epsConsensus"] == pytest.approx(2.8)
    assert "USD-normalized;" in calls[0]["args"]["consensusSource"]
    artifact = json.loads(calls[1]["args"]["text"])
    assert artifact["_native_consensus"]["revenue"] == 5e9
    assert artifact["_native_consensus"]["eps"] == 2.5
    assert artifact["currency_normalization"]["source_currency"] == "EUR"


def test_reading_normalized_snapshot_preserves_original_consensus_for_post_comparison(monkeypatch):
    from pipelines import earnings_archive as archive
    monkeypatch.setenv("CONVEX_URL", "https://example.convex.cloud")
    monkeypatch.setattr(archive, "_convex_request", lambda **_: {"capturedAt": "2026-10-21T08:00:00-04:00", "revenueConsensusUsd": 5.6e9, "consensusSource": "USD-normalized; FX evidence"})
    monkeypatch.setattr(archive, "load_financial_snapshot_artifact", lambda **_: {"_native_consensus": {"currency": "EUR", "revenue": 5e9, "eps": 2.5}})
    row = archive.fetch_pre_earnings_snapshot("SPOT", "2026-10-22")
    assert row["revenueConsensusUsd"] == 5.6e9
    assert row["_native_consensus"]["revenue"] == 5e9


def test_valuation_multiple_is_recomputed_using_normalized_inputs(fixed_fx):
    brief = {"valuation_reference": {"enterprise_value": "$112B", "cy_revenue": "€10B", "ev_cy_revenue": "11.2x (invalid mixed currencies)"}}
    result = fx.normalize_brief("SPOT", brief, "EUR", "2026-10-22")
    assert result["valuation_reference"]["ev_cy_revenue"] == "~10.0x (USD-normalized inputs)"


def test_non_ecb_rate_retains_underlying_provider_observations(monkeypatch):
    fx.get_usd_rate.cache_clear()
    monkeypatch.setattr(fx, "_ecb_days", lambda: ())
    observations = [{"key": "BOE", "date": "2020-03-13", "rate": 0.03}]
    monkeypatch.setattr(fx, "_fetch", lambda _: json.dumps([{"base": "TWD", "quote": "USD", "date": "2020-03-13", "rate": 0.03, "providers": observations}]).encode())
    result = fx.get_usd_rate("TWD", "2020-03-15")
    assert result["usd_per_unit"] == 0.03
    assert result["provider_observations"] == observations
    fx.get_usd_rate.cache_clear()


def test_post_pipeline_normalizes_verified_native_results_and_preserves_consensus(monkeypatch, fixed_fx):
    from datetime import date
    from pipelines import run_post_earnings_deep_dive_auto as post
    snapshot = fx.normalize_snapshot("SPOT", {"financial_currency": "EUR", "quote_currency": "USD", "last_q_revenue": 4e9, "price": 500}, "2026-10-22")
    monkeypatch.setattr(post, "fetch_financial_snapshot", lambda _: snapshot)
    monkeypatch.setattr(post, "fetch_pre_earnings_snapshot", lambda *_: {"revenueConsensusUsd": 5.5e9, "_native_consensus": {"revenue": 5e9, "eps": 2.5}})
    monkeypatch.setattr(post, "fetch_live_reaction_move", lambda *_, **__: {})
    brief = {"_qa_approved": True, "intro": "Revenue €5.1 billion", "financial_highlights": [{"text": "Revenue €5.1 billion"}] * 3, "sections": [{"heading": "Guidance", "bullets": [{"text": "Revenue €5.2 billion"}]}], "key_metrics": ["Revenue €5.1B", "EPS €2.50", "Margin 33%"], "official_links": {"press_release": "https://issuer.example/results"}, "financials": {"revenue_actual_usd": 5.1e9, "revenue_consensus_usd": 5e9, "eps_actual": 2.5}}
    synthesis = Mock(return_value=brief)
    monkeypatch.setattr(post, "synthesize_earnings_brief_with_review", synthesis)
    result = post.build_brief_context({"ticker": "SPOT", "company": "Spotify", "report_time": "Before Open"}, date(2026, 10, 22))
    assert synthesis.call_args.args[4]["next_q_revenue_consensus"] == 5e9
    assert synthesis.call_args.args[4]["last_q_revenue"] == 4e9
    assert result["financials"]["revenue_actual_usd"] == pytest.approx(5.712e9)
    assert result["financials"]["revenue_consensus_usd"] == pytest.approx(5.6e9)
    assert result["currency_normalization"]["source_currency"] == "EUR"
    assert "$5.71B" in result["intro"]


def test_renderer_keeps_fx_disclosure_and_qa_after_three_narrative_sections(fixed_fx):
    from pipelines.render_pre_earnings_deep_dive_email import render_deep_dive_email, render_markdown_summary
    brief = {"company": "Spotify", "ticker": "SPOT", "quarter": "Q3", "sections": [{"heading": f"Narrative {i}", "bullets": [{"text": "Analysis"}]} for i in range(3)] + [{"heading": "Analyst Q&A", "bullets": [{"text": "Current-quarter analyst question and management answer"}]}]}
    result = fx.normalize_brief("SPOT", brief, "EUR", "2026-10-22")
    for rendered in (render_deep_dive_email(result), render_markdown_summary(result)):
        assert "Currency normalization" in rendered
        assert "Current-quarter analyst question and management answer" in rendered
        assert "2026-10-22" in rendered
