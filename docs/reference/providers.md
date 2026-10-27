# Providers and messages

These types form the normalized provider boundary. See [providers](../guides/providers.md) for a live Gemini example and a custom-provider skeleton.

## Provider

Implement a `name`, `capabilities`, and async `generate`. All tool results must be matched to their original call IDs. Unsupported or malformed responses should raise an appropriate provider error.

::: stagify.Provider

::: stagify.ProviderCapabilities

## Bundled adapters

`GoogleProvider` is also importable from `stagify.providers.google`. It uses Gemini Interactions, replays opaque steps, and closes owned clients through `aclose` or its async context manager. An injected client stays caller-owned.

::: stagify.providers.interactions.GoogleProvider
    options:
      members: [__init__, generate, aclose]

## Unit-test helper

ScriptedProvider accepts an iterable of responses/exceptions or a sync/async response callback. It records incoming requests in `requests`. Exhausting a response iterable raises `ProviderOutputError`. It makes no model calls itself.

::: stagify.testing.ScriptedProvider
    options:
      members: [__init__, generate]

## Request and response types

`ModelRequest.instructions` is separate from messages. Tools contain JSON Schema parameters. `max_output_tokens` is the requested response allocation.

::: stagify.ModelRequest

`ModelResponse.calls` contains requested tool calls. `status` accepts `completed`, `requires_action`, `failed`, or `incomplete`; the runtime rejects failed/incomplete responses. `requires_action` needs at least one call. Missing usage stays unknown. `native` is adapter-owned replay content, not a portable transcript format.

::: stagify.ModelResponse

`Message` supports `user`, `assistant`, and `tool` roles. Tool results carry `call_id` and `name`; assistant messages may contain calls and adapter-native replay data.

::: stagify.Message

::: stagify.ToolCall

::: stagify.ToolSpec
