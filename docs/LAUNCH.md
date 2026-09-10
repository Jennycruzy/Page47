# Page 47 launch runbook

This is the operator sequence for the chosen launch URL:

`https://page47.xcover.online/`

The existing `https://xcover.online/page47/` route stays in service until the
subdomain is healthy. Do not change `config/web.yaml` on the VPS, or the public
URL parameter, before the DNS and certificate checks below pass.

## 1. DNS and HTTPS

At the DNS provider authoritative for `xcover.online`, create:

| Type | Host | Value | TTL |
|---|---|---|---|
| A | `page47` | `13.62.181.128` | 300 seconds |

Verify from more than one resolver:

```sh
dig +short page47.xcover.online A
dig @1.1.1.1 +short page47.xcover.online A
dig @8.8.8.8 +short page47.xcover.online A
```

All checks must return `13.62.181.128`. On the Lightsail host, install the
temporary ACME virtual host and obtain the certificate without stopping the
existing xCover virtual host:

```sh
cd /home/ubuntu/page47-preflight
sudo mkdir -p /var/www/certbot
sudo install -m 0644 deploy/nginx/page47-subdomain-acme.conf \
  /etc/nginx/sites-available/page47.xcover.online
sudo ln -sfn /etc/nginx/sites-available/page47.xcover.online \
  /etc/nginx/sites-enabled/page47.xcover.online
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/certbot \
  -d page47.xcover.online --email '<operations-email>' \
  --agree-tos --no-eff-email --non-interactive
```

After the certificate is issued, replace the temporary file with the checked-in
TLS proxy and reload Nginx:

```sh
sudo install -m 0644 deploy/nginx/page47-subdomain.conf \
  /etc/nginx/sites-available/page47.xcover.online
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

The final proxy sends the root path to `127.0.0.1:8090`. Keep the existing
`/page47` location in the xCover virtual host until the subdomain checks pass.

## 2. Public URL and SES parameters

The parameters belong in `eu-west-2`, matching `config/notifications.yaml` and
the AgentCore runtime. An administrator or narrowly scoped deployment identity
must create/update these values:

```sh
aws ssm put-parameter --region eu-west-2 \
  --name /page47/web/public-url --type String --overwrite \
  --value https://page47.xcover.online/

aws ssm put-parameter --region eu-west-2 \
  --name /page47/email/sender --type String --overwrite \
  --value '<verified-sender-address>'
```

Before sending, verify the sender identity and account status without printing
credentials or message contents:

```sh
aws sesv2 get-account --region eu-west-2 \
  --query '{sending:SendingEnabled,production:ProductionAccessEnabled}'
aws sesv2 get-email-identity --region eu-west-2 \
  --email-identity '<verified-sender-address>' \
  --query '{verified:VerifiedForSending,identity:IdentityType}'
```

The controlled delivery test must use a mailbox explicitly chosen for this
deployment. Confirm the provider returns a `MessageId`, then confirm receipt;
the recipient address is not a repository setting.

Current state as of 2026-09-10: `/page47/web/public-url` and
`/page47/email/sender` are present in `eu-west-2`; the SES sender identity is
verified. SES reports `SendingEnabled=true` and
`ProductionAccessEnabled=false`. A temporary verified watch sent one controlled
review through the application and received a provider `MessageId`; the watch
was then deactivated. Mailbox receipt was confirmed, so the SES delivery gate
is complete even though the account remains in sandbox mode.

## 3. Deploy the root-path configuration

Only after the subdomain and certificate work:

```sh
cd /home/ubuntu/page47-preflight
git fetch origin main
git merge --ff-only origin/main
sudo systemctl restart page47-web.service
curl -fsS http://127.0.0.1:8090/healthz
curl -fsS https://page47.xcover.online/healthz
curl -fsS https://page47.xcover.online/api/cities/Seattle%2C%20Washington/ledger
```

The checked-in `config/web.yaml` uses `public_path: /`. Verify that generated
review, watch, and document links begin at the subdomain root. After those
checks pass, install `deploy/nginx/page47-location.conf` in the existing xCover
virtual host and reload Nginx; it redirects old `/page47` bookmarks to the new
subdomain without sending them to the xCover application root.

## 4. CloudWatch Logs and missed-run alarm

The official CloudWatch agent package `1.300072.0b1766` is installed on the
host. The agent runs as root and uses the existing `page47-vps-deploy`
credentials as its source identity, then assumes the dedicated
`Page47CloudWatchAgent` role in account `591697681173`. This avoids relying on
the non-customer `AmazonLightsailInstanceRole` reported by the host metadata.

Apply the checked-in configuration and shared credentials settings:

```sh
cd /home/ubuntu/page47-preflight
sudo install -m 0644 deploy/cloudwatch/page47-agent.json \
  /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/file_amazon-cloudwatch-agent.json
sudo install -m 0644 deploy/cloudwatch/common-config.toml \
  /opt/aws/amazon-cloudwatch-agent/etc/common-config.toml
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.d/file_amazon-cloudwatch-agent.json
sudo systemctl restart amazon-cloudwatch-agent
sudo systemctl is-active amazon-cloudwatch-agent
```

From the Page 47 virtual environment, create the metric filter and alarm:

```sh
cd /home/ubuntu/page47-preflight
.venv/bin/python scripts/configure_cloudwatch.py \
  --config config/observability.yaml
```

Verify the two log groups, the `Page47/Snapshotter/CompletedRuns` metric, and
the `Page47-Snapshotter-MissedRun` alarm in `eu-north-1`. Test the alarm only
with a planned short pause of the collector and restore the cron entry
immediately afterward; do not delete evidence or alter the append-only store.

The 9 September 2026 live check found both log groups with active streams and
14-day retention. The metric filter and alarm were created successfully; the
alarm initially reports `INSUFFICIENT_DATA` while its two one-hour evaluation
windows fill.

## 5. Transaction Search and one successful trace

The AgentCore runtime is in `eu-west-2`, so configure and verify the
Transaction Search destination there. The account resource policy
`Page47TransactionSearchXRayAccess` now exists in that region, and the current
account-level result is:

```sh
aws xray get-trace-segment-destination --region eu-west-2
# Destination: CloudWatchLogs
# Status: ACTIVE
```

The default indexing rule is restored to a 1% target after a temporary 100%
setting used while preparing the controlled test:

```sh
aws xray get-indexing-rules --region eu-west-2
```

The current AgentCore runtime is a runtime-hosted Strands agent. The checked-in
package includes `aws-opentelemetry-distro>=0.18.0`, and the entrypoint launches
`opentelemetry-instrument app.py` so ADOT configures the active tracer provider
before the Strands graph loads. Do not infer trace support from the runtime's
`READY` status.

The managed runtime is in `eu-west-2`. Deploy the checked-in runtime artifact
with `scripts/deploy_agentcore.py --deploy`; the deployment code requests
`AGENT_OBSERVABILITY_ENABLED=true` and
`UNIFIED_TRACES_DESTINATION_ENABLED=true`. Verify the runtime returns `READY`
and that its environment contains both intended settings.

After deployment, open the AgentCore console's **Agent Runtime** page, select
`page47_review`, choose **Tracing → Edit**, toggle **Enable**, and choose
**Save**. This runtime-level switch starts the collector that accepts the
entrypoint's OTLP spans; without it, the exporter reports a refused
`localhost:4318` connection and no `spans` events are delivered.

Use one stored Seattle matter for the controlled invocation. A successful test
must have all of the following before it is called complete:

1. the Lightsail API returns success;
2. the investigation run is saved with `status=completed`;
3. the saved finding has primary evidence and no placeholder IDs;
4. the trace identifier is searchable in CloudWatch Transaction Search; and
5. the trace identifier, runtime ARN, matter ID, and UTC timestamp are recorded
   in `docs/audits/observability.md`.

If the review returns an application error, roll the runtime environment back
to its last known-good setting before retrying. Do not claim trace completion
from a control-plane `READY` response alone.

On 2026-09-10, runtime version 16 completed run
`dea939b750ec412ca0921b4a31422037` for matter `17394`. The exact window
returned one complete X-Ray summary for trace
`6aa2f721063b98043b31e7b86ca47cfb` and the runtime `spans` stream contained 51
events, including the graph, five roles, tool calls, and Bedrock model calls.
The trace gate is complete; the retained details are in
`docs/audits/observability.md`.

## 6. Evidence and evaluation gates

Denver follow-up remains an evidence-quality note, not a completeness claim:

- 473 attachment records are captured and the latest response for each is HTTP
  200; the four earlier HTTP 404 responses remain preserved in the append-only
  manifest;
- 270 URL-identified PDFs have reading results: 259 candidates, 10 absent/no
  reference, and 1 unreadable;
- the two PDFs recovered during the follow-up also have document-extraction
  results; and
- the remaining 203 successful attachments are non-PDF URLs outside the
  current PDF reader path.

The Seattle export is at `docs/evaluation-set.json` on the deployment host. The
first 30 matters are the gold subset. The completed human audit records all 30
as `cannot_determine` because the stored public record lacks the required
placement evidence, with primary record URLs and capture times. The export
status is `human_reviewed`, and the strict validator passes. Do not publish
comparison metrics until the comparison outputs and every miss have been
checked.

The controlled fixture is separate from that historical audit. It contains 28
known transformations covering clearer, less-clear, mixed, unchanged, and
cannot-determine outcomes, plus two directional reversal pairs. Its current
deterministic run is preserved in `docs/controlled-evaluation-results.json`:
28/28 Page 47 comparator states and 2/2 reversal pairs. Those are controlled
fixture results, not real-world accuracy, and the artifact remains marked
`review_required`; the fixture's Skeptic annotations are not measured by this
deterministic runner.

## Required permissions

The `page47-vps-deploy` identity now has the customer inline policy
`Page47OperationsPermissions`. The host instance role is a separate principal
and still needs the following log access in its own account:

- SSM: `ssm:GetParameter` for `/page47/*`; `ssm:PutParameter` only for the
  Page 47 parameters;
- SES: `ses:GetAccount`, `ses:GetEmailIdentity`, and `ses:SendEmail` for the
  verified sender;
- CloudWatch Logs: log-group/stream discovery, log-stream creation, event
  writes, metric-filter creation, and retention configuration for `/page47/*`;
- CloudWatch alarms: create/update and describe the named Page 47 alarm;
- X-Ray/Transaction Search: `xray:GetTraceSegmentDestination`,
  `xray:UpdateTraceSegmentDestination`, `xray:GetIndexingRules`,
  `xray:UpdateIndexingRule`, the required log-group creation/retention actions,
  and `logs:PutResourcePolicy`/`logs:DescribeResourcePolicies`; and
- the host's `AmazonLightsailInstanceRole` principal in account `000029643808`:
  log-group/stream discovery, log stream creation, retention configuration,
  and log event writes only for the two Page 47 log groups. The role must be
  granted access in that account, or the destination must be changed to a
  deliberately configured cross-account design.

Do not place AWS access keys, mailbox credentials, or certificate private keys
in this repository.
