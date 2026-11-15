import unittest

from scripts.audit_euraxess_overlap_r2 import norm, state_indexes, reference_match


def row(title="Research Assistant Computational Neuroimaging (Animal MRI)"):
    return {"id":"480114","title":title,"country":"NL","org":"Radboud University Medical Center","date":"2026-11-13","cohort":"current_week","priority":"REVIEW","channel":"AcademicTransfer","url":"https://euraxess.ec.europa.eu/jobs/480114"}


class EuraxessOverlapTests(unittest.TestCase):
    def test_exact_euraxess_alias(self):
        state={"jobs":{"j1":{"aliases":["source_id:euraxess:480114"],"last_snapshot":{"title":"other","country_code":"NL"}}}}
        aliases,countries=state_indexes(state)
        result=reference_match(row(),aliases,countries)
        self.assertEqual(result["status"],"EXACT_EURAXESS_ID_IN_STATE")

    def test_alternative_title_is_not_automatically_confirmed(self):
        state={"jobs":{"j2":{"aliases":["source_id:academictransfer:365550"],"last_snapshot":{"title":"research assistant computational neuroimaging animal mri","country_code":"NL","institution":"Radboud University Medical Center"},"first_seen_at":"2026-11-13"}}}
        aliases,countries=state_indexes(state)
        result=reference_match(row(),aliases,countries)
        self.assertEqual(result["status"],"CROSS_SOURCE_POSSIBLE_REQUIRES_ADJUDICATION")
        self.assertEqual(result["cross_source_candidate_count"],1)

    def test_no_match_does_not_claim_confirmed_false_negative(self):
        aliases,countries=state_indexes({"jobs":{}})
        self.assertEqual(reference_match(row(),aliases,countries)["status"],"NOT_MATCHED_IN_CURRENT_R2_STATE")


if __name__=="__main__":
    unittest.main()
