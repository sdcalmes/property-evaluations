import json
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from property_eval.build_site import build, check_privacy
from property_eval.scoring import score


ROOT = Path(__file__).resolve().parents[1]


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "source"
        for folder in ("data/properties", "evaluations", "templates", "static"):
            (self.root / folder).mkdir(parents=True)
        for file in ("buyer_profile.json", "templates/index.html", "templates/property.html", "static/style.css"):
            shutil.copy(ROOT / file, self.root / file)
        self.record = {
            "slug": "123-example-lane", "address": "123 Example Lane, Sample, WI",
            "status": "Active", "current_list_price": 500000,
            "above_grade_sqft": 2100, "below_grade_finished_sqft": 500,
            "lot_acres": 2.1, "buyer_fit_score": 7.2,
            "estimated_value_low": 460000, "estimated_value_high": 510000,
            "pricing_conclusion": "Fair", "major_positives": ["Garden space"],
            "major_concerns": ["Roof age unknown"], "uncertainties": ["Confirm easement"],
            "commutes": [{"destination": "Lisa's Work", "candidate_minutes": 38, "impact": "materially worse"}],
            "evaluation_date": "2026-09-29", "evaluation_markdown": "123-example-lane.md",
        }

    def save_record(self, narrative="# Example evaluation\n\nDetailed research.\n"):
        (self.root / "data/properties/123-example-lane.json").write_text(json.dumps(self.record))
        (self.root / "evaluations/123-example-lane.md").write_text(narrative)

    def test_site_and_project_path(self):
        self.save_record()
        output = build(self.root, Path(self.temp.name) / "render")
        index = (output / "index.html").read_text()
        detail = (output / "properties/123-example-lane/index.html").read_text()
        self.assertIn('href="/property-evaluations/static/style.css"', index)
        self.assertIn('href="/property-evaluations/properties/123-example-lane/"', index)
        self.assertIn('href="/property-evaluations/"', detail)
        self.assertIn("Detailed research.", detail)
        self.assertIn("2,100", detail)
        self.assertIn("500 sq ft", detail)
        self.assertIn("Lisa&#39;s Work", detail)
        self.assertNotIn("Secret Lane", detail)

    def test_empty_dashboard(self):
        output = build(self.root, Path(self.temp.name) / "render")
        self.assertIn("No evaluations saved yet", (output / "index.html").read_text())

    def test_estimated_commute_range_and_year_render(self):
        self.record["year_built"] = 2017
        self.record["commutes"] = [{"destination": "Lisa's Work", "candidate_minutes_range": "~34–39 min estimated", "impact": "longer"}]
        self.save_record()
        output = build(self.root, Path(self.temp.name) / "render")
        detail = (output / "properties/123-example-lane/index.html").read_text()
        self.assertIn("~34–39 min estimated", detail)
        self.assertIn("7.2/10", detail)
        self.assertIn("2017", detail)
        self.assertNotIn("2,017", detail)

    def test_private_address_fails_and_removes_output(self):
        profile = json.loads((self.root / "buyer_profile.json").read_text())
        profile["destinations"]["lisa_work"]["routing_address"] = "123 Secret Lane, Sample, WI"
        (self.root / "buyer_profile.json").write_text(json.dumps(profile))
        self.save_record("# Research\n\n123 Secret Lane, Sample, WI\n")
        output = Path(self.temp.name) / "render"
        with self.assertRaisesRegex(ValueError, "Private destination"):
            build(self.root, output)
        self.assertFalse(output.exists())

    def test_hashed_street_guard(self):
        output = Path(self.temp.name) / "render"
        output.mkdir()
        (output / "index.html").write_text("<p>123 Secret Lane</p>")
        digest = hashlib.sha256(b"123 secret lane").hexdigest()
        profile = json.loads((self.root / "buyer_profile.json").read_text())
        with patch("property_eval.build_site.PRIVATE_STREET_SHA256", {digest}):
            with self.assertRaisesRegex(ValueError, "Private destination"):
                check_privacy(output, profile)


class ToolkitTests(unittest.TestCase):
    def test_buyer_fit_is_renormalized_and_not_valuation(self):
        profile = json.loads((ROOT / "buyer_profile.json").read_text())
        result = score({"address": "Synthetic", "ratings": {"kitchen": 8, "garden": 4}}, profile)
        self.assertEqual(result["fit_score_0_to_10"], 6.67)
        self.assertEqual(result["weight_coverage_percent"], 24.0)
        self.assertTrue(any("Garden" in flag for flag in result["flags"]))
        self.assertIn("not use to derive market value", result["warning"])


if __name__ == "__main__":
    unittest.main()
