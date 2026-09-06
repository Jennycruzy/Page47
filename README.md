# Page 47

Page 47 helps residents see how a public matter was presented across the meetings where it appeared. It compares the public record over time and links every reported fact back to the city record.

The named primitive is **presentation drift**: the gap between how a matter is described to the public and what the matter actually does, measured across every appearance.

## Current build

The current complete record source is Seattle, Washington, on the Granicus Legistar public API. Denver, Colorado is also configured with a separately verified consent mapping so the console can demonstrate that the city-specific meaning is never copied from Seattle. The live preflight sampled 20 events, found 73 event items and 66 attachments, and found Seattle records reaching the observed sample boundary of 2015-02-02. Nine Seattle council bodies are recorded in `config/cities/seattle.yaml`.

The snapshotter is running on the Lightsail instance every 15 minutes. Its first clean capture selected five upcoming meetings and stored 30 attachment files plus five agendas. It keeps immutable bytes, SHA-256 hashes, capture times, source URLs, ETags when supplied, and explicit error records.

The historical record is now backfilled for the nine selected Seattle bodies: 1,332 meetings, 24,047 appearances, 25,640 attachment records, and 81 matters with at least three appearances, covering 9 February 2015 through 11 September 2026. The normalized SQLite store is running on Lightsail at `runtime/records/seattle.sqlite3`; all present stored fields carry a source URL and capture time.

Seattle consent placement is read from captured agenda PDFs rather than the city's unusable API integer. Denver uses its own verified mapping: `1` means consent and `0` means regular agenda in the calibrated meeting. Seattle and Denver both have live append-only captures on the Lightsail instance.

Captured Seattle PDF attachments are read into page-linked references for configured dates, dollar amounts, distances, and parcel references. Twenty Seattle attachments have completed the document-specific reading run; eleven returned structured page readings and nine recorded explicit failures. The reader preserves the document URL, capture time, page, character location, and excerpt. It says when no configured reference was found and when a PDF cannot be read. The verified Bedrock routes are `amazon.nova-micro-v1:0` for text work and `amazon.nova-lite-v1:0` for page images in `eu-west-2`.

The five-node Strands investigation graph and its AgentCore transport are implemented and pass strict type checking. A real Seattle matter has been reviewed locally and saved with primary-record links; failed runs remain visible in the record store. The repeatable deployment command builds a 49.8 MB Linux arm64 ZIP that expands to 137 MB and contains the required root `app.py`. No AgentCore runtime has been created yet: the live deployment check stopped because the VPS identity cannot read `/page47/agentcore/execution-role-arn` from SSM.

The resident console is supervised by systemd on Lightsail and reads the live Seattle and Denver stores, shows the current ledger, supports watch setup, and opens captured documents. A temporary validation route exists on the existing TLS host, but no public demo URL is claimed here; a separate domain will be connected before launch.

## What Page 47 does not do

Page 47 reports public records. It does not determine why a change was made, claim that anyone intended to hide information, or make a legal finding. A record that was never published is outside what this tool can see.

## Run it

Use Python 3.12 or newer:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/preflight.py --config config/preflight.json --output docs/preflight.json
python scripts/snapshotter.py --config config/cities/seattle.yaml
python scripts/backfill.py --config config/cities/seattle.yaml --database runtime/records/seattle.sqlite3 --evidence-root runtime/evidence/seattle
pytest
```

The preflight command performs bounded live discovery and stores the public responses used for its report. The snapshotter stores runtime evidence under the configured storage root. Do not add credentials to this repository; AWS credentials belong in the instance role or an AWS secret service.

## Evidence and records

- [Preflight report](docs/preflight.json)
- [Preflight audit](docs/audits/phase-0.md)
- [Snapshotter audit](docs/audits/phase-1.md)
- [Historical record audit](docs/audits/phase-2.md)
- [Consent calibration audit](docs/audits/phase-3.md)
- [Seattle configuration](config/cities/seattle.yaml)
- [AWS discovery response cache](docs/evidence/preflight/index.json)

The preflight report identified eight clients that met the bounded structural checks. Seattle is selected because its sampled records were viable and its observed history reached 2015. The exact historical boundary will be measured during backfill rather than inferred from a small sample.

## Next work

The remaining work is to grant the deployment identity read/write access to the two AgentCore SSM parameters and `iam:PassRole` for a least-privilege execution role, create the managed runtime, and switch the Lightsail service to it. SES still needs a verified sender and its SSM values; the code now includes a private watch-management link in each delivered message. CloudWatch logs, a missed-run alarm, and a viewable OpenTelemetry trace still need configuration. A separate public domain is still pending. Denver needs deeper record and document coverage. Finally, the hand-labelled comparison must run over the same matters for keyword alerts, search, latest-document reading, and Page 47; its results and every miss remain unpublished until review.

## Tests

The current suite has 22 tests. It replays captured real Legistar responses offline, verifies duplicate suppression and changed-copy detection, checks city-specific placement, validates stored matter history, checks page-linked document reading, validates the managed-runtime request, checks public-path links, checks private watch stopping, and checks review email links. Lightsail applies newly captured event details to the record store, reads changed PDFs, and refreshes Seattle PDF placement. Core source passes `mypy --strict` and `ruff check` in the Python 3.12 Lightsail environment.

## Limitations

The public API only exposes records marked public and viewable on the city site. Its last-published timestamp can overwrite earlier publication times; a PDF can be replaced at the same URL; intermediate modifications and deleted attachments leave no historical record. The running snapshotter preserves those forward-looking observations, but it cannot reconstruct what was lost before it started. Seattle's API consent integer is not used: Page 47 reads a captured agenda PDF, records the page supporting a matched title, and says it cannot determine placement when the PDF or match is unavailable. Denver's mapping is valid only for Denver's recorded calibration. Address matching is limited to street, neighbourhood, and council-district evidence and says when an area could not be confirmed.
