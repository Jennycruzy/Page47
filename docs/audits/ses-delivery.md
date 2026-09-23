# SES delivery check

Date: 10 September 2026.

The Page 47 host at `13.62.181.128` was checked over SSH. The host service was
active, and `https://page47.xcover.online/healthz` returned the expected
healthy response.

The live AWS checks, run in `eu-west-2`, found:

- `/page47/email/sender` is present in Parameter Store;
- SES `SendingEnabled=true`;
- SES `ProductionAccessEnabled=false` (sandbox mode); and
- the configured sender identity has `VerifiedForSendingStatus=true`.

The first application delivery attempt stopped before SES because boto3's SSM
response contained a `datetime` value that the JSON normalizer rejected. The
compatibility fix was committed as `4faf175`, pushed, copied to the VPS, and
loaded by `page47-web.service`.

The retry used one temporary verified Seattle watch with a matching public
record. It produced:

```text
status: sent
area_status: confirmed
provider_message_id: 010b01a088acd751-22fa09f3-3a1d-43a5-a3f6-c9bd20b1d132-000000
updated_at: 2026-09-10T00:17:03.946949+00:00
```

The temporary watch was then deactivated. This proves that the Page 47
application reached SES and SES accepted the message. The operator then
confirmed receipt in the verified mailbox. The SES delivery gate is complete;
production access is not required for this controlled verified-recipient test.

No email address or credential is stored in this audit.

## Production-access follow-up

Dates: 15–17 September 2026.

AWS Support approved Page 47's SES production-access request for the Europe
(London) region on 15 September 2026. A read-only verification from the Page 47
VPS on 17 September 2026 at `2026-09-17T00:58:05Z` confirmed:

- SES `SendingEnabled=true`;
- SES `ProductionAccessEnabled=true` (the account is out of the sandbox);
- `Max24HourSend=50000`; and
- `MaxSendRate=14` messages per second.

The sender, public URL, and managed-runtime parameters were still present in
Systems Manager Parameter Store, and the local web health check returned
`{"status":"ok","service":"Page 47"}`. This closes the sandbox gate for
ordinary consented recipients. The controlled message and mailbox receipt
above remain the historical delivery evidence; no email address or credential
is stored in this audit.

## Live production-path check

Date: 23 September 2026.

A read-only VPS check at `2026-09-23T05:13:26Z` confirmed `page47-web.service`
was active and enabled. The public homepage and `/healthz` both returned HTTP
200. SES in `eu-west-2` reported `SendingEnabled=true`,
`ProductionAccessEnabled=true`, `Max24HourSend=50000`, and `MaxSendRate=14`; the
`page47.xcover.online` domain identity remained verified. The fifteen-minute
collector cron entry was present and its log had been updated at
`2026-09-23T05:06:47Z`; that timestamp confirms recent log activity, not by
itself a successful full collector cycle.

A read-only query of the Seattle and Denver notification tables for records
dated on or after 15 September found seven Seattle outcomes, all `skipped`, and
no Denver outcomes. No post-approval `sent` or `failed` application delivery is
recorded. The last retained mailbox receipt remains the 10 September sandbox
test above; no production mailbox receipt is claimed.
