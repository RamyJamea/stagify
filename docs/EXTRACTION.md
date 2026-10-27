# Existing scripts retained

The Google provider uses the **Gemini Interactions API**, through the original
GeminiNLP implementation extracted from the application's shared NLP scripts.
It does not use Generate Content.

The following source files are retained without rewriting their implementation:

| Original application file | Stagify file |
| --- | --- |
| shared/nlp/interface.py | src/stagify/nlp/interface.py |
| shared/nlp/schemas.py | src/stagify/nlp/schemas.py |
| shared/nlp/providers/gemini.py | src/stagify/nlp/providers/gemini.py |

The Gemini source file SHA-256 at extraction was
`A88FFC92573BA668DF535997331D72BB790452726DB49EC53B182EB726A21B9B`.
The copied file had the same hash.

The adapter in src/stagify/providers/interactions.py translates Stagify request
and result envelopes to those existing contracts. It retains:

- interactions.create with store=False and stream=False.
- Existing GenConfig defaults, range validation, and generation parameters.
- All opaque replay steps, original function-call IDs, and function-result encoding.
- Explicitly disabled SDK retries.
- Retry-After and Google RetryInfo delay handling.
- Permanent daily-quota handling and malformed-tool-output classification.
- Input, output, cached, thought, and tool-use token counters.

The original provider regression tests were carried into
tests/test_interactions_extracted.py with package import paths changed and the
application-specific completion enum replaced by its existing string value.
Bridge tests also verify the actual outgoing Interactions request.

New runtime code adds the requested stage context policies, nested-stage
accounting, verbose logs, evidence memory, and result envelopes. Business tools,
ERP behavior, datasets, and the original application are not modified or included.
