# AWS inventory

This document records the AWS choices made so far and the work still required to make the public service complete. It is intentionally specific about what is live and what is only present in the repository.

| Service or resource | Job here | Current state | What breaks without it |
|---|---|---|---|
| Lightsail, Stockholm (`eu-north-1`) | Keep the collector, record store, and future public service running continuously at a fixed cost. | One Linux/Unix instance is running with 1 GB memory, 2 vCPUs, 40 GB SSD, and 2 TB transfer. The captured pricing assumption is USD 7.00 per month. | Scheduled public-record captures stop, and the service loses the forward-looking record that cannot be reconstructed later. |
| Local Lightsail disk | Hold immutable API responses, agenda PDFs, attachment PDFs, and SQLite records during the build. | Seattle and Denver captures and records are on the instance under `runtime/`. An object-storage backup is not configured yet. | A disk failure would remove the only stored copy; the next task is to add a recoverable backup or move the evidence store to S3. |
| Amazon Bedrock in `eu-west-2` | Run text triage, page reading, and the five review roles. | Live discovery and a real invocation succeeded on 5 September 2026. `amazon.nova-micro-v1:0` is the text route; `amazon.nova-lite-v1:0` is the page-image route. The choices are recorded in `config/models.yaml` and `docs/model-verification.json`. | The application cannot read attachment pages or run a review. |
| AgentCore Runtime | Host the bursty five-role review graph separately from the always-on Lightsail service. | The installed `bedrock-agentcore` 1.22.0 package, runtime entrypoint, typed Lightsail client, and repeatable deployment script are in the repository. A real arm64 package was built on the VPS: 49.8 MB compressed and 137 MB expanded. `ListAgentRuntimes` returned an empty list, and the first deployment check stopped before upload because the deployment identity lacks `ssm:GetParameter` for the execution-role parameter. | The graph remains a local library call and cannot be shown as the managed AWS workload required for the live demonstration. |
| Systems Manager Parameter Store | Hold the SES sender address, public service URL, AgentCore execution-role ARN, and managed runtime ARN outside source control. | Delivery code expects `/page47/email/sender` and `/page47/web/public-url`. Deployment expects `/page47/agentcore/execution-role-arn` and writes `/page47/agentcore/runtime-arn`. The current VPS identity was denied `ssm:GetParameter` for the execution-role parameter. | Email or managed review deployment fails loudly instead of exposing a secret, using an unknown sender, or silently falling back to an unconfigured runtime. |
| Amazon SESv2 | Send one review email to each matching watch. | The sender and recipient code is implemented and duplicate sends are recorded. End-to-end delivery still requires a verified SES identity and the two SSM parameters. | Residents do not receive a review without logging into the console. |
| Page 47 console service | Serve the resident console and API from Lightsail. | `page47-web.service` is enabled and healthy on `127.0.0.1:8090`. A temporary route through the existing TLS host passed direct health, city, ledger, and proxied API checks; a separate public domain is pending. | Residents and judges cannot browse the live records, watch setup, findings, or captured documents. |
| CloudWatch Logs | Keep collector and service failures visible. | Not connected yet. | A stopped collector could lose evidence silently. |
| CloudWatch alarm | Alert when the scheduled collector has not completed. | Not created yet. | A missed run would not be noticed until the overwritten city record was already gone. |
| OpenTelemetry | Show one review from request through the five roles. | Strands and AgentCore can provide the trace hooks, but an exporter and a viewable trace have not been configured. | The AWS execution path cannot be demonstrated end to end. |

## Cost record

The checked-in preflight arithmetic uses the original USD 50 planning limit, 14 days, the USD 7.00 monthly Lightsail assumption, 5 GB of storage at USD 0.023 per GB-month, 96 collector runs per day, and 100 attachments per day. It estimated USD 3.2667 for the instance and USD 0.0537 for storage over 14 days, for a fixed-cost subtotal of USD 3.3203 before model calls. The model-price portion is still marked as incomplete in the preflight record and must be calculated from current Bedrock prices before publishing a savings claim.

The two-stage document route is already measured on the stored Seattle run: 20 attachments were selected for page reading after text reading, 11 completed, and 9 recorded a visible failure. The denominator for a future cost statement must be the full number of captured attachments, not only those 20 candidates.

## Deployment sequence still required

1. Create the least-privilege AgentCore execution role with Bedrock invocation, S3 package read, CloudWatch Logs, and trace permissions. Grant the deployment identity `ssm:GetParameter`, `ssm:PutParameter`, and `iam:PassRole` limited to that role.
2. Put the execution-role ARN in `/page47/agentcore/execution-role-arn`, run `scripts/deploy_agentcore.py --deploy`, and verify the runtime reaches a healthy state. The script uploads the package, creates or updates `page47-review`, and writes `/page47/agentcore/runtime-arn`.
3. Switch `config/agentcore.yaml` invocation to enabled on Lightsail and restart `page47-web.service`. Invoke one real stored Seattle matter through AgentCore and verify the deterministic review is saved by the Lightsail service.
4. Configure the two SES parameters and verify SES sender status. Send one real message to a controlled address and retain the provider result without logging credentials.
5. Send collector output to CloudWatch Logs and alarm on a missed run. Show the alarm test in the deployment record.
6. Export one real review trace and retain its trace identifier for the demonstration.
