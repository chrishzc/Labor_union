import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FC,
} from 'react';
import {
  orderTerminalAggregateClient,
  type OrderTerminalAggregatePage,
} from '../api/orders/order_terminal_aggregate_client';

function queryErrorMessage(_error: unknown): string {
  return '結案資料暫時無法取得，請重新開啟查詢。';
}

function pendingLabel(code: string): string {
  return ({ client_settlement: '客戶帳務尚未結清', government_subsidy: '政府補助尚未完成' } as Record<string, string>)[code] ?? '尚有結案工作待確認';
}

export const OrderTerminalAggregateLane: FC<{ expanded?: boolean; onExpandedChange?: (open: boolean) => void }> = ({ expanded, onExpandedChange }) => {
  const [localOpen, setLocalOpen] = useState(false);
  const open = expanded ?? localOpen;
  const setOpen = (value: boolean) => { setLocalOpen(value); onExpandedChange?.(value); };
  const [page, setPage] = useState<OrderTerminalAggregatePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
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

    void orderTerminalAggregateClient.getAggregates(
      {
        page_size: 200,
        case_no_search: normalizedSearch || undefined,
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
  }, [normalizedSearch, open]);

  return (
    <>
      <button
        type="button"
        className={`order-v2-lane ${open ? 'active' : ''}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span>
          <strong>完全結案彙總</strong>
          <small>查看案件結案狀態與尚待完成的項目。</small>
        </span>
        <b>{open ? '檢視中' : '開啟'}</b>
      </button>

      {open && (
        <section aria-label="完全結案彙總工作清單" style={{ gridColumn: '1 / -1' }}>
          <section className="order-v2-toolbar">
            <div>
              <h2>完全結案</h2>
              <p>查看案件是否已完成所有必要結案項目。</p>
            </div>
            <div className="order-v2-toolbar-actions">
              <input
                aria-label="搜尋完全結案案件編號"
                value={search}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setSearch(event.target.value)}
                placeholder="搜尋案件編號"
              />
            </div>
          </section>

          {loading && <div className="order-v2-empty">正在查詢結案狀態…</div>}
          {error && <div className="order-v2-error" role="alert">{error}</div>}
          {!loading && !error && page && page.items.length === 0 && (
            <div className="order-v2-empty">目前沒有符合條件的正常訂單。</div>
          )}
          {!loading && !error && page?.next_cursor != null && (
            <div className="order-v2-summary-warning" role="status">
              完全結案結果超過單次查詢上限；目前顯示前 200 筆，請縮小搜尋條件。
            </div>
          )}

          {!loading && !error && page && page.items.length > 0 && (
            <div className="order-v2-case-grid">
              {page.items.map((item) => {
                const incomplete = item.components.filter((component) => !component.completed);
                return (
                  <article className="order-v2-case-card" key={item.case_no}>
                    <div className="order-v2-case-topline">
                      <strong>{item.case_no}</strong>
                      <span className="order-v2-status">
                        {item.fully_closed ? '完全結案' : '尚未完全結案'}
                      </span>
                    </div>

                    {item.fully_closed ? (
                      <div className="order-v2-business-summary">
                        <strong>所有必要結案項目已完成。</strong>
                      </div>
                    ) : (
                      <div className="order-v2-notice blocked">
                        <strong>尚有 {incomplete.length} 項結案工作未完成</strong>
                        <a href="#order-workbench-v2">前往待辦看板查看案件進度</a>
                        <ul>{incomplete.map((component) => <li key={component.code}>{pendingLabel(component.code)}</li>)}</ul>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
    </>
  );
};

export default OrderTerminalAggregateLane;
