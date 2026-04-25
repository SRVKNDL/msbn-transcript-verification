"""Tests for PrefillLambda."""

import importlib.util
from io import BytesIO
import json
import os
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("BUCKET_NAME", "msbn-transcripts-test")

_HANDLER_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../services/prefill/handler.py")
)
_spec = importlib.util.spec_from_file_location("prefill_handler", _HANDLER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler

_BUCKET_NAME = "msbn-transcripts-test"
_REVIEWER_EMAIL = "reviewer@msbn.ms.gov"


def _make_event(route_key: str, *, body: dict | None = None, email: str = _REVIEWER_EMAIL):
    event = {
        "version": "2.0",
        "routeKey": route_key,
        "requestContext": {
            "http": {"method": route_key.split(" ", 1)[0], "path": "/prefill"},
            "authorizer": {"jwt": {"claims": {"email": email}}},
        },
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _make_event_no_auth(route_key: str):
    return {
        "version": "2.0",
        "routeKey": route_key,
        "requestContext": {"http": {"method": "POST", "path": "/prefill"}},
    }


def _body(response: dict) -> dict:
    return json.loads(response["body"])


@pytest.fixture()
def s3_client(monkeypatch):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=_BUCKET_NAME)
        monkeypatch.setattr(_mod, "_s3", client)
        yield client


def test_missing_auth_returns_403(lambda_context):
    resp = handler(_make_event_no_auth("POST /prefill"), lambda_context)
    assert resp["statusCode"] == 403
    assert "reviewer identity" in _body(resp)["error"].lower()


def test_create_prefill_upload_uses_preview_prefix(s3_client, lambda_context):
    event = _make_event(
        "POST /prefill-uploads",
        body={"filename": "transcript.pdf", "contentType": "application/pdf", "size": 10},
    )

    resp = handler(event, lambda_context)
    body = _body(resp)

    assert resp["statusCode"] == 200
    assert body["s3Key"].startswith("preview/")
    assert body["s3Key"].endswith("/transcript.pdf")
    assert "uploadUrl" in body


def test_text_extraction_finds_identity_fields():
    fields = _mod._extract_fields_from_text_pages(
        [
            """
            Student Name: Jane Smith
            Institution: University of Southern Mississippi
            Country: United States
            """
        ]
    )

    assert fields == {
        "applicantName": "Jane Smith",
        "institution": "University of Southern Mississippi",
        "country": "United States",
    }


def test_prefill_uses_embedded_text_before_bedrock(
    s3_client, monkeypatch, lambda_context
):
    s3_client.put_object(
        Bucket=_BUCKET_NAME,
        Key="preview/test/transcript.pdf",
        Body=b"%PDF placeholder",
        ContentType="application/pdf",
    )
    monkeypatch.setattr(
        _mod,
        "_extract_embedded_text_by_page",
        lambda _path: [
            "Student Name: Jane Smith\nInstitution: Test College\nCountry: Canada"
        ],
    )

    def fail_bedrock(*_args, **_kwargs):
        raise AssertionError("Bedrock should not run when embedded text has all fields")

    monkeypatch.setattr(_mod, "_call_bedrock_for_page", fail_bedrock)

    resp = handler(
        _make_event("POST /prefill", body={"s3Key": "preview/test/transcript.pdf"}),
        lambda_context,
    )

    assert resp["statusCode"] == 200
    body = _body(resp)
    assert body["fields"]["applicantName"] == "Jane Smith"
    assert body["fields"]["institution"] == "Test College"
    assert body["fields"]["country"] == "Canada"
    assert body["missingFields"] == []


def test_prefill_rejects_uploads_prefix(lambda_context):
    resp = handler(
        _make_event("POST /prefill", body={"s3Key": "uploads/test/transcript.pdf"}),
        lambda_context,
    )
    assert resp["statusCode"] == 400


def test_prefill_bedrock_recovers_markdown_wrapped_json(monkeypatch):
    raw_text = """```json
{"applicantName":"Jane Smith","institution":"Test College","country":"Canada"}
```"""
    mock_client = MagicMock()
    body = json.dumps({
        "output": {
            "message": {
                "content": [{"text": raw_text}],
            }
        }
    }).encode("utf-8")
    mock_client.invoke_model.return_value = {"body": BytesIO(body)}
    monkeypatch.setattr(_mod, "_bedrock", mock_client)

    parsed = _mod._call_bedrock_for_page(b"fake-image", 1)

    assert parsed == {
        "applicantName": "Jane Smith",
        "institution": "Test College",
        "country": "Canada",
    }
