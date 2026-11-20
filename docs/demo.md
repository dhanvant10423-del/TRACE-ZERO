# TRACE//ZERO judge walkthrough

## 1. Observe the difference between sign-in and permission

1. Launch the app and choose **Load repeatable demo** on **Overview**. This loads five named runs with stable IDs and opens SIM-DEMO-DENIED.
2. In **Risk Sentinel**, inspect **Baseline session checks**, then **Action outside role**. The baseline result is PASSED. The Support analyst's fictional beneficiary change is RESTRICTED. No banking transaction is performed.
3. In **Decision trail**, inspect the sign-in, permission snapshot, requested operation and decision. Each event has a stable source reference.
4. Use **Open simulation graph** to inspect SIM-01, SIM-02 and SIM-03 and their cited records.

## 2. Challenge the evidence

1. From **Risk Sentinel**, select **Challenge synthetic evidence**.
2. Check **Read permission snapshot**, then choose **Recompute analysis**.
3. H1 changes from SUPPORTED BY EVIDENCE to UNRESOLVED. H2 also becomes UNRESOLVED. H3 retains the exact request-to-decision link. Two relationships lose support and one retains support.
4. Select **Restore all records** to return to the original analysis. This selection changes the derived view. The underlying event trail remains available in the inspector.

## 3. Test legitimate recovery

1. In **Scenario Lab**, select **Authorized beneficiary review**. The Finance identity has permission. Run the fixture to get VERIFY while independent verification is pending.
2. In **Risk Sentinel → Review and recovery**, choose **Verification completed · allow and monitor**, fill the review note, then submit it.
3. Inspect the appended review record. Try the travelling employee fixture to see a baseline flag resolved by verification instead of a complete account lock.
4. Use **Fixture evaluation** to inspect the expected response and observed response for each fixed scenario. The percentages describe these fixtures only.

## 4. Check case and upload evidence

1. Open **Investigation Graph → Case evidence**. Select the R02 bank change, then inspect E18/1088, E19/313 and the operation's approval field. R04 contains routine updates within the announced contact sync.
2. Open **Evidence Vault → Case evidence**, source E03, and search for `r.menon` to view case sign-in records. Staff authorization needs corroboration. Use source E14 to inspect roster context.
3. In **Evidence Vault → Local uploads**, upload an example CSV with the contents below. Use **Verify SHA-256**, then inspect the ambiguous second row and add a review note. Uploading the same bytes again creates a distinct inventory entry linked to the first upload.

```csv
timestamp,actor,action,target
2026-01-15T10:00:00Z,fixture-reviewer,opened,demo-record
2026-01-15T10:01:00,fixture-reviewer,reviewed,demo-record
```

## 5. Export the investigation

Select the desired exercise in **Investigation Reports**. Download the PDF human-readable report, JSON provenance report, and CSV evidence table. Case evidence, upload inventory and simulated results carry distinct origin labels. Export before refreshing if you want to preserve the current challenge selection.
