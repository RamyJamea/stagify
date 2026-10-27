from typing import Protocol

from ..contracts import ModelRequest, ModelResponse, ProviderCapabilities


class Provider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def generate(self, request: ModelRequest) -> ModelResponse: ...
