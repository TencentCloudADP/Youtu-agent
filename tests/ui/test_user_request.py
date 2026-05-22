import os

os.environ.setdefault("UTU_LLM_TYPE", "openai")
os.environ.setdefault("UTU_LLM_MODEL", "test-model")

from utu.ui.common import UserQuery, UserRequest


def test_user_request_accepts_nested_query_content():
    request = UserRequest(type="query", content={"query": "hello"})

    assert isinstance(request.content, UserQuery)
    assert request.content.query == "hello"


def test_user_request_accepts_legacy_top_level_query():
    request = UserRequest(type="query", query="hello")

    assert isinstance(request.content, UserQuery)
    assert request.content.query == "hello"
