import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.modules.evaluations.contracts import (
    EvaluationProviderResult,
    EvaluationRequest,
)
from app.modules.evaluations.prompts import build_messages
from app.modules.evaluations.schemas import EvaluationResult


class EvaluationProviderError(Exception):
    pass


class DeepSeekEvaluationAdapter:
    def __init__(
        self,
        *,
        client: Any,
        model: str,
        timeout_seconds: int,
        max_retries: int,
        sleep: Callable[[float], None],
    ) -> None:
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep

    @classmethod
    def from_settings(cls, settings: Any, *, model_name: str | None = None) -> "DeepSeekEvaluationAdapter":
        from openai import OpenAI

        if not settings.deepseek_api_key:
            raise ValueError("deepseek_api_key_missing")
        import time

        return cls(
            client=OpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            ),
            model=model_name or settings.deepseek_model,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_retries=settings.deepseek_max_retries,
            sleep=time.sleep,
        )

    def evaluate(self, request: EvaluationRequest) -> EvaluationProviderResult:
        retry_count = 0
        while True:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=build_messages(request),
                    response_format={"type": "json_object"},
                    stream=False,
                    timeout=self.timeout_seconds,
                )
                content = response.choices[0].message.content
                if not content:
                    raise _RetryableResponseError
                result = EvaluationResult.model_validate(json.loads(content))
                self._validate_rule_codes(result, request.rule_snapshot)
                usage = getattr(response, "usage", None)
                return EvaluationProviderResult(
                    result=result,
                    request_id=getattr(response, "id", None),
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    retry_count=retry_count,
                )
            except Exception as error:
                code, retryable = self._classify_error(error)
                if not retryable or retry_count >= self.max_retries:
                    raise EvaluationProviderError(code) from None
                self.sleep(float(2**retry_count))
                retry_count += 1

    @staticmethod
    def _validate_rule_codes(
        result: EvaluationResult, rule_snapshot: dict[str, Any]
    ) -> None:
        hard_codes = {
            str(rule["code"])
            for rule in rule_snapshot.get("hard_rules", [])
            if bool(rule.get("enabled", True))
        }
        weighted_codes = {
            str(rule["code"])
            for rule in rule_snapshot.get("weighted_rules", [])
            if bool(rule.get("enabled", True))
        }
        for entity in result.entities:
            if {item.rule_code for item in entity.hard_rule_results} != hard_codes:
                raise _RetryableResponseError
            if {item.rule_code for item in entity.weighted_rule_results} != weighted_codes:
                raise _RetryableResponseError

    @staticmethod
    def _classify_error(error: Exception) -> tuple[str, bool]:
        status_code = getattr(error, "status_code", None)
        stable_codes = {
            400: "bad_request",
            401: "authentication",
            402: "payment_required",
            422: "unprocessable_request",
        }
        if status_code in stable_codes:
            return stable_codes[status_code], False
        if status_code in {429, 500, 503}:
            return "provider_unavailable", True
        if isinstance(error, (TimeoutError, ConnectionError)):
            return "provider_unavailable", True
        if isinstance(error, (json.JSONDecodeError, ValidationError, _RetryableResponseError)):
            return "invalid_response", True
        return "provider_error", False


class _RetryableResponseError(Exception):
    pass
