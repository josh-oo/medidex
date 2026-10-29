# Synthetic seed data

[`synthetic_database.zip`](synthetic_database.zip) is a deterministic demo database: an exported database
archive (`database.json` and `pdfs/`, see "Study databases" in the main README). The backend never loads it on
its own: import it by hand on the Database management page (name, description and eligibility criteria are in the
file). The ids of studies and reports are those the importing database gives them.

- The database itself, "Synthetic RCT register", with a description and eligibility criteria that match the
  corpus.
- 101 studies with their linked conditions, interventions, outcomes, designs and participant groups.
- An uneven set of 220 reports: most studies have one or two reports, while a smaller number have three or four
  (one has ten), including protocol, results, follow-up, and correction/retraction-style records.
- A dummy PDF for 211 of the reports (9 have none), each containing the report title and abstract. The import
  stores each under the id of its report.

The corpus is normalized for RCT-focused workflows: the `graph` of every study holds its
comparison (its arms, what they receive, their arm types and durations and the comparison between them, see
`config/medidex-study.yaml` and `app/backend/src/utils/graph.py`): both sides
are interventions of the study (the control of each study is an intervention of its own), the
linked study and report designs are normalized to parallel-group randomized
controlled trials, and every report abstract identifies the underlying randomized
trial, comparator, and linked intervention. Secondary analyses, protocols, and
implementation records remain distinct report types but all originate from that
same realistic trial context. Report titles use varied RCT-style openings rather
than a single repeated phrase. Trial registration identifiers are shared within a
study and intentionally present on only a subset of reports.

The import is all or nothing. Importing it twice gives two separate databases.

## Examples

[`examples/`](examples) holds new reports for upload testing, none of them in the database:
[`sample_reports.ris`](examples/sample_reports.ris) with nine reports, and the fulltext PDFs of seven of them
(`Article - ….pdf`).
