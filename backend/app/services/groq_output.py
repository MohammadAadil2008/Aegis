"""Bounded Groq requests and safe diagnostics shared by both optional AI paths."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from pydantic import ValidationError


class IncompleteGroqResponse(ValueError):
    pass


def output_options(model: str, name: str, schema: dict[str, Any]) -> dict[str, Any]:
    if model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
        strict_schema = deepcopy(schema)

        def close_objects(value: Any) -> None:
            if isinstance(value, dict):
                if value.get("type") == "object":
                    value["additionalProperties"] = False
                    value["required"] = list(value.get("properties", {}))
                for child in value.values():
                    close_objects(child)
            elif isinstance(value, list):
                for child in value:
                    close_objects(child)

        close_objects(strict_schema)
        return {
            "response_format": {"type": "json_schema", "json_schema": {
                "name": name, "strict": True, "schema": strict_schema,
            }},
            # GPT-OSS shares its output budget with reasoning. Keep this bounded
            # for evidence summarization and reserve enough room for final JSON.
            "reasoning_effort": "low",
        }
    return {"response_format": {"type": "json_object"}}


def completion_content(completion: Any) -> str:
    if not completion.choices:
        raise IncompleteGroqResponse("empty_choices")
    choice = completion.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise IncompleteGroqResponse("incomplete_output")
    return choice.message.content


def failure_code(error: Exception) -> str:
    # Never expose exception text: SDK errors can contain request data.
    if isinstance(error, IncompleteGroqResponse):
        return "incomplete_output"
    if isinstance(error, (ValidationError, ValueError, json.JSONDecodeError)):
        return "invalid_output"
    status = getattr(error, "status_code", None)
    if status in {401, 403}:
        return "provider_access"
    if status == 429:
        return "rate_limited"
    if status in {400, 404, 422}:
        return "provider_configuration"
    if isinstance(error, TimeoutError) or type(error).__name__ == "APITimeoutError":
        return "provider_timeout"
    return "provider_unavailable"


FAILURE_MESSAGES = {
    "not_configured": "Groq Incident Commander is disabled or not configured.",
    "incomplete_output": "Groq did not finish the response; the incomplete answer was discarded.",
    "invalid_output": "Groq output did not match the required evidence and assessment fields.",
    "provider_access": "Groq rejected access. Check the server-side key and project permissions.",
    "rate_limited": "Groq is temporarily rate-limited. Try again after a short pause.",
    "provider_configuration": "Groq rejected the request configuration. Check the configured model and server logs.",
    "provider_timeout": "Groq did not respond within the allowed time.",
    "provider_unavailable": "Groq is temporarily unavailable.",
}
