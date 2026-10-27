# Policies and limits

All policy containers and individual transformations default to disabled. See [context management](../guides/context-management.md) for precedence and [errors and limits](../guides/errors.md) for enforcement.

## ContextPolicies

`protected_fields` must identify selected input fields. All selected stage inputs are retained exactly in this release. `memory_keys` selects working-state entries for the request view when policies are enabled; it is not an access-control boundary.

::: stagify.ContextPolicies

## ArtifactOffload

`max_chars` bounds the serialized projected tool-message view and model-facing evidence reads. It must be at least 256. Original outputs stay in memory.

::: stagify.ArtifactOffload

## Summarize

Fractions must satisfy `0 < target_fraction < trigger_fraction <= 1`. `recent_batches` is nonnegative. Summary input/output allocations must be positive. Summary requests count toward provider-call limits and usage.

::: stagify.Summarize

## RunLimits

Call limits apply to the whole run tree. Input/output allocations apply per provider request. `max_model_retries=2` permits up to three attempts for an individual request, subject to all call caps. Root stage depth is counted in the depth limit; the default 5 allows the root plus four child levels. Positive allocations, nonnegative retry settings, and a positive optional timeout are required.

::: stagify.RunLimits
