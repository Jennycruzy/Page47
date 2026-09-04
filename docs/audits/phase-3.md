# Phase 3 audit — Seattle consent calibration

Status: awaiting human confirmation. No code uses the consent value to classify or notify a resident.

## Meeting and evidence

- Meeting: Seattle City Council, event `6865`, 18 August 2026, 2:00 PM.
- Published agenda: [City Council agenda PDF](https://legistar2.granicus.com/seattle/meetings/2026/8/6865_A_City_Council_26-08-18_Full_Council_Meeting_Agenda.pdf).
- Stored event record: [Seattle event 6865 API response](https://webapi.legistar.com/v1/seattle/events/6865?EventItems=1&AgendaNote=1&MinutesNote=1&EventItemAttachments=1).
- The captured agenda is stored on Lightsail at `runtime/evidence/seattle/bodies/9badbe727708a003f497d810f63cba11c74c05b41151d01b4c0928e0fa02d83b.body`, captured at `2026-09-04T20:35:52.561476Z`, with SHA-256 `9badbe727708a003f497d810f63cba11c74c05b41151d01b4c0928e0fa02d83b`.
- The rendered page 3 visibly says `G. APPROVAL OF CONSENT CALENDAR` and describes the Consent Calendar as routine items. Pages 4 through 7 continue the items under that section. Page 8 visibly starts `H. COMMITTEE REPORTS`; the three selected matter items there are regular-agenda items.

## Comparison

- Consent-section matter items: event-item IDs `125441`, `125442`, and `125370` through `125386` — `19` items, all with `EventItemConsent = 0`.
- Regular-agenda matter items: event-item IDs `125389`, `125408`, and `125409` — `3` items, all with `EventItemConsent = 0`.
- A database query over all `24,047` stored appearances found only one value: `0`.

## Result

The observation does not distinguish consent placement from regular placement. The proposed Seattle mapping is therefore none, and `config/cities/seattle.yaml` records `mapping_usable: false` with both observed value sets as `[0]`. Consent placement must remain disabled for Seattle unless a later human-approved calibration produces distinct values.

## Blockers

- Human confirmation is required before any later code depends on Seattle consent placement.
- The AWS role still cannot list Bedrock models or AgentCore runtimes.

## Exit criteria

The meeting, visible section, event-item IDs, raw values, API record, captured agenda hash, and unusable result are recorded. The consent value remains stored for evidence but is not interpreted.
