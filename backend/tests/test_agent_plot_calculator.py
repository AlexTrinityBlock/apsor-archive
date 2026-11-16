"""Inline chart and calculator tool behavior through the public agent API.

These tests drive a real conversation turn through ``TestClient`` with the
deterministic provider fake. They prove four things the UI depends on: the
calculator returns exact numbers, a rejected expression never fails the stream,
the complete plot figure is persisted for reload while the provider context only
ever sees a redacted summary, and the frozen catalog exposes both tools.
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.module.agent.domain.plot_spec_domain import PlotSpecError, sanitize_plot_figure
from app.module.agent.test.fake_chat_generator import (
    FakeChatGenerator,
    text_result,
    tool_call_result,
    tool_calls_result,
)

CALCULATOR_EXPRESSION = "((12.5 * 4) + 7) / 3"
PLOT_TITLE = "Memories per month"
PLOT_CAPTION = "Counts from the archive timeline."
PLOT_FIGURE: dict[str, Any] = {
    "data": [
        {
            "type": "bar",
            "name": "Memories",
            "x": ["Jan", "Feb"],
            "y": [3, 5],
        }
    ],
    "layout": {
        "xaxis": {"title": {"text": "Month"}},
        "yaxis": {"title": {"text": "Memories"}},
    },
}
PLOT_ARGUMENTS_SUMMARY = {
    "title": PLOT_TITLE,
    "caption": PLOT_CAPTION,
    "figure_summary": {"traces": 1},
}


def _create_conversation(client: TestClient, title: str) -> int:
    """Create one conversation and return its id."""
    created = client.post("/api/v1/agent/conversations", json={"title": title})
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


def _send_message(client: TestClient, conversation_id: int, content: str) -> dict[str, Any]:
    """Run one turn with the JSON transport and return the completed turn body."""
    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": content},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run"]["status"] == "completed"
    assert body["error_code"] is None
    return body


def _tool_results(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the turn's tool-result entries in append order."""
    return [entry for entry in entries if entry["kind"] == "pi.tool-result"]


def _assistant_tool_call_entry(
    entries: list[dict[str, Any]],
    tool_name: str,
) -> dict[str, Any]:
    """Return the assistant entry that requested ``tool_name``."""
    for entry in entries:
        if entry["kind"] != "pi.assistant" or not entry["model"]:
            continue
        for tool_call in entry["model"][0].get("tool_calls") or []:
            if tool_call["function"]["name"] == tool_name:
                return entry
    raise AssertionError(f"No assistant tool call for {tool_name!r}.")


def _reload_entries(client: TestClient, conversation_id: int) -> list[dict[str, Any]]:
    """Read the full entry page back from the database."""
    response = client.get(
        f"/api/v1/agent/conversations/{conversation_id}/entries",
        params={"limit": 50},
    )
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_calculator_tool_evaluates_and_persists_result(client: TestClient) -> None:
    """Run a calculate call and verify the exact result survives a reload."""
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "calculate",
                {"expression": CALCULATOR_EXPRESSION},
                call_id="call_calc_1",
            ),
            text_result("The calculator returned 19."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Calculator")

    body = _send_message(client, conversation_id, "What is ((12.5 * 4) + 7) / 3?")

    assert body["answer"] == "The calculator returned 19."
    results = _tool_results(body["entries"])
    assert len(results) == 1
    result_entry = results[0]
    data = result_entry["data"]
    assert data["tool"] == "calculate"
    assert data["status"] == "ok"
    assert data["error_code"] is None
    assert data["expression"] == CALCULATOR_EXPRESSION
    assert data["result"] == 19
    assert data["formatted"] == "19"
    assert data["truncated"] is False

    tool_message = result_entry["model"][0]
    assert tool_message["role"] == "tool"
    assert tool_message["name"] == "calculate"
    assert tool_message["tool_call_id"] == "call_calc_1"
    calculation_xml = f'<calculation expression="{CALCULATOR_EXPRESSION}" result="19"/>'
    assert calculation_xml in tool_message["content"]

    assistant_entry = _assistant_tool_call_entry(body["entries"], "calculate")
    arguments = json.loads(assistant_entry["model"][0]["tool_calls"][0]["function"]["arguments"])
    assert arguments == {"expression": CALCULATOR_EXPRESSION}

    reloaded_results = _tool_results(_reload_entries(client, conversation_id))
    assert reloaded_results == [result_entry]


def test_calculator_rejects_unsafe_expression(client: TestClient) -> None:
    """Reject imports, builtins, giant powers, and division by zero as tool errors."""
    unsafe_expressions = [
        ("__import__('os').system('id')", "call_calc_import"),
        ("open('secret.txt')", "call_calc_open"),
        ("9**9**9", "call_calc_power"),
        ("1/0", "call_calc_zero"),
    ]
    fake = FakeChatGenerator(
        [
            tool_calls_result(
                [
                    ("calculate", {"expression": expression})
                    for expression, _call_id in unsafe_expressions
                ],
                call_ids=[call_id for _expression, call_id in unsafe_expressions],
            ),
            text_result("The calculator rejected every expression."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Unsafe calculations")

    body = _send_message(client, conversation_id, "Evaluate these expressions.")

    # The turn survives four tool failures: the model keeps its step and answers.
    assert body["answer"] == "The calculator rejected every expression."
    assert body["error_code"] is None
    assert len(fake.requests) == 2

    results = _tool_results(body["entries"])
    assert [entry["model"][0]["tool_call_id"] for entry in results] == [
        call_id for _expression, call_id in unsafe_expressions
    ]
    for result_entry in results:
        data = result_entry["data"]
        assert data["tool"] == "calculate"
        assert data["status"] == "error"
        assert data["error_code"] == "calculation_error"
        assert '<error code="calculation_error">' in result_entry["model"][0]["content"]

    reloaded_results = _tool_results(_reload_entries(client, conversation_id))
    assert [entry["data"]["error_code"] for entry in reloaded_results] == [
        "calculation_error"
    ] * len(unsafe_expressions)


def test_render_plot_persists_figure_and_redacts_provider_context(
    client: TestClient,
) -> None:
    """Keep the full figure in UI data and only a summary in provider messages."""
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "render_plot",
                {
                    "title": PLOT_TITLE,
                    "caption": PLOT_CAPTION,
                    "figure": PLOT_FIGURE,
                },
                call_id="call_plot_1",
            ),
            text_result("The chart shows more memories in the second month."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Plot")

    body = _send_message(client, conversation_id, "Chart the monthly memory counts.")

    results = _tool_results(body["entries"])
    assert len(results) == 1
    result_entry = results[0]
    data = result_entry["data"]
    assert data["tool"] == "render_plot"
    assert data["status"] == "ok"
    assert data["truncated"] is False
    plot = data["plot"]
    assert plot["version"] == 1
    assert plot["format"] == "plotly"
    assert plot["title"] == PLOT_TITLE
    assert plot["caption"] == PLOT_CAPTION
    # The sanitizer deep-copies, so the persisted figure is JSON-equal to input.
    assert plot["figure"] == PLOT_FIGURE
    assert plot["stats"]["trace_count"] == 1
    assert plot["stats"]["point_count"] == 2
    assert plot["stats"]["byte_size"] > 0
    assert data["arguments"] == PLOT_ARGUMENTS_SUMMARY

    # The persisted assistant call arguments are the redacted summary, not the
    # figure that the model originally supplied.
    assistant_entry = _assistant_tool_call_entry(body["entries"], "render_plot")
    raw_arguments = assistant_entry["model"][0]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(raw_arguments) == PLOT_ARGUMENTS_SUMMARY
    assert "Jan" not in raw_arguments
    assert "figure" not in json.loads(raw_arguments)

    # The provider's second request replays the persisted assistant message and
    # the tool envelope. Neither may carry the figure or its data arrays.
    assert len(fake.requests) == 2
    second_messages = fake.requests[1].messages
    provider_payload = json.dumps(second_messages, ensure_ascii=False)
    assert "Jan" not in provider_payload
    assert "[3,5]" not in provider_payload
    replayed_assistant = [
        message for message in second_messages if message.get("role") == "assistant"
    ]
    assert len(replayed_assistant) == 1
    replayed_call = replayed_assistant[0]["tool_calls"][0]
    assert replayed_call["function"]["name"] == "render_plot"
    assert json.loads(replayed_call["function"]["arguments"]) == PLOT_ARGUMENTS_SUMMARY
    replayed_tool_results = [
        message for message in second_messages if message.get("role") == "tool"
    ]
    assert len(replayed_tool_results) == 1
    assert replayed_tool_results[0]["content"] == result_entry["model"][0]["content"]
    assert "Jan" not in replayed_tool_results[0]["content"]
    assert "figure" not in replayed_tool_results[0]["content"]

    reloaded_results = _tool_results(_reload_entries(client, conversation_id))
    assert len(reloaded_results) == 1
    assert reloaded_results[0]["data"] == data
    assert reloaded_results[0]["data"]["plot"]["figure"] == PLOT_FIGURE


def test_render_plot_rejects_unsafe_or_oversized_figure(client: TestClient) -> None:
    """Reject external content, map traces, script URLs, and oversized figures."""
    thirteen_traces = [{"type": "bar", "x": ["a"], "y": [1]} for _ in range(13)]
    unsafe_calls = [
        (
            "call_plot_images",
            {
                "title": "Images",
                "figure": {
                    "data": [{"type": "bar", "x": ["a"], "y": [1]}],
                    "layout": {"images": [{"source": "https://example.com/a.png"}]},
                },
            },
        ),
        (
            "call_plot_mapbox",
            {
                "title": "Map",
                "figure": {"data": [{"type": "scattermapbox", "lat": [1], "lon": [2]}]},
            },
        ),
        (
            "call_plot_script",
            {
                "title": "Script",
                "figure": {
                    "data": [
                        {
                            "type": "bar",
                            "x": ["a"],
                            "y": [1],
                            "text": ["javascript:alert(1)"],
                        }
                    ]
                },
            },
        ),
        (
            "call_plot_points",
            {
                "title": "Too many points",
                "figure": {"data": [{"type": "scatter", "y": list(range(20_001))}]},
            },
        ),
        (
            "call_plot_traces",
            {"title": "Too many traces", "figure": {"data": thirteen_traces}},
        ),
    ]
    fake = FakeChatGenerator(
        [
            tool_calls_result(
                [("render_plot", arguments) for _call_id, arguments in unsafe_calls],
                call_ids=[call_id for call_id, _arguments in unsafe_calls],
            ),
            text_result("Those figures could not be rendered."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Unsafe plots")

    body = _send_message(client, conversation_id, "Render these figures.")

    assert body["answer"] == "Those figures could not be rendered."
    results = _tool_results(body["entries"])
    assert [entry["model"][0]["tool_call_id"] for entry in results] == [
        call_id for call_id, _arguments in unsafe_calls
    ]
    codes = [entry["data"]["error_code"] for entry in results]
    # layout.images, scattermapbox, javascript:, and the point cap are rejected by
    # the sanitizer. A 13-trace payload is already rejected by the argument
    # schema (maxItems=12), so the tool boundary reports invalid_tool_arguments;
    # the sanitizer's own trace cap is asserted directly below.
    assert codes == [
        "plot_spec_error",
        "plot_spec_error",
        "plot_spec_error",
        "plot_spec_error",
        "invalid_tool_arguments",
    ]
    for result_entry, code in zip(results, codes, strict=True):
        assert result_entry["data"]["status"] == "error"
        assert f'<error code="{code}">' in result_entry["model"][0]["content"]

    with pytest.raises(PlotSpecError):
        sanitize_plot_figure({"data": thirteen_traces})


def test_plot_and_calculation_tools_are_in_catalog(client: TestClient) -> None:
    """Expose both tools with flat, model-facing schemas and guidance."""
    response = client.get("/api/v1/agent/tools")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert catalog["prompt_version"] == "archive-agent-v13"
    assert catalog["tools_version"] == "archive-tools-v9"

    tools = {tool["name"]: tool for tool in catalog["tools"]}
    names = [tool["name"] for tool in catalog["tools"]]
    present_index = names.index("present_resource")
    assert names[present_index + 1 : present_index + 3] == ["calculate", "render_plot"]
    assert names[present_index + 3] == "web_search"

    calculate = tools["calculate"]
    assert calculate["requires_confirmation"] is False
    assert calculate["parameters"]["required"] == ["expression"]
    expression_schema = calculate["parameters"]["properties"]["expression"]
    assert expression_schema["minLength"] == 1
    assert expression_schema["maxLength"] == 300
    assert "Use this tool for every arithmetic step" in calculate["description"]

    render_plot = tools["render_plot"]
    assert render_plot["requires_confirmation"] is False
    assert render_plot["parameters"]["required"] == ["title", "figure"]
    figure_schema = render_plot["parameters"]["properties"]["figure"]
    assert figure_schema["properties"]["data"]["minItems"] == 1
    assert figure_schema["properties"]["data"]["maxItems"] == 12
    description = render_plot["description"]
    assert "Render a Plotly chart inline in the chat" in description
    assert "explain the chart" in description

    serialized = json.dumps(render_plot["parameters"])
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_plot_tool_result_content_is_small(client: TestClient) -> None:
    """Keep the provider-facing plot result a short XML confirmation."""
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "render_plot",
                {
                    "title": PLOT_TITLE,
                    "caption": PLOT_CAPTION,
                    "figure": PLOT_FIGURE,
                },
                call_id="call_plot_small",
            ),
            text_result("The chart is ready."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Small plot result")

    body = _send_message(client, conversation_id, "Draw the monthly counts.")

    results = _tool_results(body["entries"])
    assert len(results) == 1
    result_entry = results[0]
    assert result_entry["data"]["truncated"] is False
    content = result_entry["model"][0]["content"]
    assert content.startswith('<tool_result name="render_plot" call_id="call_plot_small">')
    assert "<plot_rendered" in content
    assert f'title="{PLOT_TITLE}"' in content
    assert 'traces="1"' in content
    assert 'points="2"' in content
    assert "Jan" not in content
    assert "figure" not in content
    assert '"data"' not in content
    assert len(content) < 400
