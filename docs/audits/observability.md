# Observability verification

Date: 8 September 2026.

The Page 47 AgentCore runtime is currently `READY` in `eu-west-2`:

```text
runtime: page47_review
arn: arn:aws:bedrock-agentcore:eu-west-2:591697681173:runtime/page47_review-X5IwXt4Y7h
artifact: page47-review/agentcore-deployment-isolated.zip
package_sha256: 5b1a097b29080237954b732fe4f92295478e2cb77d4b30fb6c9cee40a7bb6b22
environment: UNIFIED_TRACES_DESTINATION_ENABLED=true
```

The artifact pins the `mcp` and `pypdf` versions used by the last known-good
runtime and constructs a fresh Strands graph for each investigation. The
runtime entrypoint also serializes work within a warm process because Strands
agents reject overlapping calls.

## Controlled review

One stored Seattle matter (`17394`) was submitted after deployment:

```text
POST /api/cities/Seattle%2C%20Washington/matters/17394/investigate
HTTP 200
run_id: 8ff0cc0b64d64d5c817a7275b0ad30c0
finding_id: seattle,-washington-17394
state: clearer
publish: true
supported_count: 18
rejected_count: 0
```

The saved graph reports five completed nodes, zero failed nodes, five
executions, and 52.851 seconds of graph execution time. The runtime log group
`/aws/bedrock-agentcore/runtimes/page47_review-X5IwXt4Y7h-DEFAULT` recorded
`Invocation completed successfully (53.241s)` for the same request. The saved
finding retains primary evidence links and no placeholder observation IDs.

Earlier attempts with the rebuilt artifact exposed a concurrency/timeout
failure in the `substance` node. Those attempts remain recorded as failed runs;
they were not presented as findings. The isolated graph and dependency pins
were deployed before the successful check above.

## Trace boundary

The account-level X-Ray check still reports the `XRay` trace destination rather
than CloudWatch Logs. No usable trace identifier has been retained, so unified
trace search is not complete. An administrator still needs to enable the
CloudWatch Logs Transaction Search destination and its resource policy before
the trace gate can be closed. Runtime `READY` and a successful review are not
being treated as proof that a trace is searchable.

At 2026-09-08T10:15:58Z, `GetTraceSummaries` returned zero summaries in both
`eu-west-2` and `eu-north-1` for the recent review window.

SES parameters, CloudWatch agent delivery for the Lightsail service, the missed-
run alarm, and the controlled email receipt remain separate launch gates.
