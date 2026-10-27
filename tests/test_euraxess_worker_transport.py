import os
import unittest
from unittest.mock import patch
from src.sources.shared.euraxess_worker_transport import EuraxessWorkerSession, configured_session


class WorkerSessionTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"EURAXESS_WORKER_URL":"","EURAXESS_WORKER_TOKEN":""}):
            self.assertIsNone(configured_session())

    def test_partial_configuration_fails_closed(self):
        with patch.dict(os.environ, {"EURAXESS_WORKER_URL":"https://worker.example","EURAXESS_WORKER_TOKEN":""}):
            with self.assertRaises(ValueError):
                configured_session()

    def test_rejects_off_domain_and_unapproved_paths(self):
        s=EuraxessWorkerSession("https://worker.example","test-only")
        for url in ("https://evil.example/jobs/search","http://euraxess.ec.europa.eu/jobs/search",
                    "https://euraxess.ec.europa.eu/admin"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                s.get(url)

    def test_preserves_parameters_and_upstream_final_url(self):
        from requests import Response
        response=Response()
        response.status_code=200
        response._content=b"<html>good</html>"
        response.headers["x-euraxess-final-url"]="https://euraxess.ec.europa.eu/jobs/search?f%5B0%5D=job_country%3A794"
        s=EuraxessWorkerSession("https://worker.example","test-only")
        with patch.object(s.transport,"post",return_value=response) as request:
            result=s.get("https://euraxess.ec.europa.eu/jobs/search",
                params=[("f[0]","job_country:794")],timeout=(10,45))
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.url,response.headers["x-euraxess-final-url"])
        payload=request.call_args.kwargs["json"]
        self.assertIn("job_country%3A794",payload["query"])
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"],"Bearer test-only")

if __name__ == "__main__":
    unittest.main()
