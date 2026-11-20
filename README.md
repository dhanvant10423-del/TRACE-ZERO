# TRACE//ZERO

TRACE//ZERO combines a synthetic security policy exercise with an evidence-based investigation of CR-26-047 at Harbor & Finch Freight. It runs on a local Python server and bundles the participant evidence. The same launch serves the browser interface and API.

## Start it

Extract the whole archive. On Windows with Python 3.10+ and the Python launcher, double-click **START_TRACE_ZERO.bat**. Keep the terminal open. After indexing, the terminal prints three usernames and freshly generated passwords. Open http://127.0.0.1:8765 and sign in. Restarting rotates the credentials and invalidates sessions. Anyone who controls the server terminal or the project files is a trusted local operator.

### Live authorization demo

1. Sign in as **support**. Request the statement and try to save South Yard Freight. Both operations return HTTP 403. Support can read its own access history.
2. Sign out and sign in as **finance**. Read the statement, save South Yard Freight, then read again. The updated beneficiary comes from SQLite. Finance cannot open case files.
3. Sign in as **investigator**. Inspect all access decisions, then choose **Open investigation workspace** to use the ten investigation views. Investigator access grants no finance permission.
4. Sign out and open /api/overview directly. The server returns HTTP 401. Real authorization uses an opaque, 30-minute HttpOnly session cookie. Changing the selected identity inside Scenario Lab only changes synthetic input.
5. For another run, finance can select North Quay Logistics again. The application never sends payments. The demo statement and beneficiary are synthetic, separate from the supplied case records.

Access endpoints: POST /access/login (username, password), POST /access/logout, GET /access/session, GET /access/activity, GET /access/statement, POST /access/beneficiary (beneficiary), and GET /workspace. POST calls require a same-origin request with X-Trace-Local: 1. The server binds only to loopback. This is a local judge demo. The app cannot guard raw files against someone with operating-system access. A production deployment would require TLS, managed identities and independent audit retention.

From a terminal opened in the extracted project folder:

```sh
python -m pip install -r requirements.txt
python -B -m unittest discover -s tests -v
python -B backend/server.py --open
```

Use `python3` where that is the installed command. Dependency installation can require internet access or locally cached packages. The app runs offline after installation. Press Ctrl+C in the server terminal to stop it. Use `--port 8766` to select another port and `--db "path/to/workbench.sqlite3"` to select a different workspace database. The default database is `backend/data/workbench.sqlite3`.

## Demo in three minutes

1. On **Overview**, choose **Load repeatable demo**. Risk Sentinel opens a saved synthetic exercise. The Support analyst's baseline sign-in passes, while the beneficiary change is restricted because the identity lacks permission.
2. Open the decision trail. Inspect the linked permission snapshot and requested operation. Select **Challenge synthetic evidence** and exclude **Read permission snapshot**. H1 changes to **UNRESOLVED** while the request-to-decision link remains. Restore the record.
3. In **Scenario Lab**, select **Authorized beneficiary review** or **Legitimate employee travelling**. Run the exercise. In **Review and recovery**, document completed verification and allow monitoring. The action and review appear as separate records.
4. Open **Investigation Graph → Case evidence** for the participant case. Select R02 and inspect E18/1088 and E19/313 to trace the bank-account change. Use **Investigation Reports** to download PDF, JSON or CSV.

See [demo guide](docs/demo.md) for exact expected outcomes and a sample upload. The [case brief](docs/investigation.md) and [original prototype validation](docs/validation.md) describe the case-specific analysis. The original slides in `docs/technical_review.pptx` cover the participant case and evidence-dependency design.

## Main areas

| View | Function |
|---|---|
| Overview | Case inventory, hypothesis summary, previous exercises and demo entry point |
| Risk Sentinel | Recorded decision, baseline comparison, role permission, risk, review and labelled fixture metrics |
| Scenario Lab | Fictional identity selection, requested action and editable observation inputs |
| Evidence Vault | Original files, source hashes, indexed rows, admission reasons and review notes |
| Investigation Graph | Clickable case and synthetic record links with rule, status and source references |
| Timeline | Case, upload and simulation event views. Case filters include source, entity, event type, date and relationship |
| Hypothesis Arena | Three case hypotheses, rule scope selection, supporting and contradicting findings, and a synthetic results view |
| Dependency Analysis | Challenge or restore individual records and case sources. Compare changed findings and surviving relationships |
| External Context | Included E20 public-record excerpts and optional reference links |
| Investigation Reports | Evidence-linked PDF and JSON reports, plus CSV evidence table export |

## Project layout

- `backend/` ships the existing CR-26-047 ingestion and reasoning engine, the policy simulator, upload parsing, SQLite schema, report builder and HTTP entry point.
- `frontend/` contains the browser interface. It uses native HTML, CSS, JavaScript and a canvas-based case graph to keep both parts runnable through one offline launcher.
- `docs/` contains evidence references, [architecture](docs/architecture.md), [HTTP API](docs/api.md), demo notes and known limits.
- `tests/` covers case regression, ingest and integrity, simulation, dependency analysis, persistence and exports.

The original CR-26-047 files remain in `backend/evidence/`. Local uploads and synthetic records carry their own source IDs. Uploads require a reviewed source mapping before they can inform case-specific hypotheses. The synthetic identity switch evaluates demo policy and records fixture events. It performs no financial transactions.
