# Update bundles

An update brings new reports into a study database. Its reports can be uploaded as a RIS or NBIB file, whose PDFs
medidex then searches for, or as an **update bundle**: the reports together with their fulltext PDFs, so that they are
there as soon as the update is created. This page specifies the bundle.

## Layout

A bundle is a zip archive, by convention named `<name>.medidex-update.zip` (an export of a database is
`<name>.medidex.zip`), laid out like the export of a database:

```
update.json        the reports (see below)
pdfs/              their PDFs, each named by the "pdf" of its report
  1.pdf
  2.pdf
  ...
```

- `update.json` lies at the top of the archive.
- A PDF is named by its path in the archive, which starts with `pdfs/` (e.g. `pdfs/36347.pdf`). Any file name below
  `pdfs/` works; a number of the report is the convention.
- Files the reports do not name are ignored.
- `update.json` alone (uploaded as a `.json` file) is a bundle without PDFs.

## update.json

```json
{
  "format": "medidex-update",
  "version": 1,
  "reports": [
    {
      "title": "Efficacy of Targeted Immunotherapy in Advanced Lung Cancer",
      "year": 2023,
      "authors": ["Doe J", "Roe R"],
      "abstract": "Background: ...",
      "journal": "Journal of Clinical Oncology",
      "volume": "41",
      "issue": "3",
      "pages": "112-120",
      "language": "eng",
      "doi": "10.5555/medidex.synthetic.0200",
      "pdf": "pdfs/1.pdf"
    },
    {
      "title": "Trial registration record NCT04267848",
      "year": 2020,
      "trialId": "NCT04267848"
    }
  ]
}
```

| Field | | |
| --- | --- | --- |
| `format` | required | `"medidex-update"` |
| `version` | | `1`, the only version so far (also when left out) |
| `reports` | required | the reports of the update, at least one |

A report:

| Field | Type | |
| --- | --- | --- |
| `title` | text, required | |
| `year` | integer, required | the year of publication |
| `authors` | list of texts | as the source lists them, e.g. `"Doe J"` |
| `abstract` | text | |
| `journal`, `volume`, `issue`, `pages`, `language`, `publisher`, `city` | text | |
| `doi` | text | e.g. `10.1056/NEJMoa2118542`; medidex uses it to search for the PDF when the bundle has none |
| `trialId` | text | a trial registration id, e.g. `NCT04267848`; see below |
| `pdf` | text | the path of its PDF in the archive, e.g. `pdfs/1.pdf`; leave it out for a report without one |

Texts are UTF-8. Line breaks in a title or abstract become spaces. A report has the shape of a report of a database
export, so a report taken from an export can be put into a bundle as it is. Its `id` and `createdAt`, and any other
field not listed here, are ignored.

**Trial ids.** A report with a `trialId` and no `authors` is the record of that trial in a registry rather than a
publication: its PDF, when the bundle has none, is rendered from the registry. The `trialId` of any other report is a
guess that a curator confirms; without one, medidex guesses it from the title and abstract.

## Upload

An admin uploads the bundle as a new update on the card of the database (the web UI sends it in parts with the tus
protocol, so a proxy that limits the size of a request does not stop it; the backend's temporary directory needs room
for the whole file). The REST API takes it at `POST /projects`, either as the `file` of the form or, for a large
bundle, as the `uploadId` of a file uploaded with tus to `POST /databases/uploads`.

- **All or nothing.** A bundle that is not as specified here (e.g. a report without a `year`) or that names a PDF it
  does not contain is rejected with what is wrong, and nothing is stored.
- **One update per set of reports.** An update is identified by its reports (their titles, abstracts and authors, in
  their order), whichever file they come in: a bundle with the same reports as an update uploaded before, also as a RIS
  file, is refused as already uploaded.
- **PDFs.** The PDFs of the bundle are stored with their reports. For the reports without one, medidex searches the PDF
  (by its DOI, or renders the registry record); what it does not find is uploaded by hand on the report.
- The database takes the update only when its last update is merged and it is not being imported or indexed.

## Example

[`deploy/data/seed/examples/sample_reports.medidex-update.zip`](../deploy/data/seed/examples/sample_reports.medidex-update.zip) is the
RIS file of the examples, `sample_reports.ris`, as a bundle with seven of its nine PDFs, to upload into the demo
database.
