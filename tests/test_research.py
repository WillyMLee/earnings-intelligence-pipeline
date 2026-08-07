import unittest

from core.research import _extract_focused_excerpts


class TranscriptExcerptTests(unittest.TestCase):
    def test_prioritizes_guidance_and_qa_over_boilerplate(self):
        boilerplate = (
            "Forward-looking statements are subject to risks and uncertainties. " * 18
        )
        guidance = (
            "Analyst question-and-answer. The CFO said revenue guidance is $9.2 billion, "
            "gross margin should reach 72%, and backlog demand remains strong. " * 8
        )
        excerpt = _extract_focused_excerpts(boilerplate + (" filler " * 220) + guidance, max_total=1200, window=600)

        self.assertIn("revenue guidance", excerpt.lower())
        self.assertIn("gross margin", excerpt.lower())
        self.assertLessEqual(len(excerpt), 1208)

    def test_falls_back_to_bounded_text_when_no_signals_exist(self):
        text = "ordinary prepared remarks " * 100
        self.assertEqual(_extract_focused_excerpts(text, max_total=250), text[:250])


if __name__ == "__main__":
    unittest.main()
