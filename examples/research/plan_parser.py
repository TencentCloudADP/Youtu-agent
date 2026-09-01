import json
import re
from typing import Any

from pydantic import BaseModel


class WebSearchItem(BaseModel):
    reason: str
    "Your reasoning for why this search is important to the query."

    query: str
    "The search term to use for the web search."


class WebSearchPlan(BaseModel):
    searches: list[WebSearchItem]
    """A list of web searches to perform to best answer the query."""


class ReportData(BaseModel):
    short_summary: str
    """A short 2-3 sentence summary of the findings."""

    markdown_report: str
    """The final report."""

    follow_up_questions: list[str]
    """Suggested topics to research further."""


def _plan_from_data(data: Any) -> WebSearchPlan | None:
    """Normalize common JSON plan shapes emitted by different model providers."""
    searches = data.get("searches") if isinstance(data, dict) else data
    if not isinstance(searches, list):
        return None

    normalized: list[WebSearchItem] = []
    for item in searches[:20]:
        if isinstance(item, str):
            query = item.strip()
            reason = f"Find information relevant to {query}"
        elif isinstance(item, dict):
            query = str(item.get("query", "")).strip()
            reason = str(item.get("reason", "")).strip() or f"Find information relevant to {query}"
        else:
            continue

        if query:
            normalized.append(WebSearchItem(query=query, reason=reason))

    return WebSearchPlan(searches=normalized) if normalized else None


def parse_search_plan(output: str) -> WebSearchPlan:
    """Parse JSON or a markdown/numbered search list into a validated plan."""
    text = output.strip()
    json_candidates = [text]
    json_candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE))

    for candidate in json_candidates:
        try:
            plan = _plan_from_data(json.loads(candidate.strip()))
        except (json.JSONDecodeError, TypeError):
            continue
        if plan:
            return plan

    queries: list[str] = []
    for match in re.finditer(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$", text, flags=re.MULTILINE):
        query = match.group(1).strip().strip("`\"'“”‘’")
        if query and query not in queries:
            queries.append(query)

    plan = _plan_from_data(queries)
    if plan:
        return plan
    raise ValueError("The planner response did not contain a JSON plan or a numbered search list")


def parse_report_data(output: str) -> ReportData:
    """Parse a structured report, falling back to a provider's markdown output."""
    text = output.strip()
    json_candidates = [text]
    json_candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE))
    for candidate in json_candidates:
        try:
            return ReportData.model_validate(json.loads(candidate.strip()))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue

    if not text:
        raise ValueError("The writer response was empty")

    follow_up_questions: list[str] = []
    follow_up_heading = re.search(
        r"^#{1,6}\s*(?:follow[- ]?up questions|后续问题|延伸问题)\s*$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    markdown_report = text
    if follow_up_heading:
        markdown_report = text[: follow_up_heading.start()].rstrip()
        follow_up_section = text[follow_up_heading.end() :]
        follow_up_questions = [
            match.group(1).strip()
            for match in re.finditer(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$", follow_up_section, flags=re.MULTILINE)
        ]

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", markdown_report)
        if paragraph.strip() and not paragraph.lstrip().startswith("#")
    ]
    summary = paragraphs[0] if paragraphs else markdown_report
    return ReportData(
        short_summary=summary[:500],
        markdown_report=markdown_report,
        follow_up_questions=follow_up_questions,
    )
