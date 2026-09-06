from pathlib import Path

page_path = Path('ui_react/src/pages/OrdersPage.tsx')
text = page_path.read_text(encoding='utf-8')

old_card = '''              ) : isOrderIntakeIncomplete(order) ? (
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
              ) : (
              <div className="order-card-actions">
                <button
                  className="btn-secondary-action"
                  data-control-id="orders.card.contract-workbench"
                  onClick={() => handleOpenContractDrawer(order, 'contract_terms')}
                >
                  📑 條款與契約
                </button>

                <button
                  className="btn-primary-action"
                  data-control-id="orders.card.matching-workbench"
                  onClick={() => handleOpenMatchingDrawer(order)}
                >
                  👩‍🍼 媒合與正式排班
                </button>
              </div>
              )}'''
new_card = '''              ) : (
              <div className="order-card-actions">
                {isOrderIntakeIncomplete(order) && (
                  <div role="status" data-surface-id="orders.card.intake-incomplete">
                    ⚠️ 進件資料仍有缺漏；可進入原訂單工作台查看缺件、owner blocker 與目前適用流程。
                  </div>
                )}
                <button
                  className="btn-secondary-action"
                  data-control-id="orders.card.contract-workbench"
                  onClick={() => handleOpenContractDrawer(order, 'contract_terms')}
                >
                  📑 條款與契約
                </button>

                <button
                  className="btn-primary-action"
                  data-control-id="orders.card.matching-workbench"
                  onClick={() => handleOpenMatchingDrawer(order)}
                >
                  👩‍🍼 媒合與正式排班
                </button>
              </div>
              )}'''
assert text.count(old_card) == 1, text.count(old_card)
text = text.replace(old_card, new_card, 1)

old_early_return = '''    if (isOrderIntakeIncomplete(order) && renderIntakeRepair) {
      setDrawerLoading(false);
      return;
    }
    loadCardProjection(order.id);'''
new_early_return = '''    loadCardProjection(order.id);'''
assert text.count(old_early_return) == 1, text.count(old_early_return)
text = text.replace(old_early_return, new_early_return, 1)

old_drawer_start = '''        {(contractOrder || dateConfirmOrder) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {isOrderIntakeIncomplete((contractOrder || dateConfirmOrder)!) && renderIntakeRepair ? (
              renderIntakeRepair((contractOrder || dateConfirmOrder)!, async () => {
                await fetchOrderSummaries();
                closeContractDrawer();
              })
            ) : (
              <>
            {renderCardProjection()}'''
new_drawer_start = '''        {(contractOrder || dateConfirmOrder) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
            {isOrderIntakeIncomplete((contractOrder || dateConfirmOrder)!) && renderIntakeRepair && (
              <section
                aria-label="訂單缺件補齊"
                data-surface-id="orders.drawer.intake-repair"
              >
                {renderIntakeRepair((contractOrder || dateConfirmOrder)!, async () => {
                  await fetchOrderSummaries();
                })}
              </section>
            )}
            {renderCardProjection()}'''
assert text.count(old_drawer_start) == 1, text.count(old_drawer_start)
text = text.replace(old_drawer_start, new_drawer_start, 1)

old_drawer_end = '''            )}
              </>
            )}
          </div>'''
new_drawer_end = '''            )}
          </div>'''
assert text.count(old_drawer_end) == 1, text.count(old_drawer_end)
text = text.replace(old_drawer_end, new_drawer_end, 1)
page_path.write_text(text, encoding='utf-8')

real_data_path = Path('ui_react/src/tests/orders_page_real_data.test.tsx')
real_data = real_data_path.read_text(encoding='utf-8')
old_title = "it('opens incomplete intake repair inside the existing Orders drawer', async () => {"
new_title = "it('adds intake repair to the existing Orders drawer without replacing owner workflows', async () => {"
assert real_data.count(old_title) == 1
real_data = real_data.replace(old_title, new_title, 1)
old_assertions = '''    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();
    const intakeButton = screen.getByRole('button', { name: '補齊進件資料' });
    fireEvent.click(intakeButton);

    expect(await screen.findByRole('region', { name: 'drawer intake repair' })).toHaveTextContent('ORD-2026-0801');
    expect(renderIntakeRepair).toHaveBeenCalled();
    expect(ordersQueryClient.getOrderTerms).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: '📑 契約簽署與約定條款' })).not.toBeInTheDocument();'''
new_assertions = '''    expect(screen.queryByRole('region', { name: '訂單缺件補齊' })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '👩‍🍼 媒合與正式排班' }).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole('button', { name: '📑 條款與契約' })[0]);

    expect(await screen.findByRole('region', { name: 'drawer intake repair' })).toHaveTextContent('ORD-2026-0801');
    expect(renderIntakeRepair).toHaveBeenCalled();
    await waitFor(() => expect(ordersQueryClient.getOrderTerms).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: '📑 契約簽署與約定條款' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '📅 實質服務日曆與天數精算' })).toBeInTheDocument();'''
assert real_data.count(old_assertions) == 1, real_data.count(old_assertions)
real_data = real_data.replace(old_assertions, new_assertions, 1)
real_data_path.write_text(real_data, encoding='utf-8')

entry_path = Path('ui_react/src/tests/order_intake_completion_entry.test.tsx')
entry = entry_path.read_text(encoding='utf-8')
assert entry.count('>補齊進件資料</button>') == 1
entry = entry.replace('>補齊進件資料</button>', '>📑 條款與契約</button>', 1)
assert entry.count("{ name: '補齊進件資料' }") == 2
entry = entry.replace("{ name: '補齊進件資料' }", "{ name: '📑 條款與契約' }", 2)
entry_path.write_text(entry, encoding='utf-8')
