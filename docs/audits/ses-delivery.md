# SES delivery check

Date: 9 September 2026.

The Page 47 host at `13.62.181.128` was checked over SSH. The host service was
active, and `https://page47.xcover.online/healthz` returned the expected
healthy response.

The live AWS checks, run in `eu-west-2`, found:

- `/page47/email/sender` is present in Parameter Store;
- SES `SendingEnabled=true`;
- SES `ProductionAccessEnabled=false` (sandbox mode); and
- the configured sender identity has `VerifiedForSendingStatus=true`.

No recipient parameter is stored. The Seattle and Denver record stores each
have zero active watches and zero notification rows, so this deployment has
not yet exercised a controlled message and has no provider message ID or
receipt to record. The remaining SES gate is one controlled sandbox recipient,
an application delivery attempt, and confirmation of receipt.

No email address or credential is stored in this audit.
