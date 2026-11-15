import unittest
from scripts.audit_euraxess_historical_overlap import run, classify, make_index

def entry(source,ident,title,org="Example University",country="NL",date="2026-10-01",rec="REVIEW",url=None):
    aliases=["source_id:"+source+":"+ident]
    if url: aliases.append("url:"+url)
    return {"aliases":aliases,"first_seen_at":date,"last_seen_at":date,"last_snapshot":{
        "title":title,"institution":org,"country_code":country,"recommendation":rec}}

class HistoricalOverlapTests(unittest.TestCase):
    def test_exact_title_institution_country_is_candidate_not_verified(self):
        jobs={"e":entry("euraxess","100","Postdoctoral Exercise Neuroscience",rec="APPLY"),
              "o":entry("academictransfer","200","Postdoctoral Exercise Neuroscience")}
        result=run({"generation":1,"jobs":jobs})
        self.assertEqual(result["status_counts"],{"TITLE_ORG_COUNTRY_STRONG_CANDIDATE":1})
        self.assertEqual(result["high_priority_euraxess_records"][0]["match_status"],"TITLE_ORG_COUNTRY_STRONG_CANDIDATE")
    def test_same_title_different_institution_is_weak(self):
        jobs={"e":entry("euraxess","100","Postdoctoral Fellow"),
              "o":entry("academictransfer","200","Postdoctoral Fellow","Other University")}
        self.assertEqual(run({"jobs":jobs})["status_counts"],{"TITLE_COUNTRY_WEAK_CANDIDATE":1})
    def test_distant_first_seen_is_not_strong(self):
        jobs={"e":entry("euraxess","100","Postdoctoral Fellow",date="2026-10-01"),
              "o":entry("academictransfer","200","Postdoctoral Fellow",date="2026-02-01")}
        self.assertEqual(run({"jobs":jobs})["status_counts"],{"TITLE_ORG_COUNTRY_DIFFERENT_PERIOD":1})
    def test_unmatched_and_source_recommendation(self):
        jobs={"e":entry("euraxess","100","Postdoc Cognitive Stress",rec="STRONG_APPLY")}
        result=run({"jobs":jobs})
        self.assertEqual(result["status_counts"],{"NO_CANDIDATE_IN_STATE":1})
        self.assertEqual(result["stored_recommendation_counts"],{"STRONG_APPLY":1})

if __name__=="__main__":
    unittest.main()
