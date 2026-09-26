"""Cấu hình cho backend embedding cục bộ của CRG."""

import os
from pathlib import Path
from typing import Any

from hull_core.config.models import ModelCell, resolve_model_cells
from hull_core.config.settings import HullSettings, load_settings
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Các trường LOCAL_* cho model embedding và reranking người dùng tự cung cấp.

    Reranker cục bộ chỉ được bật khi ``local_rerank_model`` khác rỗng. Model
    embedding ngoài registry phải khai báo dimension hoặc cung cấp
    ``fastretrieval-manifest.json`` trong thư mục artifact.
    """

    local_embedding_model: str = ""
    local_rerank_model: str = ""
    local_embedding_dim: int = 0
    local_embedding_model_file: str = "onnx/model.onnx"
    local_embedding_pooling: str = "MEAN"
    local_embedding_normalize: bool = True

    model_config = {"env_prefix": "", "case_sensitive": False}

    @model_validator(mode="before")
    @classmethod
    def _empty_plugin_values_use_defaults(cls, values: Any) -> Any:
        """Treat unset optional plugin interpolation values as missing."""
        if not isinstance(values, dict):
            return values
        values = values.copy()
        for field in (
            "local_embedding_model",
            "local_rerank_model",
            "local_embedding_dim",
            "local_embedding_model_file",
            "local_embedding_pooling",
            "local_embedding_normalize",
        ):
            if values.get(field) == "":
                values.pop(field)
        return values


settings = Settings()


# ---------------------------------------------------------------------------
# Hull-core instance config (WP2 de-host, spec 2026-09-26 §3/§4)
# ---------------------------------------------------------------------------


def crg_config_dir() -> Path:
    """Host-owned instance config directory: ``$CRG_CONFIG_DIR`` or ``~/.crg``.

    Same schema as hull's ``config.toml``: ``[server]`` (bind, auth mode,
    users file) + per-task ``[models.<task>]`` provider cells. Keys live
    here (or arrive via ``HULL_<TASK>_API_KEY`` env) — they are host-only
    material and never end-user supplied (spec §4 Q1, BYOK cut).
    """
    return Path(os.environ.get("CRG_CONFIG_DIR") or Path.home() / ".crg")


def load_instance_settings() -> HullSettings:
    """Load the crg instance config through hull-core's loader."""
    return load_settings(crg_config_dir())


def resolve_cells(
    settings: HullSettings | None = None, env: dict[str, str] | None = None
) -> dict[str, ModelCell]:
    """Resolve the per-task provider cells (embed / rerank / chat / jev_score)."""
    settings = settings if settings is not None else load_instance_settings()
    return resolve_model_cells(settings.models, env=env)
