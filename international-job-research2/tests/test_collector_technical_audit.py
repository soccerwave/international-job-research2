import unittest

from scripts.verify_collector_technical_audit import verify


class CollectorTechnicalAuditTest(unittest.TestCase):
    def test_collector_technical_audit_integrity(self) -> None:
        verify()


if __name__ == "__main__":
    unittest.main()
