import unittest
from unittest.mock import patch

from core.earnings_orchestration import (
    build_earnings_research_plan,
    classify_provider_error,
    provider_waterfall,
)
from core.research import run_research_query_cascade


class EarningsOrchestrationTests(unittest.TestCase):
    def test_llmlayer_is_first_for_every_research_kind(self):
        for kind in ("discovery", "primary_source", "transcript"):
            self.assertEqual(provider_waterfall(kind)[0], "llmlayer")

    def test_exa_opt_in_does_not_displace_llmlayer(self):
        self.assertEqual(provider_waterfall("discovery", include_exa=True)[:2], ("llmlayer", "exa"))

    def test_post_plan_runs_inputs_in_parallel_then_reconciles(self):
        plan = build_earnings_research_plan("IBM", "International Business Machines", "2026-10-21", "post", "AMC")
        stages = {stage["key"]: stage for stage in plan["stages"]}

        self.assertEqual(plan["instance_id"], "earnings-ibm-2026-10-21-post-v1")
        self.assertEqual(stages["fetch_transcript"]["source_priority"][0], "LLMLayer")
        self.assertEqual(stages["collect_official_results"]["parallel_group"], "post_inputs")
        self.assertIn("fetch_transcript", stages["reconcile_evidence"]["depends_on"])
        self.assertEqual(stages["review_archive_and_deliver"]["failure_mode"], "quarantine_no_send")

    def test_pre_plan_requires_a_dated_consensus_capture(self):
        plan = build_earnings_research_plan("MSFT", "Microsoft", "2026-10-28", "pre")
        capture = next(stage for stage in plan["stages"] if stage["key"] == "capture_consensus")
        self.assertIn("captured_at", capture["required_outputs"])
        self.assertIn("capture is earlier than report timestamp", capture["quality_gates"])

    def test_quota_errors_are_non_retryable_provider_failures(self):
        self.assertEqual(classify_provider_error(RuntimeError("HTTP 433: paygo limit")), "quota_exhausted")
        self.assertEqual(classify_provider_error(RuntimeError("HTTP 429: slow down")), "rate_limited")

    @patch("core.research.search_tinyfish")
    @patch("core.research.search_tavily")
    @patch("core.research.search_llmlayer")
    def test_cascade_stops_after_sufficient_llmlayer_results(self, llmlayer, tavily, tinyfish):
        llmlayer.return_value = [
            {"provider": "llmlayer", "title": "One", "url": "https://one.test", "published_date": "2026-08-14"},
            {"provider": "llmlayer", "title": "Two", "url": "https://two.test", "published_date": "2026-08-13"},
        ]
        with patch.dict(
            "os.environ",
            {"LLMLAYER_API_KEY": "test", "TAVILY_API_KEY": "test", "TINYFISH_API_KEY": "test"},
            clear=True,
        ):
            result = run_research_query_cascade("test query")

        self.assertEqual(result["primary_provider"], "llmlayer")
        self.assertFalse(result["fallback_used"])
        self.assertFalse(result["degraded"])
        tavily.assert_not_called()
        tinyfish.assert_not_called()

    @patch("core.research.search_tinyfish")
    @patch("core.research.search_tavily")
    @patch("core.research.search_llmlayer")
    def test_quota_failure_falls_through_without_failing_the_query(self, llmlayer, tavily, tinyfish):
        llmlayer.return_value = []
        tavily.side_effect = RuntimeError("HTTP 433: paygo limit reached")
        tinyfish.return_value = [
            {"provider": "tinyfish", "title": "Fallback", "url": "https://fallback.test", "published_date": "2026-08-14"}
        ]
        with patch.dict(
            "os.environ",
            {"LLMLAYER_API_KEY": "test", "TAVILY_API_KEY": "test", "TINYFISH_API_KEY": "test"},
            clear=True,
        ):
            result = run_research_query_cascade("test query")

        self.assertEqual(result["primary_provider"], "tinyfish")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["results"][0]["provider"], "tinyfish")
        self.assertEqual(result["provider_attempts"][1]["error_kind"], "quota_exhausted")


if __name__ == "__main__":
    unittest.main()
