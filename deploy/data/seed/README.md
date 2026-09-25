# Synthetic seed data

`synthetic_seed.sql` creates deterministic demo data for a fresh Medidex resource database.
It contains the complete set of explicit titles, abstracts, IDs, and relationships; startup
does not generate any data.

- 100 studies with IDs in the `1000001`-`1000100` range.
- An uneven set of 210 reports: most studies have one or two reports, while a smaller number have three or four, including protocol, results, follow-up, and correction/retraction-style records.
- `pdfs/` contains one dummy PDF per seeded report. Each file contains the report title and abstract and is named by its zero-padded `ReportNumber`. `ReportNumber` is assigned as a globally unique, sequential value (`1`-`210`) matching insertion order, since the backend uses it as the PDF filename lookup key.
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

## Schema: direct vs. adapted

`synthetic_seed.sql` creates its tables (`report`, `study`, `study_report`, ...) directly
under the generic snake_case names `app/backend/src/database/models.py` expects — this
dataset is ours end to end, so there's no domain-specific naming to translate.

`views.sql` is a separate, **optional** adapter for the case where `POSTGRES_DB_RESOURCES`
instead points at a real physical schema that uses different table/column names — e.g. a
Cochrane-style CRG/CENTRAL database (`tblReport`, `tblStudy`, ...; see
[`ops/tools/scripts/prepare_database.py`](../../../ops/tools/scripts/prepare_database.py)
for the tool that produces one from an `.mdb` export). It creates views named after the
application's schema that re-expose that other schema's data, so the application never has
to know about it. It is not tied to `synthetic_seed.sql` and does not run against it.

It is disabled by default. To enable it:

1. Edit `views.sql` so its `CREATE VIEW` statements reference your actual physical
   table/column names (the file documents each mapping; adjust as needed).
2. Set `APPLY_SCHEMA_VIEWS=true` in [`schema-adapter.conf`](schema-adapter.conf) (read by
   `ops/app-init/init.sh` on every `app-init` run).
3. Don't mount `synthetic_seed.sql` for that database — it's demo data and isn't meant to
   be loaded on top of a real physical schema.

See `ops/app-init/init.sh` (section "2b. CONVENTIONAL-NAMING VIEWS") for exactly how the
flag is read and applied.