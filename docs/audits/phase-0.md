# Phase 0 audit — preflight

Status: complete with recorded blockers. No city-specific behavior uses an unverified value.

## Evidence

- `docs/preflight.json` was captured on `2026-09-04T16:43:21.622317Z` UTC from the Lightsail host using Python `3.12.3` and its attached IAM role.
- `docs/evidence/preflight/index.json` records `181` final HTTP attempts, their status, capture time, SHA-256, storage key, and selected response headers. No response in this run returned an ETag; the missing header is recorded by the absence of `etag` in each header map.
- `config/preflight.json` contains the candidate client list, bounded request settings, AWS regions, and cost inputs.
- `scripts/preflight.py` is the reproducible entry point. The live command was:

  ```text
  /home/ubuntu/page47-preflight/.venv/bin/python /home/ubuntu/page47-preflight/scripts/preflight.py --config /home/ubuntu/page47-preflight/config/preflight.json --output /home/ubuntu/page47-preflight/docs/preflight-current.json
  ```

- The official API help page was read during investigation and cached as a response. It specifies integer `1` for the event-detail switches, which corrected the first probe before the final run.

## Chosen city

Seattle, Washington is the initial city because its live response met the required structural checks and its oldest sampled event was dated `2015-02-03`. The final run found eight clients meeting the same checks: Seattle, Sacramento, Denver, Boston, Oakland, Phoenix, Plano, and Saint Paul.

Seattle's final sample contained:

- `20` events, with `9` of the recorded event fields populated at least once.
- `73` event items, with all `15` required event-item fields populated at least once.
- `66` attachments, with all `6` required attachment fields populated at least once.
- Eight bounded requests without a `429` response or a `Retry-After` header.

The oldest date above is an observed sample boundary, not a claim that every earlier record exists. Exact backfill depth belongs to the record-history work.

## AWS result

- The instance has `boto3 1.43.88`, `bedrock-agentcore 1.22.0`, and Python `3.12.3`.
- The Bedrock service model is present, but `ListFoundationModels` returned `AccessDeniedException` in every requested region, so no model ID was recorded or assumed.
- Both AgentCore service models are present. The SDK's region metadata is empty for the control service, so the probe calls the endpoint directly; every requested region returned `AccessDeniedException` for `ListAgentRuntimes`. This proves the endpoint was reached, but the role cannot list runtimes yet.
- The fixed fourteen-day estimate is `$3.3203`: `$3.2667` for the `$7/month` Lightsail bundle and `$0.0537` for the configured storage estimate. Model cost remains uncomputed because model IDs and pricing were not verified.

## Gaps

- The API returned no ETag headers during this run. The later snapshotter must still store the observed header value, including an explicit absent value, and use content hashes for change detection.
- Terms-of-use review for each city remains manual. The API and public record URLs were reachable, but the probe did not infer permission from reachability.
- The local Mac has Python `3.11.9`; the required Python `3.12` runtime is available on Lightsail. Local development needs a Python `3.12` environment before strict checks run locally.
- Some candidate client slugs returned HTTP `500`. They remain recorded as unavailable and were not silently removed.

## Blockers

Before any model-dependent work or deployment, the Lightsail IAM role needs permission to list and invoke the selected Bedrock models and to inspect and deploy AgentCore runtimes. The selected city's terms also need a human review.

## Exit criteria

The chosen city, sampled record depth, populated fields, AWS model-list result, AgentCore result, bounded request behavior, and cost arithmetic are all printed in `docs/preflight.json`. The remaining blockers are explicit, so this work stops here until AWS access and terms review are resolved.
