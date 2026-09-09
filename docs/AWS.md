# AWS inventory

This document records the AWS choices made so far and the work still required to make the public service complete. It is intentionally specific about what is live and what is only present in the repository.

| Service or resource | Job here | Current state | What breaks without it |
|---|---|---|---|
| Public host, previously recorded as Lightsail (`eu-north-1`) | Keep the collector, record store, and public service running continuously. | The host at `13.62.181.128` is reachable and the collector/service remain healthy. Current EC2 metadata reports a `t3.micro` in account `000029643808`, instance `i-01de6496943e7a94f`, while the Page 47 deployment credentials belong to account `591697681173`; the hosting/account classification must be reconciled. | Scheduled public-record captures stop, and the service loses the forward-looking record that cannot be reconstructed later. |
| Local host disk | Hold immutable API responses, agenda PDFs, attachment PDFs, and SQLite records during the build. | Seattle and Denver captures and records are on the host under `runtime/`. Denver's follow-up now has HTTP 200 as the latest response for all 473 attachment IDs; the four earlier HTTP 404 responses remain preserved in the append-only evidence manifest. The current Denver PDF reader has 270 results: 259 candidates, 10 with no configured reference, and 1 unreadable PDF. The two recovered candidate PDFs have document-extraction results. An object-storage backup is not configured yet. | A disk failure would remove the only stored copy; the next task is to add a recoverable backup or move the evidence store to S3. |
| Amazon Bedrock in `eu-west-2` | Run text triage, page reading, and the five review roles. | Live model discovery on 6 September 2026 returned the configured IDs. `amazon.nova-micro-v1:0` is the text route; `amazon.nova-lite-v1:0` is the page-image route. The choices are recorded in `config/models.yaml` and `docs/model-verification.json`. | The application cannot read attachment pages or run a review. |
| AgentCore Runtime | Host the bursty five-role review graph separately from the always-on Lightsail service. | Runtime `page47_review` is `READY` in `eu-west-2`. ARN: `arn:aws:bedrock-agentcore:eu-west-2:591697681173:runtime/page47_review-X5IwXt4Y7h`. The current isolated-graph package is 49.8 MB compressed and 137 MB expanded. The Lightsail client invoked stored Seattle matter `17394`; run `8ff0cc0b64d64d5c817a7275b0ad30c0` completed with five readers, 18 supported observations, and a saved `clearer` finding. | The graph cannot run as the managed AWS workload or save a managed-runtime review. |
| Systems Manager Parameter Store | Hold the SES sender address, public service URL, AgentCore execution-role ARN, and managed runtime ARN outside source control. | Delivery code expects `/page47/email/sender` and `/page47/web/public-url`. `/page47/agentcore/execution-role-arn` contains the Page 47 role ARN, deployment wrote `/page47/agentcore/runtime-arn` with the `page47_review` runtime ARN, and `/page47/web/public-url` is now present with `https://page47.xcover.online/`. `/page47/email/sender` is still absent. | Email or managed review deployment fails loudly instead of exposing a secret, using an unknown sender, or silently falling back to an unconfigured runtime. |
| Amazon SESv2 | Send one review email to each matching watch. | The sender and recipient code is implemented, duplicate sends are recorded, and each message includes the private watch-management link. SES reports sending enabled but production access disabled; a verified sender, a verified controlled recipient while in sandbox, and the sender parameter are still required. No resident message has been sent. | Residents do not receive a review without logging into the console. |
| Page 47 console service | Serve the resident console and API from the public host. | `page47-web.service` is enabled and healthy on `127.0.0.1:8090`. DNS, the `page47.xcover.online` certificate, dedicated Nginx host, HTTP redirect, HTTPS health, root response, renewal dry-run, root-relative links, legacy `/page47` redirect, and the public URL parameter are verified. | Notification links cannot be tested until SES sender configuration is complete. |
| CloudWatch Logs | Keep collector and service failures visible. | The official agent package `1.300072.0b1766` is installed and the checked-in configuration passed validation. The agent is currently stopped because its host instance role, `AmazonLightsailInstanceRole`, lacks `logs:CreateLogStream`, `logs:PutLogEvents`, and `logs:DescribeLogGroups`. The deployment-user account sees no `/page47` groups. | A stopped collector could lose evidence silently. |
| CloudWatch alarm | Alert when the scheduled collector has not completed. | The collector emits `Page47SnapshotRunSuccess` only after all city capture, record application, document reading, placement, and delivery commands finish. Its lock holds the file descriptor in the parent shell, so a failed command cannot be hidden by the lock wrapper. `scripts/configure_cloudwatch.py` creates the log metric and a two-hour missed-run alarm from `config/observability.yaml`; it still needs to be run against the live log group and tested. | A missed run would not be noticed until the overwritten city record was already gone. |
| OpenTelemetry | Show one review from request through the five roles. | The current runtime requests `UNIFIED_TRACES_DESTINATION_ENABLED=true`. In `eu-west-2`, the `Page47TransactionSearchXRayAccess` resource policy now exists, the X-Ray destination is `CloudWatchLogs/ACTIVE`, and the default indexing target is 1%. No post-activation review trace has been retained. | The AWS execution path cannot yet be demonstrated with a searchable trace. |

## Launch runbook

The exact DNS, certificate, root-path rollout, SES, CloudWatch, trace, and
evaluation gates are maintained in [`docs/LAUNCH.md`](LAUNCH.md). It preserves
the existing `/page47` route until the subdomain has passed its health checks.

## Host identity boundary (9 September 2026)

The AWS CLI on the host, when run with the Page 47 deployment credentials,
identifies as `arn:aws:iam::591697681173:user/page47-vps-deploy`. The host's
EC2 metadata identifies the machine separately as account `000029643808`,
instance `i-01de6496943e7a94f`, with the role
`AmazonLightsailInstanceRole`. The CloudWatch agent uses that instance role,
not the Page 47 deployment user. The prior operational shorthand called the
host “Lightsail”; the current metadata reports an EC2 `t3.micro` in
`eu-north-1a`, so the account and hosting classification must be reconciled
before monitoring is called complete.

## Resident watch storage

The general console creates a unique server-side watch record for each submission. It stores the selected city and public bodies, the address or neighbourhood, the email address, and whether the watch is active. The response includes a private management link; opening it shows the stored watch and allows the resident to stop it. Active watches are matched against saved reviews and are deduplicated by watch and review before SES is called.

## Cost record

The checked-in preflight arithmetic uses the original USD 50 planning limit, 14 days, the USD 7.00 monthly Lightsail assumption, 5 GB of storage at USD 0.023 per GB-month, 96 collector runs per day, and 100 attachments per day. It estimated USD 3.2667 for the instance and USD 0.0537 for storage over 14 days, for a fixed-cost subtotal of USD 3.3203 before model calls. The model-price portion is still marked as incomplete in the preflight record and must be calculated from current Bedrock prices before publishing a savings claim.

The two-stage document route is already measured on the stored Seattle run: 20 attachments were selected for page reading after text reading, 11 completed, and 9 recorded a visible failure. Denver currently has 270 selected-attachment reading results, with 259 candidate documents, 10 explicit no-reference results, and 1 unreadable document; two newly recovered candidates also have document-extraction results. The denominator for a future cost statement must be the full number of captured attachments, not only the selected candidates; no model-savings claim is published yet.

## Deployment sequence still required

1. Create the least-privilege AgentCore execution role with Bedrock invocation, S3 package read, CloudWatch Logs, and trace permissions. Grant the deployment identity `ssm:GetParameter`, `ssm:PutParameter`, and `iam:PassRole` limited to that role. **Complete.**
2. Put the execution-role ARN in `/page47/agentcore/execution-role-arn`, run `scripts/deploy_agentcore.py --deploy`, and verify the runtime reaches a healthy state. The script uploads the package, creates or updates `page47_review`, and writes `/page47/agentcore/runtime-arn`. **Complete: runtime reports `READY`.**
3. Switch `config/agentcore.yaml` invocation to enabled on Lightsail and restart `page47-web.service`. Invoke one real stored Seattle matter through AgentCore and verify the deterministic review is saved by the Lightsail service. **Complete: matter `17394` produced run `8ff0cc0b64d64d5c817a7275b0ad30c0`, five completed readers, 18 supported observations, and a saved `clearer` finding.**
4. Configure the SES sender parameter and verify SES sender status. **Partial:** the public URL parameter is present; sender verification and a controlled message remain.
5. Send collector output to CloudWatch Logs and alarm on a missed run. **Blocked:** the agent package/configuration are installed, but the separate host instance role in account `000029643808` cannot write to the groups; no metric filter or alarm exists.
6. Export one real post-activation review trace and retain its trace identifier. **Partial:** Transaction Search is active in `eu-west-2`, but no post-activation trace has been captured.

The collector's delivery step does not create a message by itself. It loads only saved reviews marked for delivery, matches them against active watches, records one outcome for each watch and review pair, and calls SES only for a confirmed area match. A failed SES call is retained as a failed delivery and is retried on the next scheduled run.
