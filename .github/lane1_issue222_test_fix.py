from pathlib import Path

QUERY_TEST = Path("ui_react/src/tests/finance_query_page.test.tsx")
REVIEW_TEST = Path("ui_react/src/tests/finance_source_review_list.test.tsx")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


text = QUERY_TEST.read_text(encoding="utf-8")
text = replace_once(
    text,
    "    if (path.endsWith('/batches/apply')) {\n",
    """    if (path.includes('/manifest')) {
      return importResponse({
        batch_id: 901,
        batch_identity: plan.batch_identity,
        format_id: 'fixture',
        source_file: 'finance.xlsx',
        sheet_name: 'Sheet1',
        header_row: 1,
        source_row_count: plan.counts.source_rows,
        status: 'previewed',
        batch_version: plan.batch_version,
        source_content_digest: plan.source_content_digest,
        classifier_version: plan.classifier_version,
        fingerprint_version: plan.fingerprint_version,
        canonical_row_count: plan.counts.canonical_created,
        occurrence_count: plan.counts.source_rows,
        review_count: plan.counts.manual_review,
        dispatch_event_count: 0,
        reconciliation_receipt_count: 0,
        created_at: '2026-09-07T00:00:00+08:00',
        completed_at: null,
      });
    }
    if (path.includes('/review-rows')) {
      return importResponse({
        items: Array.from({ length: plan.counts.manual_review }, (_, offset) => ({
          row_id: 901 + offset,
          row_identity: `ROW-REVIEW-${901 + offset}`,
          transaction_date: '2026-09-01',
          direction: 'credit',
          amount_ntd: 1000 + offset,
          classification_type: 'client_receipt',
          disposition: 'manual_review',
          reconciliation_status: 'unmatched',
          source_sheet: 'Sheet1',
          source_row: 2 + offset,
          occurrence_count: 1,
          available_actions: [],
          created_at: '2026-09-07T00:00:00+08:00',
        })),
        next_after_row_id: null,
      });
    }
    if (path.endsWith('/batches/apply')) {
""",
    "finance query fixture endpoints",
)
text = replace_once(
    text,
    "  await screen.findByText('可自動入帳', { selector: '.finance-kpi-label' });\n}\n",
    """  await screen.findByText('可自動入帳', { selector: '.finance-kpi-label' });
  await waitFor(() => {
    const item = screen.getByText('待人工確認', { selector: '.finance-kpi-label' }).parentElement;
    expect(item?.querySelector('.finance-kpi-value')?.textContent).not.toBe('—');
  });
}
""",
    "wait for review owner fact",
)
QUERY_TEST.write_text(text, encoding="utf-8")

review = REVIEW_TEST.read_text(encoding="utf-8")
review = review.replace("expect(await screen.findByText('ROW-REVIEW-222')).toBeInTheDocument();", "expect(await screen.findByText(BATCH)).toBeInTheDocument();")
review = review.replace("expect(screen.getByText('ROW-REVIEW-222')).toBeInTheDocument();", "expect(screen.getByText('Sheet1#3')).toBeInTheDocument();")
REVIEW_TEST.write_text(review, encoding="utf-8")
