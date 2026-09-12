# AWS inventory

This document records the live AWS architecture, operational configuration, and
external dependencies for the public Page 47 service.

| Service or resource | Job here | Current state | What breaks without it |
|---|---|---|---|
| Public host, previously recorded as Lightsail (`eu-north-1`) | Keep the collector, record store, and public service running continuously. | The host at `13.62.181.128` is reachable and the collector/service remain healthy. Current EC2 metadata reports a `t3.micro` in account `000029643808`, instance `i-01de6496943e7a94f`, while the Page 47 deployment credentials belong to account `591697681173`; the hosting/account classification must be reconciled. | Scheduled public-record captures stop, and the service loses the forward-looking record that cannot be reconstructed later. |
| Local host disk | Hold the active working copies of immutable API responses, agenda PDFs, attachment PDFs, and SQLite records. | Seattle and Denver captures and records are on the host under `runtime/`. Denver's follow-up now has HTTP 200 as the latest response for all 473 attachment IDs; the four earlier HTTP 404 responses remain preserved in the append-only evidence manifest. The current Denver PDF reader has 270 results: 259 candidates, 10 with no configured reference, and 1 unreadable PDF. The manifest has a chained integrity record. | The host remains the active working store; recovery uses the verified S3 copy if the host is lost. |
| Amazon S3 evidence backup | Keep a recoverable off-host copy of the exact bytes and metadata Page 47 observed. | Bucket `page47-evidence-591697681173-eu-west-2-an` is private, versioned, and encrypted with SSE-S3. The scheduled collector is configured to back up Seattle under `cities/seattle/` and Denver under `cities/denver/`. The first backup uploaded 2,047 Seattle objects and 1,313 Denver objects; a repeat run uploaded zero and skipped 3,360 unchanged objects. | If the backup schedule fails, new observations remain only on the host until the failure is corrected. |
| Amazon Bedrock in `eu-west-2` | Run text triage, page reading, and the five review roles. | Live model discovery on 6 September 2026 returned the configured IDs. `amazon.nova-micro-v1:0` is the text route; `amazon.nova-lite-v1:0` is the page-image route. The choices are recorded in `config/models.yaml` and `docs/model-verification.json`. | The application cannot read attachment pages or run a review. |
| AgentCore Runtime | Host the bursty five-role review graph separately from the always-on Lightsail service. | Runtime `page47_review` is `READY` in `eu-west-2`, version 17. ARN: `arn:aws:bedrock-agentcore:eu-west-2:591697681173:runtime/page47_review-X5IwXt4Y7h`. The ADOT auto-instrumented package is 59.2 MB compressed and 162.3 MB expanded; version 17 includes the explicit untrusted-document prompt guard. The Lightsail client previously invoked stored Seattle matter `17394`; run `dea939b750ec412ca0921b4a31422037` completed and saved a `clearer` result. | The graph cannot run as the managed AWS workload or save a managed-runtime review. |
| Systems Manager Parameter Store | Hold the SES sender address, public service URL, AgentCore execution-role ARN, and managed runtime ARN outside source control. | Delivery code expects `/page47/email/sender` and `/page47/web/public-url`. `/page47/agentcore/execution-role-arn` contains the Page 47 role ARN, deployment wrote `/page47/agentcore/runtime-arn` with the `page47_review` runtime ARN, and `/page47/web/public-url` is present with `https://page47.xcover.online/`. `/page47/email/sender` is present and resolves to a verified SES email identity; no recipient parameter is stored. | Email or managed review deployment fails loudly instead of exposing a secret, using an unknown sender, or silently falling back to an unconfigured runtime. |
| Amazon SESv2 | Send one review email to each matching watch. | The sender and recipient code is implemented, duplicate sends are recorded, and each message includes the private watch-management link. The 10 September 2026 VPS check found the sender parameter present, `SendingEnabled=true`, `ProductionAccessEnabled=false`, and `VerifiedForSendingStatus=true`. One temporary verified watch produced a `sent` notification with a provider `MessageId`; the watch was then deactivated. Mailbox receipt was confirmed while SES remains in sandbox mode. | Residents do not receive a review without logging into the console. |
| Page 47 console service | Serve the resident console and API from the public host. | `page47-web.service` is enabled and healthy on `127.0.0.1:8090`. DNS, the `page47.xcover.online` certificate, dedicated Nginx host, HTTP redirect, HTTPS health, root response, renewal dry-run, root-relative links, legacy `/page47` redirect, public URL parameter, and controlled SES application delivery are verified. | Ongoing resident delivery still needs operational monitoring. |
| CloudWatch Logs | Keep collector and service failures visible. | The official agent package `1.300072.0b1766` is active and the checked-in configuration passed validation. It reads the host's existing deployment credentials and assumes the dedicated `Page47CloudWatchAgent` role in account `591697681173`; both `/page47/lightsail/snapshotter` and `/page47/lightsail/web` exist in `eu-north-1`, with active streams and 14-day retention. The non-customer `AmazonLightsailInstanceRole` reported by host metadata is not used by the agent. | A stopped collector could lose evidence silently. |
| CloudWatch alarm | Alert when the scheduled collector has not completed. | The collector emits `Page47SnapshotRunSuccess` only after all city capture, record application, document reading, placement, and delivery commands finish. Its lock holds the file descriptor in the parent shell, so a failed command cannot be hidden by the lock wrapper. `scripts/configure_cloudwatch.py` created the `Page47SnapshotRunSuccess` metric filter and the two-hour `Page47-Snapshotter-MissedRun` alarm from `config/observability.yaml`; the alarm is currently `INSUFFICIENT_DATA` while it gathers its first evaluation windows. | A missed run would not be noticed until the overwritten city record was already gone. |
| OpenTelemetry | Show one review from request through the five roles. | Transaction Search is configured in `eu-west-2`; the X-Ray destination is `CloudWatchLogs/ACTIVE`, the default indexing target is 1%, and runtime version 16 uses the ADOT auto-instrumented entrypoint. Run `dea939b750ec412ca0921b4a31422037` produced searchable trace `6aa2f721063b98043b31e7b86ca47cfb`; the runtime `spans` stream contains 51 events and X-Ray returned one complete HTTP 200 summary. | The AWS execution path is now demonstrated with a retained searchable trace. |

## Launch runbook

The exact DNS, certificate, root-path rollout, SES, CloudWatch, trace, and
evaluation gates are maintained in [`docs/LAUNCH.md`](LAUNCH.md). It preserves
the existing `/page47` route until the subdomain has passed its health checks.

## Host identity boundary (9 September 2026)

The AWS CLI on the host, when run with the Page 47 deployment credentials,
identifies as `arn:aws:iam::591697681173:user/page47-vps-deploy`. The host's
EC2 metadata identifies the machine separately as account `000029643808`,
instance `i-01de6496943e7a94f`, with the role
`AmazonLightsailInstanceRole`. The CloudWatch agent is now explicitly
configured to use the deployment credentials as its source identity and to
assume `arn:aws:iam::591697681173:role/Page47CloudWatchAgent`; the metadata
role is not part of the working log path. The prior operational shorthand
called the host “Lightsail”; the current metadata reports an EC2 `t3.micro` in
`eu-north-1a`. The classification discrepancy remains an inventory note, not
a CloudWatch blocker.

## Resident watch storage

The general console creates a unique server-side watch record for each submission. It stores the selected city and public bodies, the address or neighbourhood, the email address, and whether the watch is active. The response includes a private management link; opening it shows the stored watch and allows the resident to stop it. Active watches are matched against saved reviews and are deduplicated by watch and review before SES is called.

## Cost record

The checked-in preflight arithmetic uses the original USD 50 planning limit, 14 days, the USD 7.00 monthly Lightsail assumption, 5 GB of storage at USD 0.023 per GB-month, 96 collector runs per day, and 100 attachments per day. It estimated USD 3.2667 for the instance and USD 0.0537 for storage over 14 days, for a fixed-cost subtotal of USD 3.3203 before model calls. The model-price portion is still marked as incomplete in the preflight record and must be calculated from current Bedrock prices before publishing a savings claim.

The two-stage document route is already measured on the stored Seattle run: 20 attachments were selected for page reading after text reading, 11 completed, and 9 recorded a visible failure. Denver currently has 270 selected-attachment reading results, with 259 candidate documents, 10 explicit no-reference results, and 1 unreadable document; two newly recovered candidates also have document-extraction results. The denominator for a future cost statement must be the full number of captured attachments, not only the selected candidates; no model-savings claim is published yet.

## Deployment record

1. Create the least-privilege AgentCore execution role with Bedrock invocation, S3 package read, CloudWatch Logs, and trace permissions. Grant the deployment identity `ssm:GetParameter`, `ssm:PutParameter`, and `iam:PassRole` limited to that role. **Complete.**
2. Put the execution-role ARN in `/page47/agentcore/execution-role-arn`, run `scripts/deploy_agentcore.py --deploy`, and verify the runtime reaches a healthy state. The script uploads the package, creates or updates `page47_review`, and writes `/page47/agentcore/runtime-arn`. **Complete: runtime reports `READY`.**
3. Switch `config/agentcore.yaml` invocation to enabled on Lightsail and restart `page47-web.service`. Invoke one real stored Seattle matter through AgentCore and verify the deterministic review is saved by the Lightsail service. **Complete: matter `17394` produced run `8ff0cc0b64d64d5c817a7275b0ad30c0`, five completed readers, 18 supported observations, and a saved `clearer` finding.**
4. Configure the SES sender parameter and verify SES sender status. **Complete:** sender configuration, application delivery, provider acceptance, and mailbox receipt are confirmed.
5. Send collector output to CloudWatch Logs and alarm on a missed run. **Partial:** the agent is active, both log groups have active streams, and the metric filter plus two-hour alarm exist in `eu-north-1`; the alarm is awaiting its initial evaluation windows and a deliberate-miss test remains.
6. Export one real post-activation review trace and retain its trace identifier. **Complete:** runtime version 16 uses `opentelemetry-instrument app.py`; run `dea939b750ec412ca0921b4a31422037` produced searchable trace `6aa2f721063b98043b31e7b86ca47cfb`, with 51 span events and one complete X-Ray summary.

The collector's delivery step does not create a message by itself. It loads only saved reviews marked for delivery, matches them against active watches, records one outcome for each watch and review pair, and calls SES only for a confirmed area match. A failed SES call is retained as a failed delivery and is retried on the next scheduled run.

## Evidence backup

The collector script runs the incremental durable-copy step inside the existing
collector lock with `PAGE47_EVIDENCE_BACKUP_BUCKET` set to
`page47-evidence-591697681173-eu-west-2-an`. The bucket is dedicated to Page 47
and separate from the AgentCore artifact bucket. It uses versioning, SSE-S3,
bucket-owner-enforced object ownership, and the S3 public-access block.

The deployment identity has only the permissions needed for the exporter:
`s3:GetBucketLocation` on the bucket and `s3:PutObject` plus `s3:GetObject` on
the Page 47 evidence prefix. `GetObject` allows the exporter to use
`HeadObject` metadata checks and skip objects whose verified SHA-256 is already
stored. The backup job has no object-deletion permission.

```bash
cd /home/ubuntu/page47-preflight
.venv/bin/python scripts/backup_evidence.py \
  --evidence-root runtime/evidence/seattle \
  --bucket YOUR_PAGE47_EVIDENCE_BUCKET \
  --prefix seattle \
  --region eu-west-2

.venv/bin/python scripts/backup_evidence.py \
  --evidence-root runtime/evidence/denver \
  --bucket YOUR_PAGE47_EVIDENCE_BUCKET \
  --prefix denver \
  --region eu-west-2
```

The command must finish only after verifying the local body hashes and
manifest chain. Keep its JSON result, including `integrity_root`, in the
deployment audit. The first scheduled-path backup was verified on 12 September
2026. A sample object returned an S3 version ID, SSE-S3 encryption, and matching
capture and response SHA-256 metadata. A repeat backup uploaded zero objects,
confirming incremental deduplication.
