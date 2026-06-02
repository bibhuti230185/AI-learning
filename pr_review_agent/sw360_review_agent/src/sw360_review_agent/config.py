# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Configuration management for the PR Review Agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ModelConfig(BaseModel):
    """LLM model provider configuration."""

    provider: str = "anthropic"
    model_name: str = "claude-sonnet-4-20250514"
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096


class GitHubConfig(BaseModel):
    """GitHub integration configuration."""

    token: str = ""
    webhook_secret: str = ""
    repository: str = "eclipse-sw360/sw360"


class Layer1Config(BaseModel):
    """Layer 1 deterministic rules configuration."""

    enabled: bool = True
    rules: list[str] = Field(
        default_factory=lambda: ["R01", "R02", "R03", "R04", "R05", "R06"]
    )


class VectorStoreConfig(BaseModel):
    """Vector store configuration for RAG."""

    provider: str = "chromadb"
    host: str | None = None
    port: int | None = None
    collection_name: str = "sw360_codebase"
    embedding_model: str = "all-MiniLM-L6-v2"


class Layer2Config(BaseModel):
    """Layer 2 RAG + LLM review configuration."""

    enabled: bool = True
    checks: list[str] = Field(
        default_factory=lambda: ["L01", "L02", "L03", "L04", "L05", "L06",
                                 "L07", "L08", "L09", "L10", "L11", "L12"]
    )
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)


class ReviewConfig(BaseModel):
    """Review posting configuration."""

    default_verdict: str = "COMMENT"
    block_on_errors: bool = False
    max_comments: int = 50
    min_confidence: float = 0.7


class ServerConfig(BaseModel):
    """Webhook server configuration."""

    host: str = "0.0.0.0"
    port: int = 8090


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"


class AgentConfig(BaseSettings):
    """Root configuration for the PR Review Agent."""

    model: ModelConfig = Field(default_factory=ModelConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    layer1: Layer1Config = Field(default_factory=Layer1Config)
    layer2: Layer2Config = Field(default_factory=Layer2Config)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    project_rules_dir: str | None = None  # Path to project_rules/ directory


def _resolve_env_vars(data: Any) -> Any:
    """Recursively resolve ${ENV_VAR} placeholders in config values."""
    if isinstance(data, str) and data.startswith("${") and data.endswith("}"):
        env_var = data[2:-1]
        return os.environ.get(env_var, "")
    elif isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_env_vars(item) for item in data]
    return data


def load_config(config_path: str | Path | None = None) -> AgentConfig:
    """Load configuration from YAML file with environment variable resolution.

    Args:
        config_path: Path to config YAML file. Defaults to config.yaml in CWD.

    Returns:
        Validated AgentConfig instance.
    """
    if config_path is None:
        config_path = Path.cwd() / "config.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path) as f:
            raw_config = yaml.safe_load(f) or {}
        resolved = _resolve_env_vars(raw_config)
        return AgentConfig(**resolved)

    # Fall back to environment variables / defaults
    return AgentConfig()
