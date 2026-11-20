# Harbor & Finch investigation brief

**Case CR-26-047 · Defensive investigation workbench**

## The decision for Finance

Verify the bank instructions for Coastal Packaging Ltd before releasing a payment to vendor V-0412. LedgerOne records a successful bank-details update on 3 September at 01:44:30 UTC. The vendor change log records the same request, vendor, credential, address and timestamp. Both records identify the operation. The approval reference is empty. Finance should confirm the intended account using its established vendor contact and obtain the approval record. Payment execution and financial loss remain unknown.

| What to inspect | Locator | Recorded value |
|---|---|---|
| Requested operation | E18/1088 | PATCH /v2/vendors/V-0412/bank-details, HTTP 200 |
| Resulting change | E19/313 | Account ending 4417 changed to one ending 9083 |
| Connection identity | E04/integrations[0] | LedgerOne credential key-tb-07, registered to TallyBridge-LedgerOne |
| Announced behavior | E16/p1, item 7 | Vendor announced email and phone synchronization beginning 1 September |
| Shared request | E18/1088, E19/313 | req-5f61b0de8 |

## What else the records support

| Recorded time | Observation | What remains open |
|---|---|---|
| 25 June, local | A support message names a ticket and a storage key together. E13/messages[1]. | A chat statement cannot establish every reader of the ticket. |
| 22 July, 06:19 UTC | A finance user downloaded an export on the same local day as their announced audit. E01/19924 and E13/messages[7]. | Testimony supplies a plausible separate purpose. |
| 11–12 August, HelpDeskr local | A service read the named ticket. Ten export jobs were created by the integration. One delete attempt timed out. E02/19792, E02/19793–19822. | A timeout leaves the later retention state open. The exact collection route to BlueVault remains unverified. |
| 12 August, 03:43 and 03:58 UTC | LedgerOne recorded two export downloads with 9,840 and 9,835 returned records. E01/28250 and E01/28269. The key maps to E04 and both addresses appear in E17. | Record sets could overlap. Their final destination and operator are unknown. |
| 14 August, recorded BlueVault date | The customer portal key read a finance bank-instructions file. E05/6483. | BlueVault has an unsynchronized clock. Minute-level ordering across systems is unreliable. |
| 17–19 August, UTC | Build-labelled private-link flows share a source IP, destination system and day with API activity. See R12. | Host labels come from the vendor. There is no shared flow-to-request ID. |
| August invoice, issued 1 September | Fourteen created jobs reconcile with five included and nine billed at INR 2,500, totaling INR 22,500 before tax. E06/p2 and R13. | Job creation determines billing. The charge alone says nothing about export contents. |
| 1–7 September | Seventy API changes match the announced contact fields. One verified bank-field change falls outside those fields. E16, E18, E19. | The notice describes functionality. A separate, valid approval for the bank change could exist. |

## Why the competing explanations survive

The same registered credential served routine operations and a bank change outside the announced sync. A broad-permission alert would put all 71 writes in the same bucket. A request-level comparison lets an investigator inspect the one write Finance needs to verify. Technical links stop at accounts, credentials and resources. An IP address or matching product name cannot identify a person.

The onboarding request names three LedgerOne modules. The register shows all-module write access. The snapshot supports a scope concern as of its export date. Historical configuration, separate exceptions, vendor-side telemetry, final deletion receipts and bank execution records would materially change what the team can conclude.

## Reproduce the challenge

1. Open the bank-change assessment on the Evidence graph. Inspect E18/1088 and E19/313.
2. In Dependency analysis, select E18 and choose **Recompute scenario**. The bank change remains in E19. The joined interpretation disappears, and the API rows with missing partners appear as gaps.
3. Inspect the surviving August export assessments. Restore the full case.
4. Challenge E16/p1 from the record inspector. The request-to-change link survives. The comparison with the announced September feature drops out.
