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

function queryErrorMessage(error: unknown): string {
  const detail = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : '無法取得正式完全結案投影';
  return `完全結案唯讀 projection 查詢失敗；不使用前端推導。原因：${detail}`;
}

export const OrderTerminalAggregateLane: FC = () => {
  const [open, setOpen] = useState(false);
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
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
      >
        <span>
          <strong>完全結案彙總</strong>
          <small>正式 server aggregate；僅顯示完成狀態與缺失組件。</small>
        </span>
        <b>{open ? '檢視中' : '開啟'}</b>
      </button>

      {open && (
        <section aria-label="完全結案彙總工作清單" style={{ gridColumn: '1 / -1' }}>
          <section className="order-v2-toolbar">
            <div>
              <h2>完全結案</h2>
              <p>只讀取 server aggregate；未完成時保留負責 owner 與正式原因。</p>
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

          {loading && <div className="order-v2-empty">正在查詢完全結案 aggregate…</div>}
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
                        <strong>所有必要組件已完成。</strong>
                      </div>
                    ) : (
                      <div className="order-v2-notice blocked">
                        <strong>未完成組件</strong>
                        {incomplete.map((component) => (
                          <span key={component.code}>
                            {component.owner} · {component.code}：{component.reason ?? '未完成'}
                          </span>
                        ))}
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
