"""Inline chart and calculator tool behavior through the public agent API.

These tests drive a real conversation turn through ``TestClient`` with the
deterministic provider fake. They prove four things the UI depends on: the
calculator returns exact numbers, a rejected expression never fails the stream,
the complete plot figure is persisted for reload while later runs drop the plot
call silently, and the frozen catalog exposes both tools.
"""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.module.agent.domain.agent_domain import (
    KIND_ASSISTANT,
    KIND_TOOL_RESULT,
    KIND_USER,
    TranscriptEntry,
)
from app.module.agent.domain.context_domain import PLOT_CONTEXT_MAX_BYTES, build_context
from app.module.agent.domain.plot_spec_domain import PlotSpecError, sanitize_plot_figure
from app.module.agent.protocol.chat_generator_protocol import ChatResult, ChatToolCall
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
PLOT_ARGUMENTS_DISPLAY = {
    "title": PLOT_TITLE,
    "caption": PLOT_CAPTION,
}


def _grid(rows: int, columns: int) -> list[list[int]]:
    """Build a rectangular row-major grid for surface and heatmap traces."""
    return [
        [row * columns + column for column in range(columns)]
        for row in range(rows)
    ]


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


def test_render_plot_persists_figure_and_hides_historical_calls(
    client: TestClient,
) -> None:
    """Keep the real call in the run and drop it silently in later runs."""
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
            text_result("The chart stays available above."),
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
    # Tool-result and tool_start payloads carry the display form only.
    assert data["arguments"] == PLOT_ARGUMENTS_DISPLAY

    # The persisted assistant call keeps display arguments only; the figure is
    # stored once, in the tool result row.
    assistant_entry = _assistant_tool_call_entry(body["entries"], "render_plot")
    raw_arguments = assistant_entry["model"][0]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(raw_arguments) == {
        "title": PLOT_TITLE,
        "caption": PLOT_CAPTION,
    }
    assert "Jan" not in raw_arguments
    persisted_model = json.dumps(assistant_entry["model"], ensure_ascii=False)
    assert '"figure"' not in persisted_model
    assert '"figure_summary"' not in persisted_model

    # The current run still sees the chart call and its result.
    assert len(fake.requests) == 2
    current_payload = json.dumps(fake.requests[1].messages, ensure_ascii=False)
    assert "render_plot" in current_payload
    assert "call_plot_1" in current_payload
    assert "Jan" in current_payload
    assert "Rendered a chart in an earlier step" not in current_payload

    # The next run drops the historical call and its orphaned result silently.
    second_body = _send_message(client, conversation_id, "Thanks, what changed?")
    assert second_body["answer"] == "The chart stays available above."
    assert len(fake.requests) == 3
    next_payload = json.dumps(fake.requests[2].messages, ensure_ascii=False)
    assert "render_plot" not in next_payload
    assert "call_plot_1" not in next_payload
    assert "Jan" not in next_payload
    assert "Rendered a chart" not in next_payload
    assert "The chart shows more memories in the second month." in next_payload
    assert not [
        message for message in fake.requests[2].messages if message.get("role") == "tool"
    ]

    reloaded_results = _tool_results(_reload_entries(client, conversation_id))
    assert len(reloaded_results) == 1
    assert reloaded_results[0]["data"] == data
    assert reloaded_results[0]["data"]["plot"]["figure"] == PLOT_FIGURE


def _call(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    """Build one persisted assistant function call."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _plot_call_entries(
    *,
    content: str,
    plot_arguments: str,
    by_run_id: int | None,
    with_result: bool = True,
    result_status: str = "ok",
    figure: dict[str, Any] | None = None,
) -> tuple[TranscriptEntry, ...]:
    """Build one user turn plus a render_plot call and optional result."""
    entries: list[TranscriptEntry] = [
        TranscriptEntry(
            id=1,
            kind=KIND_USER,
            messages=({"role": "user", "content": "Chart it."},),
        ),
        TranscriptEntry(
            id=2,
            kind=KIND_ASSISTANT,
            by_run_id=by_run_id,
            messages=(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        _call("call_plot_history", "render_plot", plot_arguments)
                    ],
                },
            ),
        ),
    ]
    if with_result:
        result_data: dict[str, Any] = {"status": result_status, "error_code": None}
        if figure is not None:
            result_data["plot"] = {"figure": figure}
        entries.append(
            TranscriptEntry(
                id=3,
                kind=KIND_TOOL_RESULT,
                by_run_id=by_run_id,
                data=result_data,
                messages=(
                    {
                        "role": "tool",
                        "tool_call_id": "call_plot_history",
                        "name": "render_plot",
                        "content": "<tool_result>rendered</tool_result>",
                    },
                ),
            )
        )
    return tuple(entries)


def test_historical_plot_call_is_removed_without_a_note() -> None:
    """A plot from an earlier run leaves only the message's own text."""
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True),
        by_run_id=1,
        figure=PLOT_FIGURE,
    )

    context = build_context(entries, keep_plot_run_id=2)

    assert [message["role"] for message in context.messages] == ["user", "assistant"]
    assistant = context.messages[1]
    assert "tool_calls" not in assistant
    assert assistant["content"] == "Here is the chart."
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "render_plot" not in payload
    assert "call_plot_history" not in payload
    assert PLOT_TITLE not in payload
    assert "Jan" not in payload
    assert "Rendered a chart" not in payload
    assert "earlier step" not in payload
    assert "omitted from history" not in payload


def test_current_run_plot_call_and_result_are_kept() -> None:
    """The run that rendered the chart still sees its call, figure, and result."""
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True),
        by_run_id=7,
        figure=PLOT_FIGURE,
    )

    context = build_context(entries, keep_plot_run_id=7)

    assert [message["role"] for message in context.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assistant = context.messages[1]
    assert assistant["content"] == "Here is the chart."
    assert [call["id"] for call in assistant["tool_calls"]] == ["call_plot_history"]
    raw_arguments = assistant["tool_calls"][0]["function"]["arguments"]
    arguments = json.loads(raw_arguments)
    assert arguments == {**PLOT_ARGUMENTS_DISPLAY, "figure": PLOT_FIGURE}
    assert arguments["figure"] == PLOT_FIGURE
    # The provider string is deterministic so the cache prefix stays stable.
    assert raw_arguments == json.dumps(
        arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assert context.messages[2]["tool_call_id"] == "call_plot_history"
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "Rendered a chart" not in payload


def _figure_of_bytes(size: int) -> dict[str, Any]:
    """Build a figure whose canonical JSON encoding is exactly ``size`` bytes."""
    base = {"data": [{"type": "bar", "name": ""}]}
    base_size = len(
        json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    figure = {"data": [{"type": "bar", "name": "x" * (size - base_size)}]}
    encoded = json.dumps(
        figure, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert len(encoded) == size
    return figure


@pytest.mark.parametrize(
    ("size", "rehydrated"),
    [
        (PLOT_CONTEXT_MAX_BYTES, True),
        (PLOT_CONTEXT_MAX_BYTES + 1, False),
    ],
)
def test_plot_context_budget_boundary(size: int, rehydrated: bool) -> None:
    """The figure is replayed at the byte cap and dropped just above it."""
    figure = _figure_of_bytes(size)
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True),
        by_run_id=3,
        figure=figure,
    )

    context = build_context(entries, keep_plot_run_id=3)

    assert [message["role"] for message in context.messages] == [
        "user",
        "assistant",
        "tool",
    ]
    assistant = context.messages[1]
    assert [call["id"] for call in assistant["tool_calls"]] == ["call_plot_history"]
    arguments = json.loads(assistant["tool_calls"][0]["function"]["arguments"])
    if rehydrated:
        assert arguments["figure"] == figure
    else:
        # Oversized figures keep the display form. No error and no note.
        assert arguments == PLOT_ARGUMENTS_DISPLAY
        assert "figure" not in arguments
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "omitted" not in payload
    assert "too large" not in payload


@pytest.mark.parametrize(
    ("with_result", "result_status", "figure"),
    [
        pytest.param(False, "ok", None, id="missing-result"),
        pytest.param(True, "error", None, id="failed-result"),
        pytest.param(True, "ok", None, id="missing-figure"),
    ],
)
def test_plot_call_without_a_stored_figure_keeps_display_arguments(
    with_result: bool,
    result_status: str,
    figure: dict[str, Any] | None,
) -> None:
    """A missing or failed figure leaves the display form, with no placeholder."""
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True),
        by_run_id=5,
        with_result=with_result,
        result_status=result_status,
        figure=figure,
    )

    context = build_context(entries, keep_plot_run_id=5)

    assistant = context.messages[1]
    assert [call["id"] for call in assistant["tool_calls"]] == ["call_plot_history"]
    arguments = json.loads(assistant["tool_calls"][0]["function"]["arguments"])
    assert arguments == PLOT_ARGUMENTS_DISPLAY
    assert "figure" not in arguments
    assert "figure_summary" not in arguments


def test_active_plot_call_ignores_a_non_object_figure() -> None:
    """A figure that is not an object is not rehydrated into the call."""
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True),
        by_run_id=5,
        figure=None,
    )
    entries = (
        entries[0],
        entries[1],
        TranscriptEntry(
            id=3,
            kind=KIND_TOOL_RESULT,
            by_run_id=5,
            data={"status": "ok", "plot": {"figure": ["not", "a", "dict"]}},
            messages=entries[2].messages,
        ),
    )

    context = build_context(entries, keep_plot_run_id=5)

    arguments = json.loads(
        context.messages[1]["tool_calls"][0]["function"]["arguments"]
    )
    assert arguments == PLOT_ARGUMENTS_DISPLAY


def test_plot_only_message_is_dropped_when_historical() -> None:
    """A message with only a historical plot call disappears entirely."""
    entries = _plot_call_entries(
        content="",
        plot_arguments=json.dumps({"title": PLOT_TITLE}),
        by_run_id=1,
        with_result=False,
    )

    context = build_context(entries, keep_plot_run_id=2)

    assert [message["role"] for message in context.messages] == ["user"]
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "render_plot" not in payload
    assert "tool_result_missing" not in payload
    assert "Rendered a chart" not in payload


def test_failed_historical_plot_is_removed_silently() -> None:
    """A failed plot call is removed without a diagnostic note."""
    entries = _plot_call_entries(
        content="The chart failed.",
        plot_arguments=json.dumps({"title": PLOT_TITLE}),
        by_run_id=1,
        result_status="error",
    )

    context = build_context(entries, keep_plot_run_id=2)

    assert [message["role"] for message in context.messages] == ["user", "assistant"]
    assert context.messages[1]["content"] == "The chart failed."
    assert "tool_calls" not in context.messages[1]
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "render_plot" not in payload
    assert "failed with" not in payload
    assert "omitted from history" not in payload


def test_mixed_tool_batch_keeps_other_calls_and_results() -> None:
    """Only the historical plot call is dropped; sibling calls stay intact."""
    plot_arguments = json.dumps(
        {"title": PLOT_TITLE, "figure": PLOT_FIGURE}, sort_keys=True
    )
    calculate = json.dumps({"expression": "1 + 1"})
    read_file = json.dumps({"path": "/library"})
    entries = (
        TranscriptEntry(
            id=1,
            kind=KIND_USER,
            messages=({"role": "user", "content": "Chart and check."},),
        ),
        TranscriptEntry(
            id=2,
            kind=KIND_ASSISTANT,
            by_run_id=1,
            messages=(
                {
                    "role": "assistant",
                    "content": "Checking both.",
                    "tool_calls": [
                        _call("call_plot_mixed", "render_plot", plot_arguments),
                        _call("call_calc_mixed", "calculate", calculate),
                        _call("call_read_mixed", "read_file", read_file),
                    ],
                },
            ),
        ),
        TranscriptEntry(
            id=3,
            kind=KIND_TOOL_RESULT,
            by_run_id=1,
            messages=(
                {
                    "role": "tool",
                    "tool_call_id": "call_plot_mixed",
                    "name": "render_plot",
                    "content": "<tool_result>plot</tool_result>",
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_calc_mixed",
                    "name": "calculate",
                    "content": "<tool_result>2</tool_result>",
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_read_mixed",
                    "name": "read_file",
                    "content": "<tool_result>files</tool_result>",
                },
            ),
        ),
    )

    context = build_context(entries, keep_plot_run_id=2)

    assert [message["role"] for message in context.messages] == [
        "user",
        "assistant",
        "tool",
        "tool",
    ]
    assistant = context.messages[1]
    assert assistant["content"] == "Checking both."
    assert [call["id"] for call in assistant["tool_calls"]] == [
        "call_calc_mixed",
        "call_read_mixed",
    ]
    assert [message["tool_call_id"] for message in context.messages[2:]] == [
        "call_calc_mixed",
        "call_read_mixed",
    ]
    payload = json.dumps(context.messages, ensure_ascii=False)
    assert "call_plot_mixed" not in payload
    assert "Rendered a chart in an earlier step" not in payload


def test_active_mixed_batch_keeps_siblings_and_rehydrates_the_plot() -> None:
    """Keeping the plot call leaves sibling calls and results untouched."""
    plot_arguments = json.dumps(PLOT_ARGUMENTS_DISPLAY, sort_keys=True)
    calculate = json.dumps({"expression": "1 + 1"})
    entries = (
        TranscriptEntry(
            id=1,
            kind=KIND_USER,
            messages=({"role": "user", "content": "Chart and check."},),
        ),
        TranscriptEntry(
            id=2,
            kind=KIND_ASSISTANT,
            by_run_id=9,
            messages=(
                {
                    "role": "assistant",
                    "content": "Checking both.",
                    "tool_calls": [
                        _call("call_plot_active_mixed", "render_plot", plot_arguments),
                        _call("call_calc_active_mixed", "calculate", calculate),
                    ],
                },
            ),
        ),
        TranscriptEntry(
            id=3,
            kind=KIND_TOOL_RESULT,
            by_run_id=9,
            data={"status": "ok", "plot": {"figure": PLOT_FIGURE}},
            messages=(
                {
                    "role": "tool",
                    "tool_call_id": "call_plot_active_mixed",
                    "name": "render_plot",
                    "content": "<tool_result>plot</tool_result>",
                },
            ),
        ),
        TranscriptEntry(
            id=4,
            kind=KIND_TOOL_RESULT,
            by_run_id=9,
            data={"status": "ok"},
            messages=(
                {
                    "role": "tool",
                    "tool_call_id": "call_calc_active_mixed",
                    "name": "calculate",
                    "content": "<tool_result>2</tool_result>",
                },
            ),
        ),
    )

    context = build_context(entries, keep_plot_run_id=9)

    assistant = context.messages[1]
    calls = {call["id"]: call for call in assistant["tool_calls"]}
    assert set(calls) == {"call_plot_active_mixed", "call_calc_active_mixed"}
    plot_call = json.loads(calls["call_plot_active_mixed"]["function"]["arguments"])
    assert plot_call["figure"] == PLOT_FIGURE
    assert json.loads(calls["call_calc_active_mixed"]["function"]["arguments"]) == {
        "expression": "1 + 1"
    }
    assert [message["tool_call_id"] for message in context.messages[2:]] == [
        "call_plot_active_mixed",
        "call_calc_active_mixed",
    ]


def test_unparseable_historical_plot_call_is_removed() -> None:
    """Run ownership, not JSON shape, decides whether a plot call is replayed."""
    broken = '{"title": "broken"'
    entries = _plot_call_entries(
        content="Here is the chart.",
        plot_arguments=broken,
        by_run_id=1,
    )

    context = build_context(entries, keep_plot_run_id=2)

    assert [message["role"] for message in context.messages] == ["user", "assistant"]
    assert context.messages[1]["content"] == "Here is the chart."
    assert "tool_calls" not in context.messages[1]
    assert "call_plot_history" not in json.dumps(context.messages)


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
                "figure": {"data": [{"type": "scatter", "y": list(range(10_001))}]},
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


def test_plot_point_count_counts_grid_cells() -> None:
    """2D surface and heatmap arrays count cells, not rows."""
    surface = sanitize_plot_figure(
        {
            "data": [
                {
                    "type": "surface",
                    "x": _grid(7, 9),
                    "y": _grid(7, 9),
                    "z": _grid(7, 9),
                }
            ]
        }
    )
    assert surface.point_count == 63
    assert (surface.grid_rows, surface.grid_columns) == (7, 9)

    heatmap = sanitize_plot_figure(
        {"data": [{"type": "heatmap", "z": _grid(2, 3)}]}
    )
    assert heatmap.point_count == 6
    assert (heatmap.grid_rows, heatmap.grid_columns) == (2, 3)


def test_plot_point_count_keeps_flat_and_ragged_semantics() -> None:
    """A flat array counts its length; ragged rows sum their cells."""
    scatter = sanitize_plot_figure(
        {
            "data": [
                {
                    "type": "scatter",
                    "x": list(range(10)),
                    "y": list(range(10)),
                }
            ]
        }
    )
    assert scatter.point_count == 10
    assert scatter.grid_rows is None
    assert scatter.grid_columns is None

    ragged = sanitize_plot_figure(
        {"data": [{"type": "heatmap", "z": [[1, 2, 3], [4, 5]]}]}
    )
    assert ragged.point_count == 5
    assert ragged.grid_rows is None


def test_surface_grid_enforces_the_real_cell_cap() -> None:
    """A 60 x 60 surface fits; a 101 x 101 grid exceeds 10,000 cells."""
    accepted = sanitize_plot_figure(
        {"data": [{"type": "surface", "z": _grid(60, 60)}]}
    )
    assert accepted.point_count == 3_600
    assert (accepted.grid_rows, accepted.grid_columns) == (60, 60)

    with pytest.raises(PlotSpecError, match="data points; the limit is 10,000"):
        sanitize_plot_figure(
            {"data": [{"type": "surface", "z": _grid(101, 101)}]}
        )


def test_plot_node_cap_rejects_a_wide_figure() -> None:
    """A layout above 100,000 JSON nodes is rejected even when points fit."""
    figure = {
        "data": [{"type": "bar", "x": ["a"], "y": [1]}],
        "layout": {
            "a": [None] * 50_000,
            "b": [None] * 50_000,
        },
    }
    with pytest.raises(PlotSpecError, match="JSON nodes; the limit is 100,000"):
        sanitize_plot_figure(figure)


def test_sanitize_plot_figure_honors_custom_limits() -> None:
    """The sanitizer reports the configured budget, not the module default."""
    ten_points = {
        "data": [
            {
                "type": "scatter",
                "x": list(range(10)),
                "y": list(range(10)),
            }
        ]
    }
    accepted = sanitize_plot_figure(
        ten_points,
        max_points=10,
        max_bytes=10_000,
        max_nodes=1_000,
    )
    assert accepted.point_count == 10

    with pytest.raises(PlotSpecError, match="10 data points; the limit is 5"):
        sanitize_plot_figure(
            ten_points,
            max_points=5,
            max_bytes=10_000,
            max_nodes=1_000,
        )

    padded = {
        "data": [{"type": "bar", "y": [1]}],
        "layout": {"title": {"text": "x" * 200}},
    }
    with pytest.raises(PlotSpecError, match="bytes; the limit is 100"):
        sanitize_plot_figure(
            padded,
            max_points=10_000,
            max_bytes=100,
            max_nodes=1_000,
        )

    with pytest.raises(PlotSpecError, match="JSON nodes; the limit is 5"):
        sanitize_plot_figure(
            {"data": [{"type": "bar", "x": ["a"], "y": [1]}]},
            max_points=10_000,
            max_bytes=10_000,
            max_nodes=5,
        )


def test_render_plot_uses_the_runtime_point_budget(client: TestClient) -> None:
    """A stored low point cap rejects a figure that the defaults would accept."""
    defaults = client.get("/api/v1/agent/settings").json()["defaults"]
    updated = client.put(
        "/api/v1/agent/settings",
        json={
            **defaults,
            "max_plot_points": 100,
            "max_plot_nodes": 1_000,
        },
    )
    assert updated.status_code == 200, updated.text

    figure = {
        "data": [
            {
                "type": "scatter",
                "x": list(range(101)),
                "y": list(range(101)),
            }
        ]
    }
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "render_plot",
                {"title": "Too many points", "figure": figure},
                call_id="call_runtime_point_budget",
            ),
            text_result("The chart exceeded the configured point budget."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Runtime plot budget")

    body = _send_message(client, conversation_id, "Draw every point.")

    results = _tool_results(body["entries"])
    assert len(results) == 1
    assert results[0]["data"]["error_code"] == "plot_spec_error"
    assert "101 data points; the limit is 100" in results[0]["data"]["detail"]
    reset = client.post("/api/v1/agent/settings/reset")
    assert reset.status_code == 200, reset.text


def test_surface_receipt_reports_grid_cells(client: TestClient) -> None:
    """The provider receipt states the real cell count and the grid shape."""
    figure = {
        "data": [
            {
                "type": "surface",
                "x": _grid(7, 9),
                "y": _grid(7, 9),
                "z": _grid(7, 9),
            }
        ]
    }
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "render_plot",
                {"title": "3D surface", "figure": figure},
                call_id="call_surface_grid",
            ),
            text_result("The surface shows a complete 7 by 9 grid."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Surface grid receipt")

    body = _send_message(client, conversation_id, "Draw a 7 by 9 surface.")

    results = _tool_results(body["entries"])
    assert len(results) == 1
    data = results[0]["data"]
    assert data["plot"]["stats"]["point_count"] == 63
    content = results[0]["model"][0]["content"]
    assert 'points="63"' in content
    assert 'rows="7"' in content
    assert 'cols="9"' in content
    assert "grid of 63 cells" in content
    assert "points counts every cell, not one row" in content


def test_plot_and_calculation_tools_are_in_catalog(client: TestClient) -> None:
    """Expose both tools with flat, model-facing schemas and guidance."""
    response = client.get("/api/v1/agent/tools")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert catalog["prompt_version"] == "archive-agent-v22"
    assert catalog["tools_version"] == "archive-tools-v21"

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
    assert "current point, byte, and node budgets are enforced by the tool" in description
    assert "10,000 data points" not in description
    assert "600 KB" not in description
    assert "30x30 to 60x60 grid (900-3,600 cells)" in description
    assert "Always pass a complete figure" in description

    serialized = json.dumps(render_plot["parameters"])
    assert "$ref" not in serialized
    assert "$defs" not in serialized


def test_plot_tool_result_content_is_small(client: TestClient) -> None:
    """Keep the provider-facing plot result a short, unambiguous receipt."""
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
    assert 'visible="true"' in content
    assert "The chart is already rendered and visible to the user" in content
    assert "Do not call render_plot again for this request" in content
    assert "Reply with a one- or two-sentence explanation" in content
    assert "Jan" not in content
    assert '"data"' not in content
    assert "[3,5]" not in content
    assert len(content) < 700


TRUNCATED_USAGE = {
    "prompt_tokens": 3998,
    "completion_tokens": 10000,
    "total_tokens": 13998,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 3998,
}


def _truncated_plot_result(call_id: str) -> ChatResult:
    """Build a completion cut off at the output cap with no visible text."""
    return ChatResult(
        text="",
        tool_calls=[
            ChatToolCall(
                call_id=call_id,
                name="render_plot",
                arguments={},
                raw_arguments=(
                    '{"title":"Random 3D plot","figure":{"data":'
                    '[{"type":"scatter3d","x":[1,2'
                ),
                parse_error="Unterminated JSON string",
            )
        ],
        finish_reason="length",
        model="fake-chat",
        usage=dict(TRUNCATED_USAGE),
    )


def test_output_limit_retries_with_smaller_output_notice(client: TestClient) -> None:
    """Retry the same step once after a truncated completion with no text."""
    fake = FakeChatGenerator(
        [
            _truncated_plot_result("call_plot_truncated"),
            text_result(
                "I kept the chart request smaller.",
                usage={
                    "prompt_tokens": 4000,
                    "completion_tokens": 50,
                    "total_tokens": 4050,
                    "prompt_cache_hit_tokens": 3000,
                    "prompt_cache_miss_tokens": 1000,
                },
            ),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Output limit retry")

    body = _send_message(client, conversation_id, "Draw a random 3D plot.")

    assert body["answer"] == "I kept the chart request smaller."
    assert len(fake.requests) == 2
    retry_block = fake.requests[1].messages[-1]
    assert retry_block["role"] == "system"
    assert retry_block["content"].startswith("<agent_status")
    assert '<retry_notice reason="output_limit">' in retry_block["content"]
    assert "smaller result" in retry_block["content"]

    # The truncated call never ran and the retry did not emit a tool result.
    assert _tool_results(body["entries"]) == []
    assistant_entries = [
        entry for entry in body["entries"] if entry["kind"] == "pi.assistant"
    ]
    assert len(assistant_entries) == 1
    assert assistant_entries[0]["data"]["finish_reason"] == "stop"
    assert "error" not in assistant_entries[0]["data"]
    assert assistant_entries[0]["data"]["usage"] == {
        "prompt_tokens": 7998,
        "completion_tokens": 10050,
        "total_tokens": 18048,
        "prompt_cache_hit_tokens": 3000,
        "prompt_cache_miss_tokens": 4998,
    }
    assert body["run"]["prompt_tokens"] == 7998
    assert body["run"]["completion_tokens"] == 10050
    assert body["run"]["total_tokens"] == 18048


def test_output_limit_retry_exhausted_returns_graceful_text(
    client: TestClient,
) -> None:
    """Two truncated completions become a normal answer, not a failed run."""
    fake = FakeChatGenerator(
        [
            _truncated_plot_result("call_plot_truncated_1"),
            _truncated_plot_result("call_plot_truncated_2"),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Output limit exhausted")

    body = _send_message(client, conversation_id, "Draw a random 3D plot.")

    assert len(fake.requests) == 2
    assert body["answer"] is not None
    assert "output budget" in body["answer"]
    assert "smaller or simpler" in body["answer"]
    assert _tool_results(body["entries"]) == []

    assistant_entries = [
        entry for entry in body["entries"] if entry["kind"] == "pi.assistant"
    ]
    assert len(assistant_entries) == 1
    assert assistant_entries[0]["data"]["finish_reason"] == "stop"
    assert "error" not in assistant_entries[0]["data"]
    assert assistant_entries[0]["data"]["usage"]["completion_tokens"] == 20000
    assert body["run"]["completion_tokens"] == 20000

    reloaded = _reload_entries(client, conversation_id)
    assert _tool_results(reloaded) == []
    reloaded_assistant = [
        entry for entry in reloaded if entry["kind"] == "pi.assistant"
    ]
    assert len(reloaded_assistant) == 1
    assert reloaded_assistant[0]["data"]["finish_reason"] == "stop"
    assert "error" not in reloaded_assistant[0]["data"]


def test_duplicate_render_plot_is_not_executed(client: TestClient) -> None:
    """A later render_plot with the same title returns a notice, not a chart."""
    duplicate_arguments = {
        "title": f"  {PLOT_TITLE.upper()}  ",
        "caption": PLOT_CAPTION,
        "figure": PLOT_FIGURE,
    }
    fake = FakeChatGenerator(
        [
            tool_call_result(
                "render_plot",
                {
                    "title": PLOT_TITLE,
                    "caption": PLOT_CAPTION,
                    "figure": PLOT_FIGURE,
                },
                call_id="call_plot_first",
            ),
            tool_call_result(
                "render_plot",
                duplicate_arguments,
                call_id="call_plot_duplicate",
            ),
            text_result("The chart is shown above."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Duplicate plot")

    body = _send_message(client, conversation_id, "Draw this chart twice.")

    assert body["answer"] == "The chart is shown above."
    results = _tool_results(body["entries"])
    assert len(results) == 2
    assert sum(1 for entry in results if "plot" in entry["data"]) == 1
    duplicate = results[1]
    assert duplicate["data"]["status"] == "ok"
    assert duplicate["data"]["duplicate"] is True
    assert "plot" not in duplicate["data"]
    duplicate_content = duplicate["model"][0]["content"]
    assert "<plot_already_rendered" in duplicate_content
    assert "already visible in the chat" in duplicate_content
    assert "Do not call render_plot again" in duplicate_content

    # Both calls belong to the current run, so the provider replay keeps them
    # and adds no synthetic note.
    for index, request in enumerate(fake.requests[1:], start=1):
        payload = json.dumps(request.messages, ensure_ascii=False)
        assert "render_plot" in payload
        assert "call_plot_first" in payload
        assert "Rendered a chart" not in payload
        assert "omitted from history" not in payload
        tools = [
            message for message in request.messages if message.get("role") == "tool"
        ]
        assert len(tools) == index

    reloaded = _reload_entries(client, conversation_id)
    assert sum(1 for entry in _tool_results(reloaded) if "plot" in entry["data"]) == 1


def test_duplicate_render_plot_loop_breaker(client: TestClient) -> None:
    """Stop after the second duplicate notice and answer in normal text."""
    arguments = {
        "title": PLOT_TITLE,
        "caption": PLOT_CAPTION,
        "figure": PLOT_FIGURE,
    }
    fake = FakeChatGenerator(
        [
            tool_call_result("render_plot", arguments, call_id="call_plot_1"),
            tool_call_result("render_plot", arguments, call_id="call_plot_2"),
            tool_call_result("render_plot", arguments, call_id="call_plot_3"),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Duplicate plot loop")

    body = _send_message(client, conversation_id, "Keep drawing the same chart.")

    # The loop breaker completes after the second duplicate, so the third
    # scripted completion is never consumed and no fourth request is made.
    assert len(fake.requests) == 3
    assert fake.remaining == 0
    assert body["answer"] is not None
    assert body["answer"].startswith("The chart is already visible in the chat")

    results = _tool_results(body["entries"])
    assert len(results) == 3
    assert sum(1 for entry in results if "plot" in entry["data"]) == 1
    assistant_entries = [
        entry for entry in body["entries"] if entry["kind"] == "pi.assistant"
    ]
    assert assistant_entries[-1]["data"]["finish_reason"] == "stop"
    assert "error" not in assistant_entries[-1]["data"]


def _invalid_plot_call(call_id: str) -> ChatResult:
    """Request render_plot without the required figure."""
    return tool_call_result(
        "render_plot",
        {"title": "3D sphere"},
        call_id=call_id,
    )


def test_repeated_invalid_arguments_add_retry_notice(client: TestClient) -> None:
    """Two rejected calls make the next provider request carry the notice."""
    fake = FakeChatGenerator(
        [
            _invalid_plot_call("call_invalid_1"),
            _invalid_plot_call("call_invalid_2"),
            text_result("I need a complete figure before I can draw that chart."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Invalid arguments notice")

    body = _send_message(client, conversation_id, "Draw a 3D sphere.")

    assert len(fake.requests) == 3
    status_block = fake.requests[2].messages[-1]
    assert status_block["role"] == "system"
    assert status_block["content"].startswith("<agent_status")
    assert '<retry_notice reason="tool_arguments">' in status_block["content"]
    assert "complete figure object" in status_block["content"]
    assert "answer the user in text without a chart" in status_block["content"]

    results = _tool_results(body["entries"])
    assert [entry["data"]["error_code"] for entry in results] == [
        "invalid_tool_arguments",
        "invalid_tool_arguments",
    ]
    assert body["error_code"] is None


def test_successful_tool_call_resets_the_invalid_argument_streak(
    client: TestClient,
) -> None:
    """A successful call between failures restarts the consecutive count."""
    fake = FakeChatGenerator(
        [
            _invalid_plot_call("call_invalid_1"),
            tool_call_result(
                "calculate",
                {"expression": "1 + 1"},
                call_id="call_good",
            ),
            _invalid_plot_call("call_invalid_2"),
            text_result("The calculation ran; I still cannot draw that chart."),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Reset invalid arguments")

    body = _send_message(client, conversation_id, "Calculate and draw.")

    assert len(fake.requests) == 4
    for request in fake.requests:
        assert '<retry_notice reason="tool_arguments">' not in request.messages[-1].get(
            "content", ""
        )

    results = _tool_results(body["entries"])
    assert [entry["data"]["error_code"] for entry in results] == [
        "invalid_tool_arguments",
        None,
        "invalid_tool_arguments",
    ]
    assert [entry["data"]["status"] for entry in results] == ["error", "ok", "error"]
    assert body["error_code"] is None


def test_invalid_arguments_loop_breaker_answers_without_tools(
    client: TestClient,
) -> None:
    """A third failure runs one text-only call, completes, and emits no error."""
    final_answer = "I cannot draw that chart because the figure was incomplete."
    fake = FakeChatGenerator(
        [
            _invalid_plot_call("call_invalid_1"),
            _invalid_plot_call("call_invalid_2"),
            _invalid_plot_call("call_invalid_3"),
            text_result(final_answer),
        ]
    )
    client.app.state.agent_chat_generator = fake
    conversation_id = _create_conversation(client, "Invalid arguments loop")

    response = client.post(
        f"/api/v1/agent/conversations/{conversation_id}/messages",
        json={"content": "Draw a 3D sphere."},
    )
    assert response.status_code == 200, response.text

    # The run ends normally: the final text-only answer is the last event and
    # no error event is emitted.
    assert "event: error" not in response.text
    assert "event: run_end" in response.text
    assert '"status":"completed"' in response.text

    assert len(fake.requests) == 4
    assert fake.requests[3].tools == []
    # Failures remain transparent inside the run: no synthetic note is added,
    # and every recorded call and result is still visible to the model.
    final_payload = json.dumps(fake.requests[3].messages, ensure_ascii=False)
    assert "render_plot" in final_payload
    assert "invalid_tool_arguments" in final_payload
    assert "Rendered a chart" not in final_payload
    assert "omitted from history" not in final_payload
    final_tools = [
        message for message in fake.requests[3].messages if message.get("role") == "tool"
    ]
    assert len(final_tools) == 3

    entries = _reload_entries(client, conversation_id)
    results = _tool_results(entries)
    assert [entry["data"]["error_code"] for entry in results] == [
        "invalid_tool_arguments",
        "invalid_tool_arguments",
        "invalid_tool_arguments",
    ]
    assistant_entries = [entry for entry in entries if entry["kind"] == "pi.assistant"]
    assert assistant_entries[-1]["model"][0]["content"] == final_answer
    assert assistant_entries[-1]["data"]["finish_reason"] == "stop"
    assert "error" not in assistant_entries[-1]["data"]
