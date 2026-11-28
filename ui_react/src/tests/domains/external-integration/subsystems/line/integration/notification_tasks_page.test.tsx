import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationTasksPage } from '../../../../../../pages/NotificationTasksPreviewPage';
import { notificationTasksClient as client, notificationFailure, type NotificationItem, type NotificationPage } from '../../../../../../api/line_notifications/notification_tasks_client';
import { lineDeliveryQueryClient } from '../../../../../../api/line_delivery/line_delivery_query_client';
import { ApiHttpError } from '../../../../../../api/shared/typed_errors';
import { transport } from '../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../api/auth/session_client';

import { hcmResubmissionClient } from '../../../../../../api/case_import/hcm_resubmission_client';

const item=(patch:Partial<NotificationItem>={}):NotificationItem=>({id:'overdue:deposit',source:'overdue',group:'reminder',title:'訂金逾期未清',case_no:'116000001',reference_id:null,
  person:'',summary:'本期未繳 NT$ 3,000',reason:'各期獨立判斷',time:'2026-10-24',tag:'待處理',recipient:'客戶私人聊天室',message:'目前訂金餘額',unavailable_reason:'客戶尚未綁定 LINE',expected_version:null,
  delivery_status:null,payment:{case_no:'116000001',payment_stage:'deposit',obligation_identity:'case1:deposit',projection_version:1,obligation_event_id:10,due_date:'2026-10-24',remaining_amount_ntd:3000},log:null,...patch});
const importSource = {source:'import_fields',label:'進件資料待修正',group:'review',category_id:'applications',category_label:'申請與資料'} as const;
const importTodo = (caseNo:string) => item({
  id:`import_fields:${caseNo}`, source:importSource.source, group:importSource.group,
  title:importSource.label, case_no:caseNo, summary:'2 項欄位問題待修正。',
  reason:'請至客戶名冊核對同案欄位。', recipient:null, message:null, payment:null, unavailable_reason:null, time:'',
  import_field_issues:[
    {source:'client_beclass', owner:'client_profile', field:'email', source_field:'Email',
      code:'client_field_invalid:Email', message:'Email來源資料有誤，請補正此欄位。'},
    {source:'hcm', owner:'order_terms', field:'service_days', source_field:'希望服務天數',
      code:'field_invalid:希望服務天數', message:'希望服務天數尚未完成。'},
  ],
});
beforeEach(()=>{
  window.matchMedia=vi.fn().mockReturnValue({matches:false}) as unknown as typeof matchMedia;
  vi.spyOn(client,'catalog').mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'}]);
  vi.spyOn(client,'list').mockResolvedValue({items:[item()],total:1,next_cursor:null});
  vi.spyOn(lineDeliveryQueryClient,'list').mockResolvedValue({items:[],total:0,page:1,page_size:6,total_pages:1});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();window.history.replaceState(null,'','/');});
describe('通知事項實際接線',()=>{
  it('進件資料待修正在申請與資料逐欄定位同案正式入口',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([importSource]);
    vi.mocked(client.list).mockResolvedValue({items:[importTodo('CASE-1')],total:null,next_cursor:null});
    const send=vi.spyOn(client,'send');
    render(<NotificationTasksPage/>);
    await screen.findByRole('heading',{name:importSource.label});
    expect(screen.queryByRole('button',{name:/款項/})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:/申請與資料/}));
    expect(screen.getByRole('link',{name:/Email來源資料有誤/})).toHaveAttribute('href','#clients?case=CASE-1&field=email&from=workbench');
    expect(screen.getByRole('link',{name:/希望服務天數尚未完成/})).toHaveAttribute('href','#clients?case=CASE-1&field=intake&from=workbench');
    fireEvent.click(screen.getByRole('button',{name:'前往客戶名冊修正'}));
    expect(window.location.hash).toBe('#clients?case=CASE-1&field=email&from=workbench');
    expect(send).not.toHaveBeenCalled();
  });
  it('選填 email 略過須確認，成功讀回後仍保留必修欄位', async () => {
    vi.mocked(client.catalog).mockResolvedValue([importSource]);
    const task = importTodo('CASE-1');
    const issues = task.import_field_issues ?? [];
    const required = issues[1];
    if (!required) throw new Error('Missing required-field fixture');
    task.import_field_issues = [{ source: 'hcm', owner: 'client_profile', field: 'email',
      source_field: 'email', code: 'hcm_field_invalid:email', message: 'email 尚未完成。',
      optional_skip_review_identity: 'review-1' }, required];
    vi.mocked(client.list).mockResolvedValue({items:[task],total:1,next_cursor:null});
    const preview = {review_identity:'review-1',case_no:'CASE-1',source_field:'email',
      review_version:1,preview_fingerprint:'a'.repeat(64)};
    const prepare = vi.spyOn(hcmResubmissionClient,'previewFieldSkip').mockResolvedValue(preview);
    const apply = vi.spyOn(hcmResubmissionClient,'applyFieldSkip').mockResolvedValue({
      event_identity:'event-1',review_identity:'review-1',case_no:'CASE-1',target_fields:['review.skip_field:email'],
      resulting_review_version:2,replayed:false,
    });
    render(<NotificationTasksPage />);
    const button = await screen.findByRole('button',{name:'略過此欄'});
    expect(screen.getAllByRole('button',{name:'略過此欄'})).toHaveLength(1);
    fireEvent.click(button);
    const confirm = await screen.findByRole('button',{name:'確認略過此欄'});
    expect(prepare).toHaveBeenCalledWith('review-1','email',true);
    expect(apply).not.toHaveBeenCalled();
    vi.mocked(client.list).mockResolvedValue({
      items:[{...task,import_field_issues:[required]}],total:1,next_cursor:null,
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByText('email 尚未完成。')).not.toBeInTheDocument());
    expect(screen.getByRole('link',{name:/希望服務天數尚未完成/})).toBeInTheDocument();
    expect(apply).toHaveBeenCalledWith(preview,expect.any(String),true);
  });
  it.each([
    {outcome: '保留必修欄位', hasRequired: true},
    {outcome: '移除已無待修欄位的案件', hasRequired: false},
  ])('第二個來源分頁確認略過 email 後$outcome', async ({hasRequired}) => {
    const caseNo = 'CASE-26';
    const firstPage = Array.from({length: 25}, (_, index) => importTodo(`CASE-${index + 1}`));
    const task = importTodo(caseNo);
    const required = task.import_field_issues?.[1];
    if (!required) throw new Error('Missing required-field fixture');
    const email = {source: 'hcm', owner: 'client_profile', field: 'email', source_field: 'email',
      code: 'hcm_field_invalid:email', message: 'email 尚未完成。', optional_skip_review_identity: 'review-26'} as const;
    const reviewedTask = {...task, import_field_issues: hasRequired ? [email, required] : [email]};
    let applied = false;

    vi.mocked(client.catalog).mockResolvedValue([importSource]);
    vi.mocked(client.list).mockImplementation(async (_source, cursor = 0) => {
      const total = applied && !hasRequired ? 25 : 26;
      if (cursor === 0) return {items: firstPage, total, next_cursor: total > 25 ? 1 : null};
      const items = applied ? (hasRequired ? [{...task, import_field_issues: [required]}] : []) : [reviewedTask];
      return {items, total, next_cursor: null};
    });
    vi.spyOn(hcmResubmissionClient, 'previewFieldSkip').mockResolvedValue({
      review_identity: 'review-26', case_no: caseNo, source_field: 'email', review_version: 1, preview_fingerprint: 'a'.repeat(64),
    });
    vi.spyOn(hcmResubmissionClient, 'applyFieldSkip').mockImplementation(async () => {
      applied = true;
      return {event_identity: 'event-26', review_identity: 'review-26', case_no: caseNo,
        target_fields: ['review.skip_field:email'], resulting_review_version: 2, replayed: false};
    });

    render(<NotificationTasksPage />);
    fireEvent.change(screen.getByRole('searchbox', {name: '搜尋通知事項'}), {target: {value: caseNo}});
    fireEvent.click(await screen.findByRole('button', {name: '載入更多事項'}));
    fireEvent.click(await screen.findByRole('button', {name: '略過此欄'}));
    fireEvent.click(await screen.findByRole('button', {name: '確認略過此欄'}));

    await waitFor(() => expect(screen.queryByText(email.message)).not.toBeInTheDocument());
    if (hasRequired) {
      expect(screen.getByRole('button', {name: new RegExp(caseNo)})).toBeVisible();
      expect(screen.getByRole('link', {name: required.message})).toHaveAttribute('href', `#clients?case=${caseNo}&field=intake&from=workbench`);
    } else {
      expect(screen.getByRole('heading', {name: '沒有符合搜尋條件的事項'})).toBeVisible();
      expect(screen.queryByRole('button', {name: new RegExp(caseNo)})).not.toBeInTheDocument();
    }
  });
  it('進件資料讀取失敗保持未確認，讀回成功後才顯示零筆',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([importSource]);
    vi.mocked(client.list).mockRejectedValue(new ApiHttpError(503,'notification_source_unavailable','此類事項暫時無法讀取，請重新整理。'));
    render(<NotificationTasksPage/>);
    await screen.findByRole('heading',{name:'目前無法完整讀取事項'});
    expect(screen.getByRole('alert')).toHaveTextContent('進件資料待修正');
    expect(screen.queryByRole('heading',{name:'目前沒有待辦事項'})).not.toBeInTheDocument();
    vi.mocked(client.list).mockResolvedValue({items:[],total:null,next_cursor:null});
    fireEvent.click(screen.getByRole('button',{name:'重試進件資料待修正'}));
    await screen.findByRole('heading',{name:'目前沒有待辦事項'});
  });
  it('進件資料頂部總數解析共用欄位 schema 並跨頁每案只計一筆',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([importSource]);
    vi.mocked(client.list).mockRestore();
    vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session');
    const first = importTodo('CASE-1');
    const get=vi.spyOn(transport,'get')
      .mockResolvedValueOnce({data:{items:[first],total:null,next_cursor:1}})
      .mockResolvedValueOnce({data:{items:[first,importTodo('CASE-2')],total:null,next_cursor:null}});

    await expect(client.pendingCount()).resolves.toBe(2);
    expect(get).toHaveBeenCalledTimes(2);
    expect(get).toHaveBeenLastCalledWith('/api/v1/line/notification-tasks/import_fields', expect.objectContaining({params:{cursor:1}}));
  });
  it('推薦待跟進開啟案件工作區，無客服通知入口',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([{source:'recommendation',label:'推薦確認',group:'review'}]);
    vi.mocked(client.list).mockResolvedValue({items:[item({id:'recommendation:7:reply_reminder',source:'recommendation',title:'推薦確認待跟進',payment:null,unavailable_reason:null})],total:1,next_cursor:null});
    render(<NotificationTasksPage/>);
    await screen.findByRole('heading',{name:'推薦確認待跟進'});
    fireEvent.click(screen.getByRole('button',{name:'開啟案件工作區'}));
    expect(window.location.hash).toBe('#order-workbench-v2?case=116000001&work=recommendation');
    expect(screen.queryByRole('button',{name:'前往客服案件'})).not.toBeInTheDocument();
  });
  it('月嫂未綁定保留人工聯絡與複製，不建立 LINE 寄送工作',async()=>{
    const reminder=item({id:'staff_binding:7',source:'staff_binding',group:'review',title:'人工提醒綁定 LINE',person:'合成姓名',
      case_no:null,recipient:'0987654321',message:'請加入工會 LINE 官方帳號並完成綁定。',payment:null});
    vi.mocked(client.catalog).mockResolvedValue([{source:'staff_binding',label:'綁定人工提醒',group:'review'}]);
    vi.mocked(client.list).mockResolvedValue({items:[reminder],total:1,next_cursor:null});
    const copy=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',{...navigator,clipboard:{writeText:copy}});
    const send=vi.spyOn(client,'send');render(<NotificationTasksPage />);
    await screen.findByRole('heading',{name:'人工提醒綁定 LINE'});
    expect(screen.getAllByText('月嫂資料').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button',{name:'查看人工提醒方式'})).not.toBeInTheDocument();
    expect(screen.getByRole('link',{name:'電話聯絡 0987654321'})).toHaveAttribute('href','tel:0987654321');
    expect(screen.queryByRole('button',{name:'移除提醒'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'複製綁定提醒'}));
    await screen.findByText('已複製，請由您透過既有聯絡方式轉達。');
    expect(copy).toHaveBeenCalledWith(reminder.message);expect(send).not.toHaveBeenCalled();
    vi.mocked(client.list).mockResolvedValue({items:[],total:0,next_cursor:null});
    fireEvent.click(screen.getByRole('button',{name:'重新整理'}));
    await screen.findByRole('heading',{name:'目前沒有待辦事項'});
    vi.unstubAllGlobals();
  });
  it('讀取真實來源；缺少綁定仍保留原因、提醒與補齊入口，不因查詢建立寄送工作',async()=>{
    const send=vi.spyOn(client,'send');render(<NotificationTasksPage />);
    await screen.findByRole('heading',{name:'訂金逾期未清'});
    expect(screen.getByRole('note')).toHaveTextContent('尚未綁定 LINE');
    expect(screen.getByRole('button',{name:'發送提醒'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'前往核對款項'})).toBeEnabled();
    expect(screen.queryByText('範例資料')).not.toBeInTheDocument();expect(send).not.toHaveBeenCalled();
  });
  it('同一次提醒防連點，結果未明重用原操作識別；每期傳回原本的 snapshot',async()=>{
    vi.mocked(client.list).mockResolvedValue({items:[item({unavailable_reason:null})],total:1,next_cursor:null});
    let fail!:(reason:Error)=>void;
    const send=vi.spyOn(client,'send').mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}))
      .mockRejectedValue(new ApiHttpError(409,'payment_overdue_recipient_unavailable','客戶尚未綁定 LINE'));
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    const button=screen.getByRole('button',{name:'發送提醒'});fireEvent.click(button);fireEvent.click(button);
    expect(send).toHaveBeenCalledTimes(1);fail(new ApiHttpError(409,'payment_overdue_recipient_unavailable','客戶尚未綁定 LINE'));
    await screen.findByRole('status');await waitFor(()=>expect(button).toBeEnabled());fireEvent.click(button);
    await waitFor(()=>expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[1][1]).toBe(send.mock.calls[0][1]);
    expect(send.mock.calls[0][0].payment).toEqual(item().payment);
  });
  it('一類讀取失敗不冒充零筆，也不阻斷其他來源；可以重試',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'},{source:'identity',label:'身分綁定審核',group:'review'}]);
    vi.mocked(client.list).mockImplementation(async source=>{if(source==='identity')throw new Error('read failed');return {items:[item()],total:1,next_cursor:null};});
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    expect(await screen.findByRole('alert')).toHaveTextContent('部分事項未能載入');
    const retry=screen.getByRole('button',{name:'重試身分綁定審核'});fireEvent.click(retry);
    await waitFor(()=>expect(client.list).toHaveBeenCalledWith('identity'));
  });
  it('更多事項沿用來源 cursor，不把第一批資料當成完整清單',async()=>{
    vi.mocked(client.list).mockImplementation(async (_source,cursor=0)=>({items:[item(cursor?{id:'overdue:first',title:'第一期款逾期未清'}:{})],total:26,next_cursor:cursor?null:1}));
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    fireEvent.click(screen.getByRole('button',{name:'載入更多事項'}));
    await screen.findByRole('button',{name:/第一期款逾期未清/});expect(client.list).toHaveBeenCalledWith('overdue',1);
    expect(screen.queryByRole('button',{name:'載入更多事項'})).not.toBeInTheDocument();
  });
  it('簽約入口定位同案契約工作區，財務入口也帶入案號',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([{source:'recommendation',label:'推薦確認與簽約',group:'review'}]);
    vi.mocked(client.list).mockResolvedValue({items:[item({id:'recommendation:1',source:'recommendation',group:'review',title:'待辦簽約',tag:'待簽約',payment:null})],total:1,next_cursor:null});
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'待辦簽約'});
    fireEvent.click(screen.getByRole('button',{name:'開啟案件工作區'}));expect(window.location.hash).toBe('#order-workbench-v2?case=116000001&work=contracts');
  });
  it('通知事項不提供寄送紀錄也不查詢歷史工作',async()=>{
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    expect(screen.queryByRole('button',{name:/寄送紀錄/})).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox',{name:'寄送狀態'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'重新整理'}));
    await waitFor(()=>expect(client.catalog).toHaveBeenCalledTimes(2));
    await screen.findByRole('heading',{name:'訂金逾期未清'});
    expect(lineDeliveryQueryClient.list).not.toHaveBeenCalled();
  });
});


it('全部來源失敗顯示無法確認待辦，重試成功後才顯示真正零筆',async()=>{
 vi.mocked(client.list).mockRejectedValue(new Error('synthetic unavailable'));
 render(<NotificationTasksPage/>);
 await screen.findByRole('heading',{name:'目前無法完整讀取事項'});
 expect(screen.queryByRole('heading',{name:'目前沒有待辦事項'})).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'重新讀取事項'})).toBeVisible();
 vi.mocked(client.list).mockResolvedValue({items:[],total:0,next_cursor:null});
 fireEvent.click(screen.getByRole('button',{name:'重試各期款項逾期'}));
 await screen.findByRole('heading',{name:'目前沒有待辦事項'});
});

it('空候選頁仍有後頁時提供載入更多，不宣稱已無待辦',async()=>{
 vi.mocked(client.list).mockResolvedValueOnce({items:[],total:null,next_cursor:1})
  .mockResolvedValue({items:[item()],total:1,next_cursor:null});
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'尚有事項待載入'});
 expect(screen.queryByRole('heading',{name:'目前沒有待辦事項'})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'載入更多事項'}));
 await screen.findByRole('heading',{name:'訂金逾期未清'});
});

it('目前分類不受其他分類讀取失敗影響',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'},{source:'identity',label:'身分綁定審核',group:'review'}]);
 vi.mocked(client.list).mockImplementation(async source=>{if(source==='identity')throw new Error('synthetic unavailable');return {items:[],total:0,next_cursor:null};});
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'目前無法完整讀取事項'});
 fireEvent.click(screen.getByRole('button',{name:/款項與群組/}));
 await screen.findByRole('heading',{name:'目前沒有待辦事項'});
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('有搜尋條件時區分搜尋無結果與真正沒有待辦',async()=>{
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'訂金逾期未清'});
 fireEvent.change(screen.getByRole('searchbox',{name:'搜尋通知事項'}),{target:{value:'不存在的項目'}});
 await screen.findByRole('heading',{name:'沒有符合搜尋條件的事項'});
 fireEvent.click(screen.getByRole('button',{name:'清除篩選'}));
 await screen.findByRole('heading',{name:'訂金逾期未清'});
});

it('權限及登入問題使用人員可理解的原因與下一步',()=>{
 expect(notificationFailure(new ApiHttpError(403,'internal_code','目前帳號無法發送提醒。'))).toContain('由有權限的工會人員處理');
 expect(notificationFailure(new ApiHttpError(403,'internal_code','目前帳號無法發送提醒。'))).not.toContain('internal_code');
 expect(notificationFailure(new ApiHttpError(401,'expired','unauthorized'))).toBe('登入已失效，請重新登入後再試。');
});

it('從設定頁返回時重讀待辦及計數，不沿用離頁前清單',async()=>{
  render(<NotificationTasksPage/>);
  await screen.findByRole('heading',{name:'訂金逾期未清'});
  vi.mocked(client.list).mockResolvedValue({items:[],total:0,next_cursor:null});
  window.history.replaceState(null,'','#line-notifications');
  fireEvent(window,new Event('hashchange'));
  window.history.replaceState(null,'','#notifications');
  fireEvent(window,new Event('hashchange'));
  await screen.findByRole('heading',{name:'目前沒有待辦事項'});
  expect(screen.getByLabelText('通知事項清單')).toHaveTextContent('已載入 0 筆，符合 0 筆');
  expect(screen.getByRole('button',{name:/款項與群組/})).toBeVisible();
});

it('重新整理逐來源採用新資料，舊事項的操作暫停至該來源讀回', async () => {
  const overdue = item({unavailable_reason: null});
  const recommendation = item({id: 'recommendation:7', source: 'recommendation', title: '原推薦待辦', payment: null});
  vi.mocked(client.catalog).mockResolvedValue([
    {source: 'overdue', label: '各期款項逾期', group: 'reminder'},
    {source: 'recommendation', label: '推薦確認', group: 'review'},
  ]);
  vi.mocked(client.list).mockImplementation(async source => ({items: [source === 'overdue' ? overdue : recommendation], total: 1, next_cursor: null}));
  const send = vi.spyOn(client, 'send');
  render(<NotificationTasksPage />);
  const refresh = await screen.findByRole('button', {name: '重新整理'});
  await waitFor(() => expect(refresh).toBeEnabled());
  expect(screen.getByRole('button', {name: '發送提醒'})).toBeEnabled();

  let publishRecommendation!: (page: NotificationPage) => void;
  let failOverdue!: (error: Error) => void;
  const recommendationRead = new Promise<NotificationPage>(resolve => { publishRecommendation = resolve; });
  const overdueRead = new Promise<NotificationPage>((_resolve, reject) => { failOverdue = reject; });
  vi.mocked(client.list).mockImplementation(source => source === 'overdue' ? overdueRead : recommendationRead);
  fireEvent.click(refresh);
  expect(screen.getByRole('button', {name: /訂金逾期未清.*更新中，顯示上次資料/})).toBeVisible();
  expect(screen.getByRole('button', {name: /原推薦待辦.*更新中，顯示上次資料/})).toBeVisible();
  expect(screen.getByRole('button', {name: '發送提醒'})).toBeDisabled();
  expect(screen.getByRole('button', {name: /全部事項/})).toHaveTextContent('—');

  await act(async () => publishRecommendation({items: [{...recommendation, title: '新推薦待辦'}], total: 1, next_cursor: null}));
  const freshRow = await screen.findByRole('button', {name: /新推薦待辦/});
  expect(freshRow).not.toHaveTextContent('顯示上次資料');
  expect(screen.getByRole('button', {name: /訂金逾期未清.*更新中，顯示上次資料/})).toBeVisible();
  await act(async () => failOverdue(new ApiHttpError(503, 'notification_source_unavailable', '款項來源暫時無法讀取。')));
  expect(screen.getByRole('button', {name: /訂金逾期未清.*更新失敗，顯示上次資料/})).toBeVisible();
  expect(screen.getByRole('button', {name: '發送提醒'})).toBeDisabled();
  expect(screen.getByRole('button', {name: /全部事項/})).toHaveTextContent('—');
  expect(send).not.toHaveBeenCalled();

  vi.mocked(client.list).mockResolvedValue({items: [], total: 0, next_cursor: null});
  fireEvent.click(screen.getByRole('button', {name: '重試各期款項逾期'}));
  await waitFor(() => expect(screen.queryByRole('button', {name: /訂金逾期未清/})).not.toBeInTheDocument());
  expect(screen.getByRole('button', {name: /全部事項/})).toHaveTextContent('1');
  expect(screen.getByRole('button', {name: '開啟案件工作區'})).toBeEnabled();
});

it('寄送工作更新後取代同一任務的舊異常，異常來源重試成功後再依新資料去重', async () => {
  const fault = item({
    id: 'notification_failure:case', source: 'notification_failure', title: '舊通知異常',
    payment: null, unavailable_reason: null,
    failure: {issue_key: 'ci_' + 'a'.repeat(64), notification_reason: 'recipient_unavailable', related_task_ids: [17]},
  });
  const delivery = item({
    id: 'delivery:17', source: 'delivery', title: '寄送工作 #17', reference_id: 17,
    payment: null, unavailable_reason: null,
  });
  const result = (value: NotificationItem): NotificationPage => ({items: [value], total: 1, next_cursor: null});
  vi.mocked(client.catalog).mockResolvedValue([
    {source: 'notification_failure', label: '通知建立異常', group: 'review'},
    {source: 'delivery', label: '寄送工作', group: 'review'},
  ]);
  vi.mocked(client.list).mockImplementation(async source => result(source === 'delivery' ? delivery : fault));
  render(<NotificationTasksPage />);
  const refresh = await screen.findByRole('button', {name: '重新整理'});
  await waitFor(() => expect(refresh).toBeEnabled());
  expect(screen.getByRole('button', {name: /舊通知異常/})).toBeVisible();
  expect(screen.queryByRole('button', {name: /寄送工作 #17/})).not.toBeInTheDocument();

  let failFault!: (error: Error) => void;
  const delayedFault = new Promise<NotificationPage>((_resolve, reject) => { failFault = reject; });
  const freshDelivery = {...delivery, title: '已更新寄送工作 #17'};
  vi.mocked(client.list).mockImplementation(source => source === 'delivery'
    ? Promise.resolve(result(freshDelivery)) : delayedFault);
  fireEvent.click(refresh);
  const refreshedRow = await screen.findByRole('button', {name: /已更新寄送工作 #17/});
  expect(refreshedRow).not.toHaveTextContent('顯示上次資料');
  expect(screen.queryByRole('button', {name: /舊通知異常/})).not.toBeInTheDocument();

  await act(async () => failFault(new ApiHttpError(503, 'notification_source_unavailable', '異常來源暫時無法讀取。')));
  expect(refreshedRow).toBeVisible();
  expect(screen.queryByRole('button', {name: /舊通知異常/})).not.toBeInTheDocument();
  expect(screen.getByRole('button', {name: /全部事項/})).toHaveTextContent('—');

  vi.mocked(client.list).mockResolvedValue(result({...fault, title: '已確認通知異常'}));
  fireEvent.click(screen.getByRole('button', {name: '重試通知建立異常'}));
  await screen.findByRole('button', {name: /已確認通知異常/});
  expect(screen.queryByRole('button', {name: /已更新寄送工作 #17/})).not.toBeInTheDocument();
  expect(screen.getByRole('button', {name: /全部事項/})).toHaveTextContent('1');
});

it('重新整理的目錄撤掉來源時，舊事項隨即移除', async () => {
  render(<NotificationTasksPage />);
  await screen.findByRole('heading', {name: '訂金逾期未清'});
  const refresh = screen.getByRole('button', {name: '重新整理'});
  await waitFor(() => expect(refresh).toBeEnabled());
  vi.mocked(client.catalog).mockResolvedValue([]);
  fireEvent.click(refresh);
  await screen.findByRole('heading', {name: '目前沒有待辦事項'});
  expect(screen.queryByText('訂金逾期未清')).not.toBeInTheDocument();
  expect(client.list).toHaveBeenCalledTimes(1);
});

it('使用來源目錄的五類篩選，非市民待審只顯示申請編號與收件時間並開啟原申請',async()=>{
  vi.mocked(client.catalog).mockResolvedValue([
    {source:'registration',label:'待審申請',group:'review',category_id:'applications',category_label:'申請與資料'},
    {source:'identity',label:'身分審核',group:'review',category_id:'identity',category_label:'LINE 身分'},
    {source:'followup',label:'媒合跟進',group:'review',category_id:'coordination',category_label:'媒合、簽約與交接'},
    {source:'overdue',label:'款項逾期',group:'reminder',category_id:'payments',category_label:'款項'},
    {source:'group',label:'待建群組',group:'reminder',category_id:'groups',category_label:'案件群組'},
  ]);
  const registration=item({id:'registration:42',source:'registration',group:'review',title:'非市民申請待審核',
    case_no:null,reference_id:42,person:'合成申請人',recipient:'合成電話',message:'合成問卷',
    summary:'合成申請內容',time:'2026-11-27T02:00:00Z',payment:null,unavailable_reason:null});
  vi.mocked(client.list).mockImplementation(async source=>({items:source==='registration'?[registration]
    : source==='overdue'?[item()]:[],total:source==='registration'||source==='overdue'?1:0,next_cursor:null}));
  render(<NotificationTasksPage/>);
  await screen.findByRole('heading',{name:'非市民申請待審核'});
  for(const label of ['申請與資料','LINE 身分','媒合、簽約與交接','款項','案件群組']) {
    expect(screen.getByRole('button',{name:new RegExp(label)})).toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole('button',{name:/案件群組/}));
  expect(screen.queryByRole('button',{name:/訂金逾期未清/})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/申請與資料/}));
  expect(screen.getByRole('button',{name:/非市民申請待審核.*申請編號：42/})).toBeInTheDocument();
  expect(screen.getByText('收件時間')).toBeInTheDocument();
  for(const privateText of ['合成申請人','合成電話','合成問卷','合成申請內容']) {
    expect(screen.queryByText(privateText)).not.toBeInTheDocument();
  }
  fireEvent.click(screen.getByRole('button',{name:'查看申請'}));
  expect(window.location.hash).toBe('#clients?tab=applications&registration=42');
});

it('客戶綁定提醒只提供有權限的單案移除，重試沿用原鍵且不發送 LINE',async()=>{
  const reminder=item({id:'customer_binding:7:116000001',source:'customer_binding',reference_id:7,group:'review',
    title:'人工提醒綁定 LINE',person:'合成姓名',can_dismiss:true,recipient:'0987654321',message:'綁定提醒訊息',payment:null,unavailable_reason:null});
  const otherCase={...reminder,id:'customer_binding:7:116000002',case_no:'116000002',can_dismiss:false};
  vi.mocked(client.catalog).mockResolvedValue([{source:'customer_binding',label:'綁定提醒',group:'review',category_id:'identity',category_label:'LINE 身分'}]);
  vi.mocked(client.list).mockResolvedValue({items:[reminder,otherCase],total:2,next_cursor:null});
  const dismiss=vi.spyOn(client,'dismissCustomerBinding').mockRejectedValueOnce(new ApiHttpError(409,'notification_conflict','合成操作失敗')).mockImplementation(async()=>{
    vi.mocked(client.list).mockResolvedValue({items:[otherCase],total:1,next_cursor:null});
    return {dismissed:true,replayed:false};
  });
  const send=vi.spyOn(client,'send');render(<NotificationTasksPage/>);
  await screen.findByRole('heading',{name:'人工提醒綁定 LINE'});
  fireEvent.click(screen.getByRole('button',{name:/116000002/}));
  expect(screen.queryByRole('button',{name:'移除提醒'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:/116000001/}));
  const button=screen.getByRole('button',{name:'移除提醒'});
  expect(button).toBeEnabled();
  expect(screen.queryByRole('textbox',{name:/原因/})).not.toBeInTheDocument();
  expect(screen.queryByRole('heading',{name:/聯絡合成姓名|聯絡 合成姓名/})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'複製綁定提醒'})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:/電話聯絡|查看綁定狀態|查看本案資料/})).not.toBeInTheDocument();
  expect(screen.queryByText('0987654321')).not.toBeInTheDocument();
  fireEvent.click(button);
  await screen.findByText('合成操作失敗');
  const originalKey=dismiss.mock.calls[0][2];
  fireEvent.click(button);
  await waitFor(()=>expect(dismiss).toHaveBeenNthCalledWith(2,expect.objectContaining({reference_id:7,case_no:'116000001'}),'使用者移除提醒',originalKey));
  await waitFor(()=>expect(screen.queryByRole('button',{name:/116000001/})).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:/116000002/})).toBeInTheDocument();
  expect(send).not.toHaveBeenCalled();
});
