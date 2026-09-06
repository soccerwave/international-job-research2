import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.sources.shared import common


REF = datetime(2026, 9, 6, 16, 0, tzinfo=timezone.utc)


class DateNormalizationStage410Tests(unittest.TestCase):
    def test_existing_european_formats_remain_supported(self):
        expected = "2026-09-14T00:00:00+00:00"
        for raw in ("14/09/2026", "14.09.2026", "14-09-2026", "14 September 2026", "14 Sep 2026"):
            with self.subTest(raw=raw):
                self.assertEqual(common.day_iso(raw, reference=REF), expected)

    def test_iso_timestamp_with_z_is_normalized(self):
        self.assertEqual(
            common.day_iso("2026-08-17T13:42:11Z", reference=REF),
            "2026-08-17T00:00:00+00:00",
        )

    def test_iso_timestamp_preserves_source_calendar_day_across_offset(self):
        self.assertEqual(
            common.day_iso("2026-09-01T00:30:00+02:00", reference=REF),
            "2026-09-01T00:00:00+00:00",
        )

    def test_month_first_named_format_is_unambiguous_and_supported(self):
        self.assertEqual(
            common.day_iso("August 17, 2026", reference=REF),
            "2026-08-17T00:00:00+00:00",
        )

    def test_ordinal_suffix_and_label_are_removed(self):
        self.assertEqual(
            common.day_iso("Closing date: 14th September 2026", reference=REF),
            "2026-09-14T00:00:00+00:00",
        )

    def test_workday_today_and_yesterday_are_reference_based(self):
        self.assertEqual(common.day_iso("Posted Today", reference=REF), "2026-09-06T00:00:00+00:00")
        self.assertEqual(common.day_iso("Posted Yesterday", reference=REF), "2026-09-05T00:00:00+00:00")

    def test_workday_days_ago_is_reference_based(self):
        self.assertEqual(common.day_iso("Posted 5 Days Ago", reference=REF), "2026-09-01T00:00:00+00:00")
        self.assertEqual(common.day_iso("30+ Days Ago", reference=REF), "2026-08-07T00:00:00+00:00")

    def test_ambiguous_us_numeric_date_is_not_guessed(self):
        # Repository scope is day-first for slash-separated numeric source dates.
        self.assertEqual(common.day_iso("09/06/2026", reference=REF), "2026-06-09T00:00:00+00:00")

    def test_unknown_date_text_remains_none(self):
        self.assertIsNone(common.day_iso("rolling applications", reference=REF))
        self.assertIsNone(common.day_iso("not specified", reference=REF))

    def test_make_record_uses_one_collection_reference_for_relative_dates(self):
        with patch("src.sources.shared.common.utc_now_iso", return_value="2026-09-06T16:00:00+00:00"):
            rec = common.make_record(
                source_key="workday_usyd",
                source_kind="ATS",
                provider="University of Sydney",
                source_job_id="1",
                listing_url="https://example.org/jobs",
                detail_url="https://example.org/job/1",
                title="Research Fellow",
                posted_text="Posted 2 Days Ago",
                deadline_text="14 September 2026",
            )
        self.assertEqual(rec["dates"]["posted_at"], "2026-09-04T00:00:00+00:00")
        self.assertEqual(rec["dates"]["deadline_at"], "2026-09-14T00:00:00+00:00")
        self.assertEqual(rec["dates"]["collected_at"], "2026-09-06T16:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
