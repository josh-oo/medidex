# Synthetic seed data

`synthetic_seed.sql` creates deterministic demo data for a fresh Medidex resource database.
It contains the complete set of explicit titles, abstracts, IDs, and relationships; startup
does not generate any data.

- 100 studies with IDs in the `1000001`-`1000100` range.
- An uneven set of 242 reports: many studies have one report, while a small number have 10 or more, including protocol, results, follow-up, and correction/retraction-style records.
- [`sample_reports.ris`](sample_reports.ris) contains five newest reports from distinct studies for upload testing; those reports are intentionally excluded from the seed.
- Study/report links and provenance rows required by the backend repositories.
- Linked conditions, interventions, outcomes, designs, and participant groups.

During loading, the seed normalizes the corpus for RCT-focused workflows: study
comparisons use concise, varied `Control: ... vs Intervention: ...` labels, the
linked study and report designs are normalized to parallel-group randomized
controlled trials, and every report abstract identifies the underlying randomized
trial, comparator, and linked intervention. Secondary analyses, protocols, and
implementation records remain distinct report types but all originate from that
same realistic trial context. Report titles use varied RCT-style openings rather
than a single repeated phrase. Trial registration identifiers are shared within a
study and intentionally present on only a subset of reports.

The SQL creates the study/report/aspect tables when they are absent and leaves an existing
resource schema unchanged. Every data row is explicit and uses `ON CONFLICT DO NOTHING`,
so repeated startup is idempotent.