# Seattle PDF consent placement calibration

## Method

Seattle's `EventItemConsent` value was `0` for both visible consent and regular items. The reader therefore uses the published agenda PDF. It extracts page text, finds `APPROVAL OF CONSENT CALENDAR` and `ITEMS REMOVED FROM CONSENT CALENDAR`, then matches an API item's normalized title to its position in that interval. A missing or ambiguous title remains `cannot_determine`.

## Real records checked

- Event `6865`, 18 August 2026: consent section on pages 3–7, regular material beginning on page 8. API response SHA-256 `b5fb03cbba69365ced7fc675b22b6f2e3ea0d8328d9bfddcd02ba14d826f6010`; agenda PDF SHA-256 `9badbe727708a003f497d810f63cba11c74c05b41151d01b4c0928e0fa02d83b`.
- Event `6854`, 11 August 2026: consent heading on page 3 and removal heading on page 12. API response SHA-256 `6752aeda10342ec1f7a2272efbd4ab7c87fb263cdc7a240baa8fa4d2fd2991b6`; agenda PDF SHA-256 `f879dcd9ba411c54eb9f5ac174897f76ae2ad9d48fb4c6cd913b08ae66614572`.
- Event `6847`, 4 August 2026: consent heading on page 3 and removal heading on page 8. API response SHA-256 `9af91de0ca4eec41b79a3f0db8b8830119dcd99683ca3e2c007311916069ca78`; agenda PDF SHA-256 `597eb6daa175ee17c7395e91e52576bc00832227e2d8f003ecc7217b8e4735e2`.

The reader classified matter-bearing items from all three agendas using the exact stored API titles: 23 items on event `6865`, 45 on `6854`, and 36 on `6847`. It produced both consent and regular results. The API integer is not used for Seattle placement.

## Limits

This reader depends on a text-readable agenda and an item title that appears in it. Scanned pages, changed titles, and missing agenda PDFs return `cannot_determine`. It does not infer placement from agenda sequence alone.

This record shows where the items were published. Page 47 does not determine why these changes were made.
