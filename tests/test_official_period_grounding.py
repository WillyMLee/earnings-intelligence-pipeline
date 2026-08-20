import unittest

from core.synthesis import _extract_official_fiscal_period, _html_release_text, _sanity_check_brief


class OfficialPeriodGroundingTests(unittest.TestCase):
    def test_current_official_release_beats_stale_prior_quarter(self):
        results = [
            {
                "title": "Walmart releases Q1 FY27 earnings",
                "url": "https://corporate.walmart.com/news/2026/05/earnings",
                "snippet": "Quarterly results from May.",
                "published_date": "2026-05-21",
            },
            {
                "title": "Walmart releases Q2 FY27 earnings",
                "url": "https://corporate.walmart.com/news/2026/08/20/walmart-releases-q2-fy27-earnings",
                "snippet": "Official earnings release and financial results for August 20, 2026.",
                "published_date": "2026-08-20",
            },
        ]

        self.assertEqual(
            _extract_official_fiscal_period(results, "2026-08-20", "Walmart Inc."),
            "Q2 FY2027",
        )

    def test_ambiguous_undated_results_do_not_create_a_period_gate(self):
        results = [
            {
                "title": "Acme Q1 FY27 earnings release",
                "url": "https://acme.example/q1",
                "snippet": "Financial results",
            },
            {
                "title": "Acme Q2 FY27 earnings release",
                "url": "https://acme.example/q2",
                "snippet": "Financial results",
            },
        ]

        self.assertEqual(_extract_official_fiscal_period(results, "2026-08-20", "Acme Corp"), "")

    def test_issuer_html_is_reduced_to_visible_release_text(self):
        html = "<html><script>wrong quarter</script><body><h1>Q2 FY27</h1><p>Revenue of $187.9 billion</p></body></html>"
        self.assertEqual(_html_release_text(html), "Q2 FY27 Revenue of $187.9 billion")

    def test_structured_headlines_must_match_direct_issuer_text(self):
        brief = {
            "fiscal_quarter_label": "Q2 FY2027",
            "financials": {"revenue_actual_usd": 177_000_000_000, "eps_actual": 1.80},
            "financial_highlights": [],
            "key_metrics": [
                "U.S. comparable sales: +3.6% YoY",
                "Capital expenditures: $6.68 billion for the quarter",
            ],
            "sections": [],
        }
        facts = {
            "official_fiscal_quarter_label": "Q2 FY2027",
            "official_release_source_text": (
                "Revenue of $187.9 billion. Adjusted EPS1 of $0.81. "
                "Walmart U.S. comp sales grew 2.6%."
            ),
        }
        issues = _sanity_check_brief(brief, facts=facts)
        self.assertTrue(any("revenue_actual_usd conflicts" in issue for issue in issues))
        self.assertTrue(any("eps_actual conflicts" in issue for issue in issues))
        self.assertTrue(any("2.6% for that category" in issue for issue in issues))
        self.assertTrue(any("CapEx amount" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
