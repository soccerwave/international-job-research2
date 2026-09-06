def good_collector():
    return [
        {
            "schema_version": "VACANCY_SCHEMA_V1.0.0",
            "source": {"source_id": "stub_source", "source_vacancy_id": "1", "source_url": "https://example.invalid/jobs/1"},
            "job": {"title": "Postdoctoral Researcher in Exercise Neuroscience"},
            "location": {"country_code": "NL", "country": "Netherlands"}
        }
    ]


def second_good_collector():
    return [
        {
            "schema_version": "VACANCY_SCHEMA_V1.0.0",
            "source": {"source_id": "stub_source_two", "source_vacancy_id": "2", "source_url": "https://example.invalid/jobs/2"},
            "job": {"title": "Research Fellow in Stress Biology"},
            "location": {"country_code": "GB", "country": "United Kingdom"}
        }
    ]


def failing_collector():
    raise RuntimeError("intentional Stage 4 fixture failure")
