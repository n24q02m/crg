"""Retry classification of the cloud embedding path (plain-HTTP, post-de-host).

``_is_retryable`` must classify on error-message semantics, not the exception
class name or status code: the transport (hull-core's ``ProviderError``,
httpx errors) can re-wrap a provider's permanent 4xx as a generic
connection-shaped error with a synthetic 500. Retrying those burns the full
retry budget on a request that can never succeed.

The old litellm-based tests are ported to the current plain-HTTP transport:
the "wrapped 422" shape is reproduced with a connection-named exception class
carrying ``status_code = 500`` and Cohere's real 422 body, and the batch-level
tests drive ``CloudEmbeddingBackend`` through its documented dispatch seam
(monkeypatch ``_post_embeddings``).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from better_code_review_graph.embeddings import (
    _MAX_RETRIES,
    CloudEmbeddingBackend,
    _is_retryable,
)

# The exact provider body cohere returns for an unsupported output_dimension,
# as the transport surfaces it after wrapping the 422 in a connection error.
_COHERE_422_BODY = (
    'CohereException - {"message": "768 is not a valid output_dimension, '
    'use one of 256, 512, 1024, 1536"}'
)


class WrappedConnectionError(Exception):
    """Transport-wrapped error: connection-shaped class name, synthetic 500."""

    status_code = 500


def _wrapped_422() -> WrappedConnectionError:
    """A connection-named error wrapping cohere's 422 dims rejection."""
    return WrappedConnectionError(_COHERE_422_BODY)


class TestIsRetryableClassification:
    """`_is_retryable` must classify on error semantics, not the class name."""

    def test_wrapped_422_unsupported_dimension_is_not_retryable(self):
        exc = _wrapped_422()
        # Guard: this really is the tricky shape (class name -> "connection",
        # synthetic 500) that fooled the old substring matcher.
        assert "connection" in type(exc).__name__.lower()
        assert getattr(exc, "status_code", None) == 500

        assert _is_retryable(exc) is False

    def test_genuine_connection_error_is_retryable(self):
        exc = Exception("Connection error.")

        assert _is_retryable(exc) is True

    def test_rate_limit_is_retryable(self):
        exc = Exception("rate limit exceeded")

        assert _is_retryable(exc) is True

    def test_timeout_is_retryable(self):
        exc = Exception("Request timed out.")

        assert _is_retryable(exc) is True

    def test_invalid_api_key_is_not_retryable(self):
        exc = WrappedConnectionError("AuthenticationError - invalid api key")

        assert _is_retryable(exc) is False

    def test_model_not_found_404_is_not_retryable(self):
        exc = WrappedConnectionError("NotFoundError - model does not exist (404)")

        assert _is_retryable(exc) is False


class TestPermanentErrorNotRetriedAtBatchLevel:
    """The retry loop must fail fast on a permanent error, not burn 3 attempts."""

    def test_wrapped_422_fails_fast_without_retries(self):
        # Reproduces the propagation finding: a wrapped permanent 422 must be
        # raised after a SINGLE provider call, not retried 3x.
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise _wrapped_422()

            with patch(
                "better_code_review_graph.embeddings._post_embeddings",
                side_effect=side_effect,
            ):
                with pytest.raises(WrappedConnectionError):
                    backend.embed_texts(["test"], dimensions=1024)

            assert call_count == 1

    def test_genuine_connection_error_is_retried_to_exhaustion(self):
        # Contrast: a genuine connection error IS retried up to _MAX_RETRIES,
        # proving the classification narrows only the permanent class.
        with patch.dict(os.environ, {}, clear=True):
            backend = CloudEmbeddingBackend(model="cohere/embed-v4.0")
            call_count = 0

            def side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                raise Exception("Connection error.")

            with patch(
                "better_code_review_graph.embeddings._post_embeddings",
                side_effect=side_effect,
            ):
                with patch("better_code_review_graph.embeddings.time.sleep"):
                    with pytest.raises(Exception, match="Connection error."):
                        backend.embed_texts(["test"], dimensions=1024)

            assert call_count == _MAX_RETRIES
