from pathlib import Path

orders_path = Path('ui_react/src/pages/OrdersPage.tsx')
text = orders_path.read_text(encoding='utf-8')

signature = "export const OrdersPage: React.FC = () => {"
assert text.count(signature) == 1
text = text.replace(
    signature,
    "interface OrdersPageProps {\n"
    "  renderIntakeRepair?: (\n"
    "    order: OrderSummaryCardViewModel,\n"
    "    onChanged: () => Promise<void>,\n"
    "  ) => React.ReactNode;\n"
    "}\n\n"
    "export const OrdersPage: React.FC<OrdersPageProps> = ({ renderIntakeRepair }) => {",
    1,
)

old_card = """              ) : isOrderIntakeIncomplete(order) ? (
                <div className="order-card-actions" role="status">
                  案件仍待補齊姓名、服務日期等進件資料；完成補件後即可操作契約、媒合、排班與取消流程。
                </div>
              ) : ("""
new_card = """              ) : isOrderIntakeIncomplete(order) ? (
                <div className="order-card-actions">
                  <div role="status">
                    案件仍待補齊姓名、服務日期等進件資料；完成補件後即可操作契約、媒合、排班與取消流程。
                  </div>
                  <button
                    type="button"
                    className="btn-secondary-action"
                    data-control-id="orders.card.intake-repair"
                    onClick={() => handleOpenContractDrawer(order, 'contract_terms')}
                  >
                    補齊進件資料
                  </button>
                </div>
              ) : ("""
assert text.count(old_card) == 1
text = text.replace(old_card, new_card, 1)

old_loader = """    loadCardProjection(order.id);

    if (initialTab === 'calendar') {"""
new_loader = """    if (isOrderIntakeIncomplete(order) && renderIntakeRepair) {
      setDrawerLoading(false);
      return;
    }
    loadCardProjection(order.id);

    if (initialTab === 'calendar') {"""
assert text.count(old_loader) == 1
text = text.replace(old_loader, new_loader, 1)

old_drawer_start = """        {(contractOrder || dateConfirmOrder) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {renderCardProjection()}"""
new_drawer_start = """        {(contractOrder || dateConfirmOrder) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {isOrderIntakeIncomplete(contractOrder || dateConfirmOrder) && renderIntakeRepair ? (
              renderIntakeRepair(contractOrder || dateConfirmOrder, async () => {
                await fetchOrderSummaries();
                closeContractDrawer();
              })
            ) : (
              <>
            {renderCardProjection()}"""
assert text.count(old_drawer_start) == 1
text = text.replace(old_drawer_start, new_drawer_start, 1)

old_drawer_end = """            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrdersPage;"""
new_drawer_end = """            )}
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default OrdersPage;"""
assert text.count(old_drawer_end) == 1
text = text.replace(old_drawer_end, new_drawer_end, 1)
orders_path.write_text(text, encoding='utf-8')

management_path = Path('ui_react/src/pages/OrdersManagementPage.tsx')
management = management_path.read_text(encoding='utf-8')
marker = 'export const OrdersManagementPage: React.FC = () => {'
start = management.index(marker)
replacement = '''export const OrdersManagementPage: React.FC = () => {
  const [repairItems, setRepairItems] = useState<OrderSummaryItem[]>([]);

  useLayoutEffect(() => subscribeOrderSummarySnapshots(({ page, params }) => {
    if (params.lifecycle_scope !== 'unfinished' || params.query_text || params.after_case_no) return;
    setRepairItems(page.items.filter(needsIntakeRepair));
  }), []);

  return (
    <OrdersPage
      renderIntakeRepair={(order, onChanged) => {
        const item = repairItems.find((candidate) => candidate.case_no === order.id);
        return item ? (
          <IntakeRepairCard item={item} onChanged={onChanged} />
        ) : (
          <div role="status">正在讀取此案件的最新缺件資料…</div>
        );
      }}
    />
  );
};

export default OrdersManagementPage;
'''
management = management[:start] + replacement
management_path.write_text(management, encoding='utf-8')

test_path = Path('ui_react/src/tests/orders_page_real_data.test.tsx')
test = test_path.read_text(encoding='utf-8')
insertion = '''

  it('opens incomplete intake repair inside the existing Orders drawer', async () => {
    const renderIntakeRepair = vi.fn((order: { id: string }) => (
      <section aria-label="drawer intake repair">補件案件：{order.id}</section>
    ));

    render(<OrdersPage renderIntakeRepair={renderIntakeRepair} />);
    await screen.findByText('ORD-2026-0801');

    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();
    const intakeButton = screen.getByRole('button', { name: '補齊進件資料' });
    fireEvent.click(intakeButton);

    expect(await screen.findByRole('region', { name: 'drawer intake repair' })).toHaveTextContent('ORD-2026-0801');
    expect(renderIntakeRepair).toHaveBeenCalled();
    expect(ordersQueryClient.getOrderTerms).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '📑 契約簽署與約定條款' })).not.toBeInTheDocument();
  });
'''
head, tail = test.rsplit('\n});', 1)
test_path.write_text(head + insertion + '\n});' + tail, encoding='utf-8')

entry_path = Path('ui_react/src/tests/order_intake_completion_entry.test.tsx')
entry = entry_path.read_text(encoding='utf-8')
old_mock = '''vi.mock('../pages/OrdersPage', async () => {
  const ReactModule = await import('react');
  const queryModule = await import('../api/orders/order_query_client');
  return {
    OrdersPage: () => {
      ReactModule.useEffect(() => {
        void queryModule.loadAllOrderSummaries(
          queryModule.ordersQueryClient.getOrderSummaries.bind(queryModule.ordersQueryClient),
          { page_size: 200, lifecycle_scope: 'unfinished' },
        );
      }, []);
      return <div data-testid="legacy-orders-page">legacy orders workbench</div>;
    },
  };
});'''
new_mock = '''vi.mock('../pages/OrdersPage', async () => {
  const ReactModule = await import('react');
  const queryModule = await import('../api/orders/order_query_client');
  const adapterModule = await import('../adapters/orders/order_summary_adapter');
  return {
    OrdersPage: ({ renderIntakeRepair }: {
      renderIntakeRepair?: (
        order: ReturnType<typeof adapterModule.adaptOrderSummaryItem>,
        onChanged: () => Promise<void>,
      ) => ReactModule.ReactNode;
    }) => {
      const [activeItem, setActiveItem] = ReactModule.useState<
        Awaited<ReturnType<typeof queryModule.loadAllOrderSummaries>>['items'][number] | null
      >(null);
      const [open, setOpen] = ReactModule.useState(false);
      const refresh = ReactModule.useCallback(async () => {
        const page = await queryModule.loadAllOrderSummaries(
          queryModule.ordersQueryClient.getOrderSummaries.bind(queryModule.ordersQueryClient),
          { page_size: 200, lifecycle_scope: 'unfinished' },
        );
        setActiveItem(page.items.find((item) => item.order_status === '待補件') ?? null);
        return page;
      }, []);
      ReactModule.useEffect(() => {
        void refresh();
      }, [refresh]);
      return (
        <>
          <div data-testid="legacy-orders-page">legacy orders workbench</div>
          {activeItem && (
            <button type="button" onClick={() => setOpen(true)}>補齊進件資料</button>
          )}
          {open && activeItem && renderIntakeRepair?.(
            adapterModule.adaptOrderSummaryItem(activeItem),
            async () => {
              await refresh();
              setOpen(false);
            },
          )}
        </>
      );
    },
  };
});'''
assert entry.count(old_mock) == 1
entry = entry.replace(old_mock, new_mock, 1)
entry = entry.replace(
    "    const region = await screen.findByRole('region', { name: '訂單缺件補齊' });",
    "    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();\n"
    "    fireEvent.click(await screen.findByRole('button', { name: '補齊進件資料' }));\n"
    "    const region = await screen.findByRole('article');",
    1,
)
entry = entry.replace(
    "    render(<OrdersManagementPage />);\n\n    fireEvent.change(await screen.findByLabelText('CASE-153 約定服務開始日'), {",
    "    render(<OrdersManagementPage />);\n\n"
    "    fireEvent.click(await screen.findByRole('button', { name: '補齊進件資料' }));\n"
    "    fireEvent.change(await screen.findByLabelText('CASE-153 約定服務開始日'), {",
    1,
)
entry_path.write_text(entry, encoding='utf-8')
