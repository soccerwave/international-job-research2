import unittest

from src.sources.core import corehr, portals
from src.sources.shared.common import html_to_text


class Stage6DetailExtractionTests(unittest.TestCase):
    def test_empty_main_falls_back_to_body_content(self):
        html = """
        <html>
          <body>
            <header>Navigation noise</header>
            <main></main>
            <section id="job-content">
              <h1>Postdoctoral Research Fellow</h1>
              <p>{body}</p>
            </section>
          </body>
        </html>
        """.format(body="Exercise neuroscience and stress biology research. " * 20)
        text = html_to_text(html)
        self.assertIn("Postdoctoral Research Fellow", text)
        self.assertIn("Exercise neuroscience", text)
        self.assertNotIn("Navigation noise", text)
        self.assertGreater(len(text), 200)

    def test_form_wrapper_preserves_job_content(self):
        html = """
        <html>
          <body>
            <form action="/search">
              <main></main>
              <section id="job-content">
                <h1>Research Fellow in Brain Health</h1>
                <p>{body}</p>
              </section>
              <button type="submit">Apply</button>
            </form>
          </body>
        </html>
        """.format(body="Brain health, cognition, and stress research. " * 20)
        text = html_to_text(html)
        self.assertIn("Research Fellow in Brain Health", text)
        self.assertIn("Brain health, cognition", text)
        self.assertNotIn("Apply", text)
        self.assertGreater(len(text), 200)

    def test_academics_explicit_china_marker_is_not_defaulted_to_germany(self):
        self.assertEqual(portals.infer_academics_country("Hainan (China) Vollzeit Befristet"), "CN")

    def test_corehr_detail_heading_can_upgrade_truncated_listing_title(self):
        html = """
        <html><body>
          <h1>Professor In Pharmacy (Pharmaceutics)</h1>
          <div>Closing Date: 17/09/2026</div>
          <p>{body}</p>
        </body></html>
        """.format(body="Academic pharmacy research and teaching. " * 20)
        parsed = corehr.parse_detail(html, "Professor In")
        self.assertEqual(parsed["title"], "Professor In Pharmacy (Pharmaceutics)")
        self.assertIn("Academic pharmacy research", parsed["description"])

    def test_corehr_vacancy_banner_ignores_navigation_occurrence(self):
        html = """
        <html><body>
          Search Vacancies Login Register Job Specification Terms and Conditions
          University of Galway Vacancies Professor In Pharmacy, Full-Time, Permanent
          Applications are invited for a Professor In Pharmacy (Pharmaceutics) at University of Galway.
          <p>{body}</p>
        </body></html>
        """.format(body="Academic pharmacy research and teaching. " * 20)
        parsed = corehr.parse_detail(html, "Professor In")
        self.assertEqual(parsed["title"], "Professor In Pharmacy")


if __name__ == "__main__":
    unittest.main()
