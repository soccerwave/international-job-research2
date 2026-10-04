import unittest

from src.sources.shared import euraxess


class EuraxessExternalLinkTests(unittest.TestCase):
    def test_parse_listing_rejects_external_jobs_paths(self):
        html = """
        <div id="job-teaser-content">
          <div class="ecl-content-block__label-container">
            <span class="ecl-label">JOB</span>
            <span class="ecl-label">Croatia</span>
          </div>
          <a href="https://www.science.hr/jobs/244480/example-role">External mirror</a>
          <a href="/jobs/60761872">EURAXESS role</a>
        </div>
        """
        rows = euraxess.parse_listing(html)
        self.assertEqual([row["id"] for row in rows], ["60761872"])
        self.assertEqual(rows[0]["url"], "https://euraxess.ec.europa.eu/jobs/60761872")


if __name__ == "__main__":
    unittest.main()
