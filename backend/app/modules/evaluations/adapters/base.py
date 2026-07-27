from typing import Protocol

from app.modules.evaluations.contracts import EvaluationRequest
from app.modules.evaluations.schemas import EvaluationResult


class EvaluationAdapter(Protocol):
    def evaluate(self, request: EvaluationRequest) -> EvaluationResult: ...
