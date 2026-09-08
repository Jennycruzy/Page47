# Managed runtime review

This record proves that the Lightsail service can send a real stored matter to the deployed AgentCore runtime and save the returned review. It does not use a fabricated matter or a test-only response.

## Deployment evidence

The deployment was run on Lightsail with the checked-in deployment script and the configured execution-role parameter:

```text
cd /home/ubuntu/page47-preflight
PATH=/home/ubuntu/page47-preflight/.venv/bin:$PATH \
PYTHONPATH=/home/ubuntu/page47-preflight/src \
.venv/bin/python3 scripts/deploy_agentcore.py \
  --project-root . --config config/agentcore.yaml \
  --output /tmp/page47-agentcore.zip --deploy
```

The current package contains the required root `app.py`, measures 49,810,273
bytes compressed, and expands to 137,066,621 bytes. The runtime read back from
AWS is:

```text
runtime: page47_review
region: eu-west-2
status: READY
artifact: page47-review/agentcore-deployment-isolated.zip
package_sha256: 5b1a097b29080237954b732fe4f92295478e2cb77d4b30fb6c9cee40a7bb6b22
arn: arn:aws:bedrock-agentcore:eu-west-2:591697681173:runtime/page47_review-X5IwXt4Y7h
```

The role used by the runtime is stored in `/page47/agentcore/execution-role-arn` and is not copied into application source.

## Real review evidence

The Lightsail API submitted stored Seattle matter `17394`:

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

The saved graph state contains all five expected readers—Archivist, Substance, Process, Skeptic, and Brief Writer—with five completed nodes, zero failed nodes, and five executions. The saved resident-facing links were checked against the stored evidence catalog; they resolve to the city's Legistar record or to captured evidence, and no model-supplied placeholder URL was retained.

The saved graph has five completed nodes, zero failed nodes, and five
executions. The same record store retains failed review attempts instead of
replacing them. The controlled run's AgentCore log recorded successful
completion in 53.241 seconds. This preserves failures for review and prevents
a bad answer from being presented as a successful one.

## Verification commands

The following checks were run on Lightsail after the deployment:

```text
curl -sS http://127.0.0.1:8090/healthz
{"status":"ok","service":"Page 47"}

curl -sS https://page47.xcover.online/healthz
{"status":"ok","service":"Page 47"}

PYTHONPATH=/home/ubuntu/page47-preflight/src:/home/ubuntu/page47-preflight/tests \
/home/ubuntu/page47-preflight/.venv/bin/python3 -m pytest -q --import-mode=importlib tests
44 passed

PYTHONPATH=/home/ubuntu/page47-preflight/src \
/home/ubuntu/page47-preflight/.venv/bin/ruff check src/page47 scripts tests
All checks passed!

MYPYPATH=/home/ubuntu/page47-preflight/src \
/home/ubuntu/page47-preflight/.venv/bin/mypy --strict --explicit-package-bases \
/home/ubuntu/page47-preflight/src/page47
Success: no issues found in 45 source files
```

## Remaining operational work

This verification covers the managed review request, the live subdomain, and
its save path. It does not claim that email delivery, Lightsail CloudWatch
delivery/alarming, or a viewable trace is complete. Those items remain listed
in `docs/AWS.md` until each one has a live check and recorded result.
