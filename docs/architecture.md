# Architecture and limits

## Components

| Component | Implementation |
|---|---|
| Case admission | Schema-specific CSV, JSON and reviewed document extracts. Originals preserved under backend/evidence |
| Case analysis | Existing typed entity index, deterministic rules and witness references. Cached excluded-evidence analyses are independent of writes to the local vault |
| Synthetic exercises | Fixed and customizable fixtures, explicit role policies, immutable event batches and a separate review trail |
| Upload admission | CSV and JSON parsers, openpyxl workbook rows, pypdf text extraction, SHA-256 original-byte checks and row-level review notes |
| Persistence | SQLite initializes on startup. Separate tables store original uploads, extracted observations, upload reviews, exercise runs and exercise review records |
| Reports | ReportLab PDF, structured JSON and spreadsheet-safe CSV export. Reports include the challenge state and selected run |
| Interface | Native browser UI served on the same loopback origin as the Python API |

A case evidence challenge reevaluates the case rules on the active subset and diffs it against the baseline. Synthetic dependency analysis follows its own explicit rule prerequisites. Removing the permission snapshot withdraws the permission-based results, while a request-to-decision relationship can still be supported by the remaining records.

## Boundaries and future work

- Demo identity selection provides an immediately repeatable access-control fixture. A production deployment would need authenticated investigators, permissions for administrative actions and protected storage.
- Arbitrary uploads are preserved, indexed, reviewable and exportable. Mapping new vendor schemas to the case rules requires review. The app does not assert case joins from names, uploaded timestamps or keyword matches.
- PDF intake supports extractable text. Image-only pages require transcription or a future OCR step. Uploads are limited to 10 MiB and 5,000 parsed records. Source metadata reports an indexing limit when it is reached.
- External references are links and supplied E20 excerpts. Live external connectors, automatic retrieval and AI summaries are outside this local prototype.
- Fixture metrics use a small, labelled exercise catalog. They describe test coverage and behavior here. They do not estimate real-world performance or the probability that a person is an attacker.
- Challenge selections and case hypothesis rule scopes live in the current browser tab. Exports capture those selections. Upload originals, review notes and simulation runs persist in the SQLite database.
- The app retains the existing lightweight local HTTP and frontend stack to keep launch and debugging simple. There is no frontend build step.
