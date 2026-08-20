import unittest

from core.synthesis import _extract_official_fiscal_period


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


if __name__ == "__main__":
    unittest.main()
