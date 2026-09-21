import json

from better_code_review_graph.tools import _estimate_payload_bytes


def test_estimate_payload_bytes_empty():
    assert _estimate_payload_bytes() == 0


def test_estimate_payload_bytes_single_dict():
    d = {"key": "value", "int": 123, "bool": True, "none": None}
    estimate = _estimate_payload_bytes(d)
    actual_json_len = len(json.dumps(d, separators=(",", ":")))
    assert estimate == actual_json_len
    assert isinstance(estimate, int)


def test_estimate_payload_bytes_list_of_dicts():
    payload = [{"a": 1}, {"b": 2}]
    estimate = _estimate_payload_bytes(payload)
    actual_json_len = len(json.dumps(payload, separators=(",", ":")))
    assert estimate == actual_json_len


def test_estimate_payload_bytes_multiple_args():
    d1 = {"a": 1}
    d2 = {"b": 2}
    l1 = [{"c": 3}]
    expected = (
        len(json.dumps(d1, separators=(",", ":")))
        + len(json.dumps(d2, separators=(",", ":")))
        + len(json.dumps(l1, separators=(",", ":")))
    )
    assert _estimate_payload_bytes(d1, d2, l1) == expected


def test_estimate_payload_bytes_overestimation():
    # Because estimate_payload_bytes now uses json.dumps directly, the length is exact
    d = {"key": "it's a string with single quote"}
    estimate = _estimate_payload_bytes(d)
    actual_json_len = len(json.dumps(d, separators=(",", ":")))
    assert estimate == actual_json_len
