# Validation and proof pack

## Measured scope

The supplied case has no independent attack ground-truth labels. The comparison below evaluates a narrower question Finance can check against the source fields. It measures whether a matched API vendor change merits bank-field review under the announced contact sync. It does not estimate the probability of compromise or measure incident-wide detection accuracy.

| Reviewed reference class | Raised for bank review | Cleared by the bank-field rule |
|---|---:|---:|
| Bank-account change with empty approval, 1 | 1 | 0 |
| Announced email or phone updates, 70 | 0 | 70 |

The reviewed subset comprises all 71 E19 API changes in the supplied pack. The other 296 E19 records came through UI or import channels and fall outside this detector. False alarms against the 70 contact controls were 0/70. Missed bank-field review targets were 0/1. Labels use the same operational definition as the rule. This is a reproducibility check with one positive example. A contact update could still be abusive, and an empty approval field could omit a real approval. Obtain independent investigator labels before interpreting precision or recall as attack-detection performance.

## Rule coverage

| Rule | Required observations and decision | Baseline results |
|---|---|---:|
| R01 | A register entry and log identify the same credential inside the same system. | 1 |
| R02 | A joined bank write exceeds the announced contact-field change and lacks a recorded approval. | 1 |
| R03 | The registered LedgerOne all-module scope exceeds the modules named in the onboarding request. | 1 |
| R04 | A joined email or phone write falls within the vendor’s announced contact sync after its effective date. | 70 |
| R05 | A ticket read and a later storage read involve a key mentioned in chat. The transfer mechanism is unobserved. | 1 |
| R06 | A successful vendor PATCH and an API change share a unique request ID, vendor, field family, credential, address and UTC timestamp. | 71 |
| R07 | A user’s finance export and the integration’s export use different recorded principals and a separately documented audit context. | 1 |
| R08 | Expose missing proof or unavailable source coverage. | 0 |
| R09 | A registered HelpDeskr integration downloaded a created export from a vendor-listed high-confidence IP in its stated UTC date window. | 5 |
| R10 | An export deletion returned an error. A final deletion receipt is needed to determine its later state. | 1 |
| R11 | A registered LedgerOne key downloaded an export from an E17 high-confidence address within its stated date range. | 2 |
| R12 | A build-labelled flow and API request share source address, destination system and UTC day. Candidate only. | 3 |
| R13 | Distinct successful August export creations reconcile to the reviewed E06 invoice count. | 1 |

Each result has a stable rule-and-anchor ID, a complete set of witness locators and independent directions for H1, H2 and H3. A missing direction is neutral. Supporting and contradicting observations yield MIXED. Only supporting observations yield SUPPORTED BY EVIDENCE. Only contradictions yield CONTRADICTED. No directional result yields UNRESOLVED. A complete absence of eligible inputs yields NOT EVALUATED. Recomputing can find an alternative witness, which is reported as a changed result.

## Inclusion and uncertainty

- Read original files without writing to them. Inventory every supplied item by filename, SHA-256, row count, columns and quality flags. A CSV missing a required schema column is unavailable. Extra named columns remain available for inspection.
- Retain good observations without an applicable rule in the index. Their admission does not imply an incident finding.
- Quarantine missing required values, invalid times, invalid identifiers or IPs, negative byte counts and conflicting natural IDs. Structurally malformed rows have a rejection reason. A repeated identical keyed row remains visible as DUPLICATE.
- A missing optional BlueVault IP or SSO device yields PARTIAL. Rules using other known attributes can still run. Active roster rows with termination dates are AMBIGUOUS and remain outside automated conclusions.
- An unavailable source is visible in the source index. Hash checking binds the reviewed PDF pages and Excel sheet rows to the original bytes. Treat changed documents as new review work.
- E02 and E13 local time are interpreted as IST. E17 indicator windows use UTC calendar dates as an explicit comparison assumption. The same HelpDeskr export sequence has ten jobs, of which five meet R09 under that convention. The other five remain visible. A date match with a different timezone could change coverage.
- E04 describes current configuration. The identified credential, snapshot scope, historical authorization and human operator are different claims. E05 clock drift is uncalibrated. E15 build-host labels come from the vendor. Shared IP and time produce candidate leads only.
- E20 lookups use a validated client version or a typed IP-range match. The offline cache returns the saved source, date, matched key, match basis, page and retrieval time. Repeated requests reuse the cached result. Sources without a justified match return no context. Case section 11 limits work to supplied data and the simulation.
- The demo evaluates predefined relationships. Free-text chat interpretation uses a narrow case-specific predicate. New authorization formats, new event types or new documents need reviewed mappings. The system does not claim general language understanding.

## Reproduce

Run the command below from the project root.

```sh
python -B -m unittest discover -s tests -v
```

The tests exercise real evidence, missing files, changed documents, duplicate IDs, timestamp parsing, missing attributes, address and actor conflicts, support aggregation, candidate links, external-context exclusion, replacement IDs and dependency challenges. The core bank rule also runs on fresh request and vendor identifiers through the full evaluator. Lack of a finance approval record cannot establish criminal intent.

**Challenge examples.** Removing E18 turns 71 joined changes into unresolved pairs. Removing E07 drops the scope-comparison rule. Removing E20 leaves case rule results intact and disables reference lookups. Challenging a single E18 request leaves unrelated operations unchanged.

**Repeat independently.** Filter E19 for API, group by field, then match its request_id column to E18. Compare UTC, vendor, actor and IP, HTTP response, method and endpoint. Read E16 item 7 before assigning a business interpretation. Regenerate the machine-readable report with the dashboard’s Export report action. Compare it with baseline_report.json.
