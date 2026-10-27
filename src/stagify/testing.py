"""A deterministic provider useful for examples and application contract tests."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any

from .contracts import ModelRequest, ModelResponse, ProviderCapabilities
from .errors import ProviderOutputError


class ScriptedProvider:
    name = "scripted"

    def __init__(
        self,
        responses: Iterable[ModelResponse | Exception] | Callable[..., Any],
        *,
        capabilities: ProviderCapabilities | None = None,
    ):
        self.capabilities = capabilities or ProviderCapabilities()
        self.requests: list[ModelRequest] = []
        self._handler = responses if callable(responses) else None
        self._responses = None if self._handler else iter(responses)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._handler is not None:
            response = self._handler(request)
            response = await response if inspect.isawaitable(response) else response
        else:
            try:
                response = next(self._responses)
            except StopIteration as exc:
                raise ProviderOutputError("Scripted provider has no response left") from exc
        if isinstance(response, Exception):
            raise response
        if not isinstance(response, ModelResponse):
            raise ProviderOutputError("Scripted provider must return ModelResponse")
        return response
