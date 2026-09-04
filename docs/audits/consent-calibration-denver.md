# Denver consent placement calibration

## Evidence

- Meeting: Parks, Art and Culture, 1 September 2026, event `12901`.
- Published agenda: [Denver agenda PDF](https://denver.legistar1.com/denver/meetings/2026/9/12901_A_Parks%2C_Art_and_Culture_26-09-01_Committee_Agenda.pdf).
- Stored API response: [event 12901](https://webapi.legistar.com/v1/denver/events/12901?EventItems=1&AgendaNote=1&MinutesNote=1&EventItemAttachments=1), captured in `docs/evidence/preflight/responses/20260904T164423.223432Z_650bc8cd19a1088a_ee60828b4d1d7108.body` with SHA-256 `ee60828b4d1d710842794bc70cfc5052a4ae6638cca18f4239f00a69e5b4b1e0`.
- The PDF visibly labels page 2 `Consent Items`. The item at agenda sequence 8 is under that heading. The first page contains the regular `Action Items` section; the regular items have agenda sequences 1–7.

## Comparison

- Consent item `237282`, the Fox Run Park naming request, has `EventItemConsent: 1`.
- Regular items `237278`, `237279`, `237280`, `237281`, `237453`, `237454`, `237455`, and `237575` have `EventItemConsent: 0`.

## Decision

For Denver, the observed mapping is `1 = consent placement` and `0 = regular placement`. The mapping is recorded in `config/cities/denver.yaml` and is supported by a published agenda and its API response. Seattle remains explicitly disabled because its sampled consent and regular items both returned `0`.

This record shows where the items were published. Page 47 does not determine why these changes were made.
