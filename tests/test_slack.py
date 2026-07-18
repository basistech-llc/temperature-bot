"""Direct HTTP contract tests for the Slack client."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pydantic import BaseModel, Field
import pytest
import requests

from app import slack

AUTHORIZATION_HEADER = "Authorization"
CONTENT_LENGTH_HEADER = "Content-Length"
CONTENT_TYPE_HEADER = "Content-Type"


class SlackRequestBody(BaseModel):
    """Slack request fields emitted by the client."""

    channel: str
    text: str
    ts: str | None = None


class CapturedSlackRequest(BaseModel):
    """One HTTP request observed by the local Slack endpoint."""

    path: str
    authorization: str | None
    content_type: str | None
    body: SlackRequestBody


class SlackStubState(BaseModel):
    """Mutable response and request state shared with the HTTP server thread."""

    response_status: int = 200
    response_body: str = '{"ok": true, "ts": "1712345678.123456"}'
    requests: list[CapturedSlackRequest] = Field(default_factory=list)


def _handler_for(state: SlackStubState):
    class SlackHandler(BaseHTTPRequestHandler):
        """Capture Slack API requests and return the configured response."""

        def do_POST(self):  # pylint: disable=invalid-name
            length = int(self.headers.get(CONTENT_LENGTH_HEADER, "0"))
            body = SlackRequestBody.model_validate_json(self.rfile.read(length))
            state.requests.append(
                CapturedSlackRequest(
                    path=self.path,
                    authorization=self.headers.get(AUTHORIZATION_HEADER),
                    content_type=self.headers.get(CONTENT_TYPE_HEADER),
                    body=body,
                )
            )
            payload = state.response_body.encode("utf-8")
            self.send_response(state.response_status)
            self.send_header(CONTENT_TYPE_HEADER, "application/json")
            self.send_header(CONTENT_LENGTH_HEADER, str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            return

    return SlackHandler


@pytest.fixture
def slack_endpoint(monkeypatch):
    """Run a real local HTTP endpoint and point the Slack client at it."""
    state = SlackStubState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(slack, "SLACK_POST_URL", f"{base_url}/chat.postMessage")
    monkeypatch.setattr(slack, "SLACK_UPDATE_URL", f"{base_url}/chat.update")
    monkeypatch.setenv("SLACK_TOKEN", "contract-token")
    monkeypatch.setenv("SLACK_CHANNEL", "C-default")
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_slack_post_sends_authenticated_json_contract(slack_endpoint):
    state = slack_endpoint

    message_ts = slack.post("Sensor is stuck")

    assert message_ts == "1712345678.123456"
    assert state.requests == [
        CapturedSlackRequest(
            path="/chat.postMessage",
            authorization="Bearer contract-token",
            content_type="application/json; charset=utf-8",
            body=SlackRequestBody(channel="C-default", text="Sensor is stuck"),
        )
    ]


def test_slack_update_uses_override_channel_and_message_timestamp(slack_endpoint):
    state = slack_endpoint
    state.response_body = '{"ok": true, "ts": "1712345678.654321"}'

    message_ts = slack.post(
        "Sensor recovered",
        channel="C-override",
        message_ts="1712345678.123456",
    )

    assert message_ts == "1712345678.654321"
    request = state.requests[0]
    assert request.path == "/chat.update"
    assert request.body == SlackRequestBody(
        channel="C-override",
        text="Sensor recovered",
        ts="1712345678.123456",
    )


@pytest.mark.parametrize(
    ("response_body", "expected_error"),
    (
        ('{"ok": false, "error": "channel_not_found"}', "channel_not_found"),
        ('{"ok": true}', "did not include a message timestamp"),
    ),
)
def test_slack_post_rejects_unsuccessful_response_envelopes(
    slack_endpoint, response_body, expected_error
):
    slack_endpoint.response_body = response_body

    with pytest.raises(RuntimeError, match=expected_error):
        slack.post("Sensor is stuck")


def test_slack_post_raises_for_http_failure(slack_endpoint):
    slack_endpoint.response_status = 503
    slack_endpoint.response_body = '{"ok": false, "error": "unavailable"}'

    with pytest.raises(requests.HTTPError):
        slack.post("Sensor is stuck")
