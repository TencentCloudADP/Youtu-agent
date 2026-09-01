from __future__ import annotations

import asyncio
import pathlib

from agents import custom_span, gen_trace_id, trace
from rich.console import Console

from examples.research.plan_parser import (
    ReportData,
    WebSearchItem,
    WebSearchPlan,
    parse_report_data,
    parse_search_plan,
)
from examples.research.printer import Printer
from utu.agents import SimpleAgent
from utu.config import ConfigLoader
from utu.tools import SearchToolkit
from utu.utils import FileUtils

PROMPTS = FileUtils.load_yaml(pathlib.Path(__file__).parent / "prompts.yaml")


class ResearchManager:
    def __init__(self):
        self.console = Console()
        self.printer = Printer(self.console)

    async def build(self):
        self.planner_agent = SimpleAgent(
            name="PlannerAgent",
            instructions=PROMPTS["PLANNER_PROMPT"],
            # model="gpt-4o",
        )
        toolkit = SearchToolkit(ConfigLoader.load_toolkit_config("search"))
        self.search_agent = SimpleAgent(
            name="Search agent",
            instructions=PROMPTS["SEARCH_PROMPT"],
            tools=toolkit.get_tools_in_agents(),
        )
        self.writer_agent = SimpleAgent(
            name="WriterAgent",
            instructions=PROMPTS["WRITER_PROMPT"],
            # model="o3-mini",
        )

    async def run(self, query: str) -> None:
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            # self.printer.update_item(
            #     "trace_id",
            #     f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}",
            #     is_done=True,
            #     hide_checkmark=True,
            # )

            self.printer.update_item(
                "starting",
                "Starting research...",
                is_done=True,
                hide_checkmark=True,
            )
            search_plan = await self._plan_searches(query)
            search_results = await self._perform_searches(search_plan)
            report = await self._write_report(query, search_results)

            final_report = f"Report summary\n\n{report.short_summary}"
            self.printer.update_item("final_report", final_report, is_done=True)

            self.printer.end()

        print("\n\n=====REPORT=====\n\n")
        print(f"Report: {report.markdown_report}")
        print("\n\n=====FOLLOW UP QUESTIONS=====\n\n")
        follow_up_questions = "\n".join(report.follow_up_questions)
        print(f"Follow up questions: {follow_up_questions}")

    async def _plan_searches(self, query: str) -> WebSearchPlan:
        self.printer.update_item("planning", "Planning searches...")
        result = await self.planner_agent.run(
            f"Query: {query}",
        )
        search_plan = parse_search_plan(str(result.final_output))
        self.printer.update_item(
            "planning",
            f"Will perform {len(search_plan.searches)} searches",
            is_done=True,
        )
        return search_plan

    async def _perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        with custom_span("Search the web"):
            self.printer.update_item("searching", "Searching...")
            num_completed = 0
            tasks = [asyncio.create_task(self._search(item)) for item in search_plan.searches]
            results = []
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
                self.printer.update_item("searching", f"Searching... {num_completed}/{len(tasks)} completed")
            # results = await asyncio.gather(*tasks)
            self.printer.mark_item_done("searching")
            return results

    async def _search(self, item: WebSearchItem) -> str | None:
        input = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await self.search_agent.run(
                input,
            )
            return str(result.final_output)
        except Exception:  # pylint: disable=broad-except
            return None

    async def _write_report(self, query: str, search_results: list[str]) -> ReportData:
        self.printer.update_item("writing", "Thinking about report...")
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = await self.writer_agent.run(
            input,
        )
        self.printer.mark_item_done("writing")
        return parse_report_data(str(result.final_output))


async def main(query: str) -> None:
    research_manager = ResearchManager()
    await research_manager.build()
    await research_manager.run(query)


if __name__ == "__main__":
    query = input("What would you like to research? ")
    asyncio.run(main(query))
