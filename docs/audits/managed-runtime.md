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

The package contained the required root `app.py`, measured 49,809,452 bytes compressed, and expanded to 137,062,304 bytes. The runtime read back from AWS is:

```text
runtime: page47_review
region: eu-west-2
version: 7
status: READY
arn: arn:aws:bedrock-agentcore:eu-west-2:591697681173:runtime/page47_review-X5IwXt4Y7h
```

The role used by the runtime is stored in `/page47/agentcore/execution-role-arn` and is not copied into application source.

## Real review evidence

The Lightsail API submitted stored Seattle matter `17394`:

```text
POST /api/cities/Seattle%2C%20Washington/matters/17394/investigate
HTTP 200
run_id: 4c8f8a7767e545fe9a5cabea73d5bf89
finding_id: seattle,-washington-17394
state: clearer
publish: true
supported_count: 18
rejected_count: 0
```

The saved graph state contains all five expected readers—Archivist, Substance, Process, Skeptic, and Brief Writer—with five completed nodes, zero failed nodes, and five executions. The saved resident-facing links were checked against the stored evidence catalog; they resolve to the city's Legistar record or to captured evidence, and no model-supplied placeholder URL was retained.

The same record store retains failed review attempts instead of replacing them. For example, an earlier attempt for matter `17394` was saved as failed after a document page mismatch was rejected. This preserves the failure for review and prevents a bad answer from being presented as a successful one.

## Verification commands

The following checks were run on Lightsail after the deployment:

```text
curl -sS http://127.0.0.1:8090/healthz
{"status":"ok","service":"Page 47"}

PYTHONPATH=/home/ubuntu/page47-preflight/src:/home/ubuntu/page47-preflight/tests \
/home/ubuntu/page47-preflight/.venv/bin/python3 -m pytest -q --import-mode=importlib tests
39 passed

PYTHONPATH=/home/ubuntu/page47-preflight/src \
/home/ubuntu/page47-preflight/.venv/bin/ruff check src/page47 scripts tests
All checks passed!

MYPYPATH=/home/ubuntu/page47-preflight/src \
/home/ubuntu/page47-preflight/.venv/bin/mypy --strict --explicit-package-bases \
/home/ubuntu/page47-preflight/src/page47
Success: no issues found in 45 source files
```

## Remaining operational work

This verification covers the managed review request and its save path. It does not claim that email, CloudWatch delivery, a public domain, or a viewable trace is complete. Those items remain listed in `docs/AWS.md` until each one has a live check and recorded result.
