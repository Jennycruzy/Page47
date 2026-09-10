# Observability verification

Date: 9 September 2026.

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

## Post-activation review

After Transaction Search became active, the same stored Seattle matter (`17394`)
was submitted again on 9 September 2026. The VPS saved the following completed
run:

```text
run_id: e44ba7e6a0e641759896c6c28e79a35d
started_at: 2026-09-09T06:52:33.520535+00:00
finished_at: 2026-09-09T06:52:58.723787+00:00
status: completed
graph: 5 completed nodes, 0 failed nodes, 5 executions
execution_time: 53.973 seconds
finding: seattle,-washington-17394, clearer, publish=true, 18 supported
```

The corresponding AgentCore runtime log recorded a successful invocation with
request ID `9dcf6075-7f1e-40d8-94dc-2cbf82fc7e5d` and session ID
`c3bce38645594aaaae9fec76a81a3e623a059bf847a74fa1b85a7cfba7d00994`.
The Default X-Ray rule was at its normal 1% target during this request, and an
exact-window `GetTraceSummaries` query returned no trace. A temporary 100%
target was applied at 06:59:35 UTC for one retry, but it produced no new saved
run; the target was restored to 1% at 07:03:48 UTC. No searchable trace ID has
been retained, so the trace gate remains open.

## 10 September trace retry

Transaction Search was retried with the Default indexing target temporarily
raised to 100% and then restored to 1% immediately after the invocation. The
live public host returned another successful application response for matter
`17394`:

```text
run_id: 97e02cd94e6543e38b5c44875d4b6188
finding: seattle,-washington-17394, cannot_determine, publish=false
runtime_request_id: 0bfee1c8-5496-4381-b4c1-736e903e837f
runtime_session_id: 968f46201cf048bf812e9c042e24b50bacd9e5b40ffb48afa38522ebd7e42316
runtime_log: Invocation completed successfully (20.579s)
trace_query_window: 2026-09-10T15:08:45Z through 2026-09-10T15:10:40Z
```

The exact-window `GetTraceSummaries` query still returned zero summaries, and
the runtime log search found no trace identifier. The indexing target was
verified back at 1% at `2026-09-10T15:10:41Z`. This retry confirms another
successful managed-runtime invocation, not a searchable OpenTelemetry trace;
the trace gate remains open.

## 9 September AWS setup

The `page47-vps-deploy` identity in account `591697681173` now has the
customer inline policy `Page47OperationsPermissions`. The public URL and SES
sender parameters are present in `eu-west-2`, and the sender identity is
verified. SES reports `SendingEnabled=true` and
`ProductionAccessEnabled=false`. A temporary verified watch sent one
controlled review through the application, and mailbox receipt was confirmed.

Transaction Search setup was completed for the AgentCore region
`eu-west-2`. The account resource policy `Page47TransactionSearchXRayAccess`
was created, `GetTraceSegmentDestination` now reports:

```text
Destination: CloudWatchLogs
Status: ACTIVE
```

The default X-Ray indexing rule is back at a 1% sampling target after the
temporary validation setting. A post-activation review was saved as run
`e44ba7e6a0e641759896c6c28e79a35d`, but its 1% sampling window returned no
trace summary and no trace identifier has been retained, so the trace gate
remains open. The earlier `GetTraceSummaries` check at 2026-09-08T10:15:58Z
returned zero summaries in both `eu-west-2` and `eu-north-1` for its recent
review window.

## CloudWatch host boundary

The official CloudWatch agent package `1.300072.0b1766` was installed on the
host and the checked-in configuration passed validation. It was then stopped
for this handoff because the agent uses the host's instance role rather than
the `page47-vps-deploy` user. Its log shows denied `logs:CreateLogStream`,
`logs:PutLogEvents`, and `logs:DescribeLogGroups` calls for
`AmazonLightsailInstanceRole`.

The SSH shell identifies as account `591697681173`, but EC2 instance metadata
identifies the host as account `000029643808`, instance
`i-01de6496943e7a94f`, with role `AmazonLightsailInstanceRole`. The
`/page47` groups are therefore not visible through the deployment user's
account, and the host role must be reconciled or granted cross-account log
access before the agent and missed-run alarm can be configured. Runtime
`READY`, a successful review, and an active Transaction Search destination are
not being treated as proof that a searchable trace or monitoring pipeline
works.

CloudWatch log delivery and the missed-run alarm, one post-activation
searchable trace, and the comparison outputs remain separate launch gates.
