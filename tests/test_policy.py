import pytest

from observe.policy import PolicyOutcome, evaluate_sink


def test_block_pii_external_post() -> None:
    r = evaluate_sink("http_post_external", {"pii", "public"})
    assert r.outcome == PolicyOutcome.deny


def test_allow_public_file_write() -> None:
    r = evaluate_sink("file_write", {"public"}, sink_meta={"path": "workspace/x.txt"})
    assert r.outcome == PolicyOutcome.allow


def test_block_internal_outside() -> None:
    r = evaluate_sink(
        "file_write",
        {"internal_doc"},
        sink_meta={"path": "outside/x.txt"},
    )
    assert r.outcome == PolicyOutcome.deny
