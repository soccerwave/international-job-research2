import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from src.sources.shared import academicpositions, dvs, ecss, euraxess, fens, jobs_ac_uk, linkedin_mads
from src.sources.shared.common import infer_country_code, make_record

ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/"schemas"/"vacancy.schema.json").read_text(encoding="utf-8"))
VALIDATOR=Draft202012Validator(SCHEMA)

class SharedSourceParserTests(unittest.TestCase):
    def assert_schema(self, record):
        errors=list(VALIDATOR.iter_errors(record))
        self.assertFalse(errors, "\n".join(e.message for e in errors))

    def test_common_record_schema(self):
        record=make_record(source_key="x",source_kind="THEMATIC_PORTAL",provider="X",source_job_id="123",
            listing_url="https://example.org/jobs",detail_url="https://example.org/job/123",title="Postdoctoral Researcher",
            country_code="DE",country_name="Germany",full_jd="A "*200,detail_status="FULL")
        self.assert_schema(record)
        self.assertEqual(record["classification"]["market_tier"],"CORE")
        self.assertEqual(infer_country_code("Hong Kong"),"HK")

    def test_euraxess_current_facets_and_cards(self):
        html='<select name="job_country[]"><option value="791">Austria</option><option value="794">Germany</option></select><article><a href="/jobs/12345">Postdoctoral Researcher in Exercise</a><div>University X Germany Posted on: 4 September 2026</div></article>'
        self.assertEqual(euraxess.discover_country_facets(html)["germany"],"job_country:794")
        rows=euraxess.parse_listing(html)
        self.assertEqual(rows[0]["id"],"12345")

    def test_euraxess_legacy_facet_compatibility(self):
        html='<select><option value="job_country:111">Germany</option></select>'
        self.assertEqual(euraxess.discover_country_facets(html)["germany"],"job_country:111")

    def test_euraxess_generic_detail_heading_does_not_replace_listing_title(self):
        parsed=euraxess.parse_detail_metadata('<main><h1>Job offer</h1><p>Organisation: University X</p></main>')
        self.assertEqual(parsed["title"],"")

    def test_academicpositions_jsonld(self):
        desc="Research exercise neuroscience. "*30
        html='<html><script type="application/ld+json">'+json.dumps({"@type":"JobPosting","title":"Postdoc in Brain Health","datePosted":"2026-09-01","validThrough":"2026-10-01","hiringOrganization":{"name":"Uni X"},"jobLocation":{"address":{"addressLocality":"Berlin","addressCountry":"Germany"}},"description":desc})+'</script></html>'
        parsed=academicpositions.parse_detail(html)
        self.assertEqual(parsed["institution"],"Uni X")
        self.assertEqual(parsed["country"],"Germany")
        self.assertGreater(len(parsed["description"]),200)

    def test_jobs_ac_uk_search_parser(self):
        html='<div class="job"><a href="/job/ABC123/postdoctoral-research-fellow/">Postdoctoral Research Fellow</a><p>University X Location: London</p></div>'
        rows=jobs_ac_uk.parse_search(html)
        self.assertEqual(rows[0]["id"],"ABC123")

    def test_ecss_table_parser(self):
        html='<table><tr><th>Announcing date</th><th>Application deadline</th><th>Vacancy</th><th>Institution</th><th>Country</th><th>Details</th></tr><tr><td>23.07.2026</td><td>18.08.2026</td><td>[Po] Assistant Professor in Exercise</td><td>Uni X</td><td>Germany</td><td><a href="https://ecss.mobi/DATA/JOBS/2474.pdf">Download</a></td></tr></table>'
        rows=ecss.parse_listing(html)
        self.assertEqual(rows[0]["id"],"2474")
        self.assertEqual(rows[0]["country"],"Germany")

    def test_dvs_parser(self):
        html='<div class="vacancy"><strong>Universität Jena</strong><br/>Wissenschaftliche:r Mitarbeiter:in Sportpsychologie<br/><a href="https://jobs.uni-jena.de/1234.pdf">mehr...PDF</a><br/>Bewerbungsschluss: 18.09.2026</div>'
        rows=dvs.parse_listing(html)
        self.assertEqual(rows[0]["institution"],"Universität Jena")
        self.assertIn("Sportpsychologie",rows[0]["title"])
        self.assertEqual(dvs.infer_dvs_country(rows[0]["institution"],rows[0]["url"]),"DE")
        self.assertEqual(dvs.infer_dvs_country("Universität Wien","https://jobs.univie.ac.at/1"),"AT")
        self.assertIsNone(dvs.infer_dvs_country("Unknown University","https://example.org/job"))

    def test_fens_listing_and_detail(self):
        listing='<table><tr><td><a href="/careers/job-market/job/123456">Postdoctoral Position in Stress Neuroscience</a></td><td>Post-doctoral Position</td></tr></table>'
        rows=fens.parse_listing(listing)
        self.assertEqual(rows[0]["id"],"123456")
        detail='<main><h1>Postdoctoral Position in Stress Neuroscience</h1><p>Position: Post-doctoral Position</p><p>Deadline: 30 September 2026</p><p>City: Berlin</p><p>Country: Germany</p><p>Institution: Uni X</p><p>Department: Neuroscience</p><p>Description: '+("stress brain exercise "*30)+'</p></main>'
        parsed=fens.parse_detail(detail)
        self.assertEqual(parsed["country"],"Germany")
        self.assertEqual(parsed["department"],"Neuroscience")

    def test_fens_empty_department_stays_empty(self):
        html='<main><h1>PhD students</h1><p>Position: Ph.D. Student</p><p>Deadline: 15 November 2026</p><p>City: Hong Kong</p><p>Country: Hong Kong</p><p>Institution: CUHK</p><p>Department:</p><p>Description: neuroscience project</p></main>'
        parsed=fens.parse_detail(html)
        self.assertEqual(parsed["country"],"Hong Kong")
        self.assertEqual(parsed["department"],"")

    def test_linkedin_fake_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo=Path(tmp); cli=repo/linkedin_mads.CLI_RELATIVE; cli.parent.mkdir(parents=True); cli.write_text("//stub")
            def runner(_repo,args):
                if "search" in args:
                    payload={"results":[{"id":"444","title":"Postdoctoral Researcher","company":"Uni X","location":"Berlin, Germany","date":"2026-09-04","url":"https://www.linkedin.com/jobs/view/444"}]}
                    return subprocess.CompletedProcess(args,0,json.dumps(payload),"")
                return subprocess.CompletedProcess(args,0,"Full description "+("exercise neuroscience "*30),"")
            rows=linkedin_mads.collect(locations=("Germany",),queries=("postdoctoral researcher",),limit_per_search=1,max_jobs=1,repo_path=repo,runner=runner)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["location"]["country_code"],"DE")
            self.assert_schema(rows[0])

if __name__=="__main__":
    unittest.main()
