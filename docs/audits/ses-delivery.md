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
application reached SES and SES accepted the message. Mailbox receipt still
requires a manual check in the verified inbox; no claim is made about receipt
until that check is confirmed.

No email address or credential is stored in this audit.
