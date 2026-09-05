# Seattle PDF placement in stored records and findings

## Stored results

Command run on Lightsail:

```text
python scripts/apply_pdf_placements.py --config config/cities/seattle.yaml --database runtime/records/seattle.sqlite3 --evidence-root runtime/evidence/seattle
```

After preserving agenda PDFs for events `6833`, `6847`, `6854`, and `6865`, the store contained 73 PDF-backed matter appearances: 55 consent and 18 regular. Each stored result has the PDF page number and source URL in its field provenance.

## Real finding check

Matter `14765`, the YEW alley-vacation petition, appeared at the Transportation, Waterfront, and Seattle Center Committee on 27 July 2026 and at City Council on 4 August 2026.

- Committee appearance `124621`: regular agenda, page 4, [published committee agenda](https://legistar2.granicus.com/seattle/meetings/2026/7/6833_A_Transportation%2C_Waterfront%2C_and_Seattle_Center_Committee_26-07-27_Committee_Agenda.pdf).
- City Council appearance `124999`: consent calendar, page 8, [published City Council agenda](https://legistar2.granicus.com/seattle/meetings/2026/8/6847_A_City_Council_26-08-04_Full_Council_Meeting_Agenda.pdf).

`page47.findings.placement.compare_placement` returned `moved_to_consent` with the resident-facing sentence: “This item moved from the regular agenda to the consent calendar.” Both cited source URLs came from the stored PDF captures.

Page 47 does not determine why this change was made.

## Ongoing updates

`scripts/apply_captured_events.py` records only event-detail captures whose capture key is not already in the database. In its first live run it added 15 Seattle detail records and 143 appearances, with no parse failures; a repeat run added zero records. The scheduled Lightsail job runs this update before `scripts/apply_pdf_placements.py`, so a newly captured meeting can become a stored appearance without a full historical collection.
