import unittest

from scripts.verify_collector_coverage_reconciliation import verify


class CollectorCoverageReconciliationTest(unittest.TestCase):
    def test_collector_coverage_reconciliation_integrity(self) -> None:
        verify()


if __name__ == "__main__":
    unittest.main()
