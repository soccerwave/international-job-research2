import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from src.sources.core import corehr, pageup, portals, smartrecruiters, successfactors, university_vacancies, workday
from src.sources.shared.common import make_record

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "vacancy.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


class Stage6CoreSourceTests(unittest.TestCase):
    def assert_schema(self, record):
        errors = list(VALIDATOR.iter_errors(record))
        self.assertFalse(errors, "\n".join(error.message for error in errors))

    def test_core_record_contract_remains_stage3_schema(self):
        row = make_record(
            source_key="stage6_test", source_kind="ATS", provider="University X",
            source_job_id="123", listing_url="https://example.org/jobs",
            detail_url="https://example.org/jobs/123", title="Postdoctoral Researcher",
            country_code="AU", country_name="Australia", full_jd="Research role. " * 40,
            detail_status="FULL",
        )
        self.assert_schema(row)
        self.assertEqual(row["record_stage"], "SHARD_ENRICHED")
        self.assertEqual(row["position"]["role_family"], "UNKNOWN")

    def test_academictransfer_parser(self):
        html = '''<article><a href="/en/jobs/363711/postdoctoral-researcher-stress/">Postdoctoral Researcher in Stress</a>
        <div>University X | Deadline 30 September 2026 | Published 4 September 2026 Amsterdam</div></article>'''
        rows = portals.parse_academictransfer_listing(html)
        self.assertEqual(rows[0]["id"], "363711")
        self.assertIn("Stress", rows[0]["title"])

    def test_academics_parser_and_foreign_override(self):
        html = '''<div><a href="https://www.academics.de/jobs/postdoctoral-researcher-universitaet-regensburg-1110998">Postdoctoral Researcher</a>
        <span>Universität Regensburg, Regensburg, Deutschland</span></div>
        <div><a href="https://www.academics.de/jobs/postdoc-university-vienna-1110999">Postdoc Vienna</a>
        <span>Universität Wien, Österreich</span></div>'''
        rows = portals.parse_academics_listing(html)
        self.assertEqual(rows[0]["id"], "1110998")
        self.assertEqual(rows[0]["country_code"], "DE")
        self.assertEqual(rows[1]["country_code"], "AT")

    def test_university_vacancies_node_parser(self):
        html = '''<article><a href="/node/36980">Postdoctoral Research Fellow in Neuroscience</a>
        <div>University College Dublin | Reference 019345 | Closing Date 20 September 2026</div></article>'''
        rows = portals.parse_university_vacancies_listing(html)
        self.assertEqual(rows[0]["id"], "019345")
        self.assertIn("Postdoctoral", rows[0]["title"])

    def test_university_vacancies_api_parser(self):
        payload = {
            "statusCode": 200,
            "message": "Success",
            "data": {
                "jobPosts": [{
                    "id": 731,
                    "title": "Postdoctoral Researcher in Exercise Neuroscience",
                    "slug": "postdoctoral-researcher-in-exercise-neuroscience",
                    "reference": "011950",
                    "description": "<p>Exercise neuroscience and stress biology research.</p>" * 20,
                    "applyUrl": "https://example.edu/jobs/011950",
                    "status": "published",
                    "publishedAt": "2026-09-04T15:05:00.634Z",
                    "closingDate": "2026-09-25T17:00:00.000Z",
                    "source": "corehr",
                    "institution": {"id": 1, "slug": "university-of-galway", "institutionName": "University of Galway"},
                    "category": {"id": 3, "name": "Research"},
                    "jobType": {"id": 1, "name": "FULL_TIME", "displayName": "Full Time"},
                }],
                "pagination": {"page": 1, "limit": 1, "total": 1},
            },
        }
        rows = university_vacancies.parse_search_payload(payload)
        self.assertEqual(rows[0]["id"], "731")
        self.assertEqual(rows[0]["reference"], "011950")
        self.assertEqual(rows[0]["institution"], "University of Galway")
        self.assertEqual(rows[0]["deadline"], "2026-09-25")
        self.assertGreater(len(rows[0]["description"]), 200)

    def test_cnrs_parser(self):
        html = '''<div><a href="/Offres/CDD/UPR1234-ABCDEF-001/Default.aspx">Post-doctorant en neurosciences du stress</a>
        <span>CNRS Paris</span></div>'''
        rows = portals.parse_cnrs_listing(html)
        self.assertEqual(len(rows), 1)
        self.assertIn("Post-doctorant", rows[0]["title"])

    def test_uniroles_parser(self):
        html = '''<article><h3>Postdoctoral Research Fellow</h3><div>Employer: University X | Closing: 30 September 2026</div>
        <a href="https://uniroles.com.au/job/123456/postdoctoral-research-fellow/">Postdoctoral Research Fellow</a></article>'''
        rows = portals.parse_uniroles_listing(html)
        self.assertEqual(rows[0]["id"], "123456")
        self.assertEqual(rows[0]["institution"], "University X")

    def test_innsbruck_parser(self):
        html = '''<tr><td>University Assistant Postdoc</td><td>Closing date: 30.09.2026</td>
        <td><a href="/public/karriereportal.details?asg_id_in=14567">University Assistant Postdoc</a></td></tr>'''
        rows = portals.parse_innsbruck_listing(html)
        self.assertEqual(rows[0]["id"], "14567")

    def test_corehr_listing_and_detail(self):
        listing = '''<table><tr><td>Post Doctoral Researcher in Brain Health</td><td>Closing Date: 25/09/2026</td>
        <td><a href="erq_jobspec_version_4.display_form?p_recruitment_id=019345&p_form_profile_detail=&p_company=5023">Job Spec More -&gt;</a></td></tr></table>'''
        rows = corehr.parse_listing(listing, "https://my.corehr.com/pls/uccrecruit/search")
        self.assertEqual(rows[0]["id"], "019345")
        self.assertIn("Post Doctoral", rows[0]["title"])
        detail = corehr.parse_detail('<main>Job Title: Post Doctoral Researcher | Closing Date: 25/09/2026 | Full description '+('brain health research ' * 30)+'</main>')
        self.assertIn("Post Doctoral", detail["title"])
        self.assertIn("25/09/2026", detail["deadline"])

    def test_corehr_selects_search_form_not_login_form(self):
        html = '''
        <form name="callTheLoginFromNav" action="erq_login_package.build_login_screen" method="post">
          <input type="hidden" name="p_company" value="5023">
        </form>
        <form name="callErecruitDoSearch" action="erq_search_version_4.start_search_with_params" method="post">
          <input type="hidden" name="p_company" value="5023">
          <input type="hidden" name="p_internal_external" value="E">
          <select name="p_competition_type"><option value="ALLOPTIONS" selected>All</option></select>
          <input type="text" name="p_recruitment_id" value="">
          <input type="text" name="p_keywords" value="">
          <input type="hidden" name="p_force_type" value="E">
        </form>'''
        action, payload = corehr._form_payload_and_action(html, "https://my.corehr.com/pls/uccrecruit/search")
        self.assertTrue(action.endswith("erq_search_version_4.start_search_with_params"))
        self.assertIn(("p_company", "5023"), payload)
        self.assertIn(("p_competition_type", "ALLOPTIONS"), payload)

    def test_corehr_current_javascript_vacancy_links(self):
        html = '''<input type="hidden" name="p_company" value="5023">
        <table><tr>
          <td><a href="javascript:viewTheJobSpec('098933')">Post-Doctoral Researcher (Systems Neuroscientist) - APC Microbiome</a></td>
          <td>Job ID : 098933</td><td>Close Date : 25-Sep-2026 12:00</td>
          <td><a href="javascript:viewTheJobSpec('098933')">Job Spec More-&gt;</a></td>
        </tr></table>'''
        rows = corehr.parse_listing(html, "https://my.corehr.com/pls/uccrecruit/erq_search_version_4.start_search_with_params")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "098933")
        self.assertIn("Systems Neuroscientist", rows[0]["title"])
        self.assertIn("erq_jobspec_version_4.display_form", rows[0]["url"])
        self.assertIn("p_recruitment_id=098933", rows[0]["url"])
        self.assertIn("p_company=5023", rows[0]["url"])

    def test_pageup_parser(self):
        html = '''<article><a href="/513/ind/en/job/684321/postdoctoral-research-fellow">Postdoctoral Research Fellow</a>
        <div>Location: Clayton campus | Applications Close: 30 September 2026</div></article>'''
        rows = pageup.parse_listing(html, pageup.TENANTS["monash"].listing_url)
        self.assertEqual(rows[0]["id"], "684321")
        self.assertIn("Clayton", rows[0]["city"])

    def test_smartrecruiters_json(self):
        search_payload = {"content": [{
            "id": "744000099999999", "name": "Postdoctoral Research Fellow",
            "location": {"city": "Sydney", "country": "Australia"},
            "company": {"name": "Western Sydney University"}, "releasedDate": "2026-09-01T00:00:00Z",
            "refNumber": "REF123"
        }]}
        rows = smartrecruiters.parse_search_payload(search_payload)
        self.assertEqual(rows[0]["id"], "744000099999999")
        detail = smartrecruiters.parse_detail_payload({
            "name": "Postdoctoral Research Fellow",
            "company": {"name": "Western Sydney University"},
            "location": {"city": "Sydney", "country": "Australia"},
            "jobAd": {"sections": {
                "jobDescription": {"text": "<p>Research description</p>"},
                "qualifications": {"text": "<p>PhD required</p>"}
            }}
        })
        self.assertIn("PhD required", detail["description"])

    def test_successfactors_parser(self):
        html = '''<div><a href="/job/Brussels-Postdoctoral-Researcher-1050/123456789/">Postdoctoral Researcher</a></div>'''
        rows = successfactors.parse_listing(html, "https://jobs.vub.be/go/EN_ALL-JOBS/3775601/")
        self.assertEqual(rows[0]["id"], "123456789")

    def test_workday_json(self):
        payload = {"jobPostings": [{
            "title": "Postdoctoral Research Fellow",
            "externalPath": "/job/St-Lucia/Postdoctoral-Research-Fellow_R-68195",
            "locationsText": "St Lucia Campus", "postedOn": "Posted 2 Days Ago",
            "bulletFields": ["Full-time", "Research"]
        }]}
        rows = workday.parse_search_payload(payload)
        self.assertEqual(rows[0]["id"], "R-68195")
        self.assertTrue(rows[0]["external_path"].startswith("/job/"))
        detail = workday.parse_detail_payload({"jobPostingInfo": {
            "title": "Postdoctoral Research Fellow", "jobReqId": "R-68195",
            "jobDescription": "<p>Exercise neuroscience research.</p>" * 20,
            "location": "St Lucia Campus", "timeType": "Full time"
        }})
        self.assertEqual(detail["job_req_id"], "R-68195")
        self.assertGreater(len(detail["description"]), 100)

    def test_malformed_payloads_fail_soft_at_parser_boundary(self):
        self.assertEqual(smartrecruiters.parse_search_payload({"content": [None, {}, "bad"]}), [])
        self.assertEqual(workday.parse_search_payload({"jobPostings": [None, {}, "bad"]}), [])
        self.assertEqual(successfactors.parse_listing("<html></html>", "https://jobs.example.org"), [])
        self.assertEqual(university_vacancies.parse_search_payload({"data": {"jobPosts": [None, {}, "bad"]}}), [])


if __name__ == "__main__":
    unittest.main()
