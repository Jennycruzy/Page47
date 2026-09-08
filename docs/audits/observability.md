# Observability attempt

Date: 8 September 2026.

The deployed `page47_review` runtime was `READY` before this check. Its current
artifact, execution role, network mode, protocol, and lifecycle settings were
read without changing them. A trace-only update temporarily set
`UNIFIED_TRACES_DESTINATION_ENABLED=true`; the control plane returned `READY`,
but a controlled invocation of stored Seattle matter `17394` returned HTTP 500.
The runtime environment was then restored to its prior empty environment and
returned `READY` again.

The application service remained healthy after the rollback: `/healthz` returned
`{"status":"ok","service":"Page 47"}` and the Seattle ledger remained
readable. The invocation did not produce a usable trace identifier. Its final
application error was `Brief writer cited unknown observation: N/A`, so this
check does not claim that the AgentCore runtime is unhealthy or that tracing is
complete.

The account-level X-Ray check still reports the `XRay` trace destination rather
than CloudWatch Logs. Transaction Search enablement, the required account
permissions, a successful review invocation, and retention of a viewable trace
remain deployment work.
