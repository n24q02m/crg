# syntax=docker/dockerfile:1
# Multi-target Dockerfile per spec
# `~/projects/.superpower/mcp-core/specs/2026-04-30-multi-mode-stdio-http-architecture.md`
# section D6. Build stdio: `docker buildx build --target stdio -t <repo>:stdio .`
# Build http:  `docker buildx build --target http  -t <repo>:http .`
# Build latest (= http): `docker buildx build --target http -t <repo>:latest .`

# ========================
# Stage 1: Builder
# ========================
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim@sha256:531f855bda2c73cd6ef67d56b733b357cea384185b3022bd09f05e002cd144ca AS builder
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN sed -i '/^\[tool\.uv\.sources\]/,/^$/d' pyproject.toml && cp uv.lock /tmp/uv.lock.docker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY src/ src/
COPY migrations/ migrations/
COPY rules/ rules/
RUN sed -i '/^\[tool\.uv\.sources\]/,/^$/d' pyproject.toml && cp /tmp/uv.lock.docker uv.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ========================
# Stage 2: Runtime base (shared by stdio + http targets)
# ========================
FROM python:3.13-slim-bookworm@sha256:2325bb286ec344af3e5898cc224b5844e2707ac6e26b1632516fd3edc84a5e26 AS runtime
LABEL io.modelcontextprotocol.server.name="io.github.n24q02m/better-code-review-graph"
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"
# Make /app writable so appuser can create runtime state dirs
# (~/.mcp-relay/jwt-keys, config.enc, graph DB) — the runtime stage's
# WORKDIR + appuser HOME both resolve to /app, so without this the
# JWT issuer crashes at first authorize with FileNotFoundError.
RUN chown -R appuser:appuser /app
USER appuser

# ========================
# Stage 3a: stdio target (default for plugin marketplace & uvx-style usage)
# ========================
FROM runtime AS stdio
ENV MCP_TRANSPORT=stdio
ENTRYPOINT ["python", "-m", "better_code_review_graph"]

# ========================
# Stage 3b: http target (multi-user remote daemon)
# ========================
FROM runtime AS http
ENV MCP_TRANSPORT=http \
    MCP_PORT=8080
EXPOSE 8080
ENTRYPOINT ["better-code-review-graph", "serve"]
