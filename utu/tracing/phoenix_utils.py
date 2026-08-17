import os
from typing import TYPE_CHECKING

from phoenix.client import Client
from phoenix.client.types.spans import SpanQuery

if TYPE_CHECKING:
    import pandas as pd


class PhoenixUtils:
    # https://github.com/Arize-ai/phoenix/tree/main/packages/phoenix-client
    def __init__(self, base_url: str = None, project_name: str = None):
        self.base_url = base_url or os.getenv("PHOENIX_BASE_URL")
        self.project_name = project_name or os.getenv("PHOENIX_PROJECT_NAME")
        print(f"Using Phoenix base url: {self.base_url} with project name: {self.project_name}")
        self.client = Client(base_url=self.base_url)
        self.project_info = self.get_project()
        print(f"Project info: {self.project_info}")

    def get_spans(
        self, condition: str, select: list[str] = None, limit: int = 10, root_spans_only: bool = True
    ) -> "pd.DataFrame":
        if not select:
            query = SpanQuery().where(condition)
        else:
            query = SpanQuery().where(condition).select(*select)
        return self.client.spans.get_spans_dataframe(
            project_name=self.project_name,
            query=query,
            limit=limit,
            root_spans_only=root_spans_only,
            timeout=30,  # slow?
        )

    def get_project(self) -> dict:
        return self.client.projects.get(project_name=self.project_name)

    def get_trace_url_by_id(self, trace_id: str) -> str | None:
        # Escape single quotes to prevent injection into the filter expression.
        safe_trace_id = trace_id.replace("'", "''")
        spans_df = self.get_spans(
            condition=f"metadata['trace_id'] == '{safe_trace_id}'", select=["context.trace_id"], limit=1
        )
        if spans_df.empty:
            return None
        trace_id = spans_df.iloc[0]["context.trace_id"]
        return f"{self.base_url}/projects/{self.project_info['id']}/spans/{trace_id}"
