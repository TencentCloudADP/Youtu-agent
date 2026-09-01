import pytest

from examples.research.plan_parser import parse_report_data, parse_search_plan


@pytest.mark.parametrize(
    ("output", "expected_queries"),
    [
        (
            '{"searches": [{"reason": "Find the release notes", "query": "Youtu-Agent releases"}]}',
            ["Youtu-Agent releases"],
        ),
        (
            """```json
            {"searches": ["agent evaluation metrics", "LLM judge reliability"]}
            ```""",
            ["agent evaluation metrics", "LLM judge reliability"],
        ),
        (
            '1. "马云出生日期"\n2. "Jack Ma birthday"\n- 马云个人资料',
            ["马云出生日期", "Jack Ma birthday", "马云个人资料"],
        ),
    ],
)
def test_parse_search_plan(output: str, expected_queries: list[str]):
    plan = parse_search_plan(output)

    assert [item.query for item in plan.searches] == expected_queries
    assert all(item.reason for item in plan.searches)


def test_parse_search_plan_rejects_unstructured_text():
    with pytest.raises(ValueError, match="did not contain"):
        parse_search_plan("I cannot create a search plan.")


def test_parse_report_data_from_json():
    report = parse_report_data(
        '{"short_summary": "Summary", "markdown_report": "# Report\\nDetails", '
        '"follow_up_questions": ["What comes next?"]}'
    )

    assert report.short_summary == "Summary"
    assert report.markdown_report == "# Report\nDetails"
    assert report.follow_up_questions == ["What comes next?"]


def test_parse_report_data_falls_back_to_markdown():
    report = parse_report_data(
        "# Research report\n\nThe evidence supports the conclusion.\n\n"
        "## Follow-up questions\n\n- What should be validated next?"
    )

    assert report.short_summary == "The evidence supports the conclusion."
    assert report.markdown_report == "# Research report\n\nThe evidence supports the conclusion."
    assert report.follow_up_questions == ["What should be validated next?"]
