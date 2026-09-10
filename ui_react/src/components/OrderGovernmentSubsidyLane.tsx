import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FC,
} from 'react';
import {
  GOVERNMENT_SUBSIDY_SUBSTATUS_CODES,
  orderGovernmentSubsidyProjectionClient,
  type GovernmentSubsidySubstatusCode,
  type OrderGovernmentSubsidyProjectionPage,
} from '../api/orders/order_government_subsidy_projection_client';

const SUBSTATUS_LABELS: Readonly<Record<GovernmentSubsidySubstatusCode, string>> = {
  claim_lineage_missing: '待確認補助申請',
  draft: '申請草稿',
  submitted: '已送件',
  approved: '已核准',
  partially_paid: '部分入款',
  paid: '已入款',
  pending_review: '溢撥待檢視',
  offset_reserved: '折抵保留中',
  offset_applied: '折抵完成',
  return_payable: '退款待支付',
  partially_returned: '部分退款',
  returned: '退款完成',
};

function formatNtd(value: number): string {
  return `NT$ ${value.toLocaleString('zh-TW')}`;
}

function queryErrorMessage(_error: unknown): string {
  return '補助結算資料暫時無法取得，請重新開啟查詢。';
}

export const OrderGovernmentSubsidyLane: FC<{ expanded?: boolean; onExpandedChange?: (open: boolean) => void }> = ({ expanded, onExpandedChange }) => {
  const [localOpen, setLocalOpen] = useState(false);
  const open = expanded ?? localOpen;
  const setOpen = (value: boolean) => { setLocalOpen(value); onExpandedChange?.(value); };
  const [page, setPage] = useState<OrderGovernmentSubsidyProjectionPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedSubstatus, setSelectedSubstatus] =
    useState<GovernmentSubsidySubstatusCode | null>(null);
  const requestSequence = useRef(0);
  const normalizedSearch = search.trim();

  useEffect(() => {
    if (!open) return undefined;

    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    const controller = new AbortController();

    setLoading(true);
    setError(null);
    setPage(null);

    void orderGovernmentSubsidyProjectionClient.getProjections(
      {
        page_size: 200,
        case_no_search: normalizedSearch || undefined,
        substatus_code: selectedSubstatus ?? undefined,
      },
      { signal: controller.signal },
    )
      .then((data) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setPage(data);
      })
      .catch((caught) => {
        if (controller.signal.aborted || requestSequence.current !== requestId) return;
        setError(queryErrorMessage(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted && requestSequence.current === requestId) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [normalizedSearch, open, selectedSubstatus]);

  const totalCount = page
    ? GOVERNMENT_SUBSIDY_SUBSTATUS_CODES.reduce(
      (sum, code) => sum + page.substatus_counts[code],
      0,
    )
    : 0;

  return (
    <>
      <button
        type="button"
        className={`order-v2-lane ${open ? 'active' : ''}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>
          <strong>政府補助結算支線</strong>
          <small>查看補助申請、入款與結算進度。</small>
        </span>
        <b>{open ? '檢視中' : '開啟'}</b>
      </button>

      {open && (
        <section
          aria-label="政府補助結算支線工作清單"
          style={{ gridColumn: '1 / -1' }}
        >
          <section className="order-v2-toolbar">
            <div>
              <h2>政府補助結算</h2>
              <p>查詢案件的補助申請、核准與入款進度；尚未找到申請資料時會標示待確認。</p>
            </div>
            <div className="order-v2-toolbar-actions">
              <input
                aria-label="搜尋政府補助案件編號"
                value={search}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
                placeholder="搜尋案件編號"
              />
            </div>
          </section>

          <div className="order-v2-subfilters" aria-label="政府補助子狀態篩選">
            <button
              type="button"
              className={selectedSubstatus === null ? 'active' : ''}
              onClick={() => setSelectedSubstatus(null)}
            >
              全部 <strong>{totalCount}</strong>
            </button>
            {GOVERNMENT_SUBSIDY_SUBSTATUS_CODES.map((code) => (
              <button
                type="button"
                key={code}
                className={selectedSubstatus === code ? 'active' : ''}
                onClick={() => setSelectedSubstatus(code)}
              >
                {SUBSTATUS_LABELS[code]} <strong>{page?.substatus_counts[code] ?? 0}</strong>
              </button>
            ))}
          </div>

          {loading && <div className="order-v2-empty">正在查詢補助結算資料…</div>}
          {error && <div className="order-v2-error" role="alert">{error}</div>}
          {!loading && !error && page && page.items.length === 0 && (
            <div className="order-v2-empty">目前沒有符合查詢條件的訂單。</div>
          )}
          {!loading && !error && page?.next_cursor != null && (
            <div className="order-v2-summary-warning" role="status">
              補助結果超過單次查詢上限；目前顯示前 200 筆，請縮小搜尋或子狀態條件。
            </div>
          )}

          {!loading && !error && page && page.items.length > 0 && (
            <div className="order-v2-case-grid">
              {page.items.map((item) => (
                <article className="order-v2-case-card" key={item.case_no}>
                  <div className="order-v2-case-topline">
                    <strong>{item.case_no}</strong>
                    <span className="order-v2-status">
                      {SUBSTATUS_LABELS[item.substatus_code]}
                    </span>
                  </div>

                  <dl className="order-v2-business-summary">
                    <div><dt>身分類別</dt><dd>{item.identity_status ?? '尚待確認'}</dd></div>
                    <div><dt>申報時數</dt><dd>{item.claimed_hours} 小時</dd></div>
                    <div><dt>補助單價</dt><dd>{item.unit_price_ntd === null ? '尚無／多費率' : formatNtd(item.unit_price_ntd)}</dd></div>
                  </dl>

                  <div className="order-v2-case-meta">
                    <span>申請：{formatNtd(item.requested_amount_ntd)}</span>
                    <span>核准：{formatNtd(item.approved_amount_ntd)}</span>
                    <span>已入款／折抵：{formatNtd(item.net_allocated_ntd)}</span>
                    {item.overpayment_remaining_ntd !== null && (
                      <span>待處置溢撥：{formatNtd(item.overpayment_remaining_ntd)}</span>
                    )}
                    {item.occurred_at && (
                      <span>資料時間：{new Date(item.occurred_at).toLocaleString('zh-TW')}</span>
                    )}
                  </div>

                  {item.blockers.length > 0 && (
                    <div className="order-v2-notice blocked">
                      <strong>阻塞</strong>
                      <span>補助資料尚有待處理項目，請核對申請與入款紀錄。</span>
                    </div>
                  )}
                  {item.warnings.length > 0 && (
                    <div className="order-v2-notice warning">
                      <strong>提醒</strong>
                      <span>此案件的補助資料需要進一步確認。</span>
                    </div>
                  )}

                  <div className="order-v2-case-meta" aria-label="Government Subsidy 唯讀入口">
                    <a href="#reports">前往營運與補助報表</a>
                    <details><summary>技術詳情與資料來源</summary>
                      <p>Owner：{item.source.owner}；Source：{item.source.identity ?? '無'}；Version：{item.source.version ?? '無'}；Claim batch：{item.claim_batch_id ?? '無'}</p>
                      {[...item.blockers, ...item.warnings].map((notice) => <p key={notice.code}>{notice.code}：{notice.message}</p>)}
                    </details>
                    {item.available_read_actions.length > 0 && (
                      <details>
                        <summary>查詢來源</summary>
                        {item.available_read_actions.map((action) => (
                          <span key={action.action_id}>{action.action_id}</span>
                        ))}
                      </details>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
};

export default OrderGovernmentSubsidyLane;
