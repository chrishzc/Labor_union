# DS-02 independent CI verification

Result: **passed**. The same four mixed-assignment tests pass with the fixed component and fail with the original candidate specifically because it displays the selected person's formal amount instead of the assignment-review hint.

- [Run 45992195244, attempt 1](https://github.com/chrishzc/Labor_union/actions/runs/45992195244/attempts/1) — success.
- Actual checkout: `207daf6e5ea16b2a84671eafbf616bd9a2c603e5`.
- Source commit: `af37823d98e994cdf0412fcb2660d1725a1b6704`, parent `252195342a168fd7e49daaabab12c892bd91ae70`.
- Source tree `65125bb860417d5f3b18e27a48f9887eaad2c695` exactly equals the supplied snapshot plus the complete fixed patch, including both verified documents.
- Original candidate component: `39c423f6c36563008d361954932e60ccee174fc5`.
- Fixed component: `a66ea80cfad3da6da082169ad880e114c18da2e2`.
- Same official test file, lockfile, dependency install and Node v24.22.3; only component bytes differ.
- [Original seven-file CI artifact](https://github.com/chrishzc/Labor_union/actions/runs/45992195244/artifacts/15193897848), SHA256 `fc6db1b8da9bf593c86c9253dc67e7b658f538f30e9b7198be6ef076ac49575e`. Downloaded, hash-verified and independently read back.

| Exact test name | Fixed | Original candidate |
|---|---|---|
| 同人混合指派 'needs_review'，未建帳列先回 false 時不顯金額，移除後才顯示 | passed | failed as expected |
| 同人混合指派 'needs_review'，未建帳列先回 true 時不顯金額，移除後才顯示 | passed | failed as expected |
| 同人混合指派 'not_established'，未建帳列先回 false 時不顯金額，移除後才顯示 | passed | failed as expected |
| 同人混合指派 'not_established'，未建帳列先回 true 時不顯金額，移除後才顯示 | passed | failed as expected |

Each old failure expects `請核對本案指派` and instead receives `月嫂編號 42 · 正式應付 NT$ 48,000 · 付款日 待確認` at the existing test's review-hint assertion. The helper validates four executed cases in both JSON and JUnit, the exact status/order combinations, and the expected failure text; an installation error, missing fixture, skipped test or arbitrary nonzero exit cannot pass the oracle.

In every fixed case, the positive control removes only assignment 99, then restores the original NT$ 48,000 display with an unknown due date. Exactly two accounting GETs, no POST, no synchronize/supplement and no onSaved are asserted. Old cases fail before that downstream positive control, so no claim is made that those downstream assertions ran in the old group. Acceptance changes: none. Runner/fixture repairs: none.

Strict `tsc -p tsconfig.app.json --strict --noEmit --incremental false --pretty false` and focused oxlint of the component and official test both passed on the same GitHub runner. Other runtime tests were filtered out; this result does not claim the whole file or suite passes. Browser, live backend/network, DB, deployment and production behavior remain unverified. No local project tests ran.

This is an independent verification branch, not a second blind implementation result. The CI triggers only on this exact branch and only when its three runner files change. No PR or merge was created; #439, #447, main, existing workflows and merge gates were not modified.

[Detailed provenance and scope](evidence.json), [raw oracle report](oracle-report.json), [fixed JUnit](fixed.xml), [old JUnit](old.xml). All three raw report files preserve the downloaded artifact bytes. Fixed pstack sources were read at `03fffdb6b6f3ff595959f027e0511acbd95123f3`; no host installation/configuration change is claimed. Remaining blockers: none.

Readback note: the source/runner diff passes `git diff --check`. The final evidence diff reports eight trailing-space lines in `old.xml` from Vitest's DOM diagnostic. They are preserved intentionally so the retained JUnit bytes match the original artifact; no code/test whitespace issue is present. All five evidence files were read back from GitHub; the three original result/JUnit files also passed a byte-for-byte Git object comparison against the downloaded artifact.
