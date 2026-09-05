# Page 47

Page 47 helps residents see how a public matter was presented across the meetings where it appeared. It compares the public record over time and links every reported fact back to the city record.

The named primitive is **presentation drift**: the gap between how a matter is described to the public and what the matter actually does, measured across every appearance.

## Current build

The first supported city is Seattle, Washington, on the Granicus Legistar public API. The live preflight sampled 20 events, found 73 event items and 66 attachments, and found records reaching the observed sample boundary of 2015-02-03. Nine Seattle council bodies are recorded in `config/cities/seattle.yaml`.

The snapshotter is running on the Lightsail instance every 15 minutes. Its first clean capture selected five upcoming meetings and stored 30 attachment files plus five agendas. It keeps immutable bytes, SHA-256 hashes, capture times, source URLs, ETags when supplied, and explicit error records.

The historical record is now backfilled for the nine selected Seattle bodies: 1,332 meetings, 24,047 appearances, 25,640 attachment records, and 81 matters with at least three appearances, covering 9 February 2015 through 11 September 2026. The normalized SQLite store is running on Lightsail at `runtime/records/seattle.sqlite3`; all present stored fields carry a source URL and capture time.

The public console and notification service are not live yet. The AWS role currently cannot list Bedrock models or AgentCore runtimes, so the repository records no assumed model ID and does not enable model-dependent work.

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

## Design still to build

Consent placement will not be used until a Seattle agenda PDF is compared with its event-item values and the mapping is recorded with evidence. The public console, notification service, PostgreSQL deployment, historical norms, document reading, and later model work remain to be built. The model work will use the five-node Strands investigation graph, a deterministic evidence rule, and Bedrock on the managed runtime after AWS access is granted.

## Tests

The current suite has 12 tests. It replays captured real Legistar responses offline, verifies duplicate suppression, verifies changed-copy detection, checks the city configuration, reads published agenda text, and exercises the record store with recorded matters and event items. Lightsail applies newly captured event details to the record store before refreshing Seattle PDF placement. Core source passes `mypy --strict` and `ruff check` in the Python 3.12 Lightsail environment.

## Limitations

The public API only exposes records marked public and viewable on the city site. Its last-published timestamp can overwrite earlier publication times; a PDF can be replaced at the same URL; intermediate modifications and deleted attachments leave no historical record. The running snapshotter begins preserving those forward-looking observations now, but it cannot reconstruct what was lost before it started. Seattle's API consent integer is not used: Page 47 reads a captured agenda PDF, records the page supporting a matched title, and says it cannot determine placement when the PDF or match is unavailable. Address matching will be limited to street, neighbourhood, and council-district evidence and will say when an area could not be confirmed.
