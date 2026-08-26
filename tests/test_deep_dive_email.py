from pipelines.render_pre_earnings_deep_dive_email import render_deep_dive_email, render_markdown_summary


def _context():
    return {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "quarter": "Q2 FY2027",
        "brief_label": "Correction: Pre-Earnings Summary",
        "report_date_label": "Reports 2026-08-26 -- AMC",
        "key_figures": [
            {"label": "Street revenue", "value": "$92.2B"},
            {"label": "Street EPS", "value": "$2.09"},
            {"label": "Company guide", "value": "$91.0B ±2%"},
        ],
        "intro": "NVIDIA reports after the close.\n\n## Stock market information\n- raw tool output",
        "financial_highlights": [
            {"text": f"Metric {index}: useful detail", "children": []} for index in range(8)
        ],
        "sections": [
            {
                "heading": f"Section {section}",
                "bullets": [{"text": f"Point {item}", "children": []} for item in range(6)],
            }
            for section in range(5)
        ],
        "key_metrics": [f"Watch {index}" for index in range(8)],
        "official_links": {"press_release": "https://investor.nvidia.com/results"},
    }


def test_email_restores_key_figures_and_hides_raw_tool_output():
    html = render_deep_dive_email(_context())
    assert "Key figures" in html
    assert "Reports 2026-08-26 -- AMC" in html
    assert "Street revenue" in html
    assert "Stock market information" not in html
    assert "raw tool output" not in html
    assert "<strong>Metric 0</strong>" in html


def test_email_enforces_compact_section_and_bullet_limits():
    html = render_deep_dive_email(_context())
    assert "Metric 5" in html
    assert "Metric 6" not in html
    assert "Section 2" in html
    assert "Section 3" not in html
    assert "Point 3" in html
    assert "Point 4" not in html
    assert "Watch 5" in html
    assert "Watch 6" not in html


def test_markdown_matches_compact_email_contract():
    markdown = render_markdown_summary(_context())
    assert "**Street revenue:** $92.2B" in markdown
    assert "Stock market information" not in markdown
    assert "Section 3" not in markdown
