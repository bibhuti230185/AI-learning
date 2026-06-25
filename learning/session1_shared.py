"""Shared utilities for LangChain Session 1 scripts."""

import os
import sys
import warnings
from pathlib import Path

from langchain_openai import ChatOpenAI


BASE_URL = "https://api.siemens.com/llm/v1"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_MAX_TOKENS = 4096


AVAILABLE_MODELS = {
    "deepseek-v4-flash": {
        "usage": "chat, completions",
        "max_tokens": 1048576,
        "license": "MIT",
    },
    "qwen-3.6-27b": {
        "usage": "chat, completions",
        "max_tokens": 262144,
        "license": "Apache-2.0",
    },
    "ministral-3-14b-instruct-2512": {
        "usage": "chat, completions",
        "max_tokens": 256000,
        "license": "Apache-2.0",
    },
    "qwen3-embedding-0.6b": {
        "usage": "embeddings",
        "max_tokens": 32768,
        "license": "Apache-2.0",
    },
    "qwen3-embedding-8b": {
        "usage": "embeddings",
        "max_tokens": 32768,
        "license": "Apache-2.0",
    },
    "qwen3-reranker-0.6b": {
        "usage": "reranking",
        "max_tokens": 32768,
        "license": "Apache-2.0",
    },
    "bge-m3": {
        "usage": "embeddings",
        "max_tokens": 8000,
        "license": "MIT",
    },
}


def setup_runtime(script_file: str) -> None:
    """Set local runtime defaults and load env files before model creation."""

    def warn(*args, **kwargs):
        pass

    warnings.warn = warn
    warnings.filterwarnings("ignore")
    os.environ["ANONYMIZED_TELEMETRY"] = "False"
    load_env_files(script_file)


def load_env_files(script_file: str) -> None:
    """Load simple KEY=VALUE pairs from common workspace .env files."""
    script_dir = Path(script_file).resolve().parent
    candidate_files = [
        script_dir / ".env",
        script_dir.parent / ".env",
        script_dir.parent / ".github" / ".env",
    ]

    for env_file in candidate_files:
        if not env_file.exists():
            continue

        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


def get_api_key_or_exit() -> str:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        return api_key

    print("⚠️  WARNING: OPENAI_API_KEY environment variable not set!")
    print("   Please set it: $env:OPENAI_API_KEY='your-api-key-here'")
    print("   The examples below will fail without a valid API key.")
    print("\n❌ Cannot initialize LLM - API key not set")
    print("   Set your API key with: $env:OPENAI_API_KEY='your-key-here'")
    print("   Then run this file again.\n")
    sys.exit(1)


def get_available_chat_models() -> list[str]:
    return [
        model_name
        for model_name, model_meta in AVAILABLE_MODELS.items()
        if "chat" in model_meta["usage"]
    ]


def select_primary_secondary_models(chat_models: list[str]) -> tuple[str, str]:
    default_primary_index = 0
    default_secondary_index = 2 if len(chat_models) > 2 else 1

    primary = os.getenv("MODEL_PRIMARY", chat_models[default_primary_index])
    secondary = os.getenv("MODEL_SECONDARY", chat_models[default_secondary_index])

    if primary not in chat_models:
        raise ValueError(
            f"MODEL_PRIMARY='{primary}' is not in available chat models: {chat_models}"
        )

    if secondary not in chat_models:
        raise ValueError(
            f"MODEL_SECONDARY='{secondary}' is not in available chat models: {chat_models}"
        )

    if primary == secondary:
        for candidate in chat_models:
            if candidate != primary:
                secondary = candidate
                break

    return primary, secondary


def build_chat_model(
    model_name: str,
    api_key: str,
    temperature: float,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = 30,
) -> ChatOpenAI:
    """Create a chat model client with shared Siemens endpoint settings."""
    return ChatOpenAI(
        model=model_name,
        base_url=BASE_URL,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
