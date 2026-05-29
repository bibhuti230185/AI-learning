# Copyright Siemens AG, 2026.
# Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0

"""Unit tests for the model abstraction layer."""

import pytest

from sw360_review_agent.config import ModelConfig
from sw360_review_agent.models import (
    LLMMessage,
    LLMResponse,
    create_provider,
    parse_json_response,
    register_provider,
    LLMProvider,
)


class TestParseJsonResponse:
    def test_parses_clean_json_array(self):
        response = LLMResponse(
            content='[{"line": 10, "rule": "R01"}]',
            model="test",
        )
        result = parse_json_response(response)
        assert len(result) == 1
        assert result[0]["line"] == 10

    def test_parses_json_with_code_fence(self):
        response = LLMResponse(
            content='```json\n[{"line": 5}]\n```',
            model="test",
        )
        result = parse_json_response(response)
        assert len(result) == 1
        assert result[0]["line"] == 5

    def test_parses_empty_array(self):
        response = LLMResponse(content="[]", model="test")
        result = parse_json_response(response)
        assert result == []

    def test_parses_single_object_as_list(self):
        response = LLMResponse(
            content='{"line": 1, "message": "test"}',
            model="test",
        )
        result = parse_json_response(response)
        assert len(result) == 1

    def test_handles_malformed_json(self):
        response = LLMResponse(content="not json at all", model="test")
        result = parse_json_response(response)
        assert result == []


class TestProviderFactory:
    def test_unknown_provider_raises(self):
        config = ModelConfig(provider="nonexistent")
        with pytest.raises(ValueError, match="Unknown model provider"):
            create_provider(config)

    def test_register_custom_provider(self):
        class MockProvider(LLMProvider):
            def __init__(self, config):
                pass

            async def generate(self, messages, **kwargs):
                return LLMResponse(content="mock", model="mock")

            async def close(self):
                pass

        register_provider("mock_test", MockProvider)
        config = ModelConfig(provider="mock_test", model_name="test-model")
        provider = create_provider(config)
        assert isinstance(provider, MockProvider)
