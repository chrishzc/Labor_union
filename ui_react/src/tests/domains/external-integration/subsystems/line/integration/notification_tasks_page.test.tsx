import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationTasksPage } from '../../../../../../pages/NotificationTasksPreviewPage';
import { notificationTasksClient as client, notificationFailure, type NotificationItem } from '../../../../../../api/line_notifications/notification_tasks_client';
import { lineDeliveryQueryClient } from '../../../../../../api/line_delivery/line_delivery_query_client';
import { ApiHttpError } from '../../../../../../api/shared/typed_errors';
import { transport } from '../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../api/auth/session_client';

const item=(patch:Partial<NotificationItem>={}):NotificationItem=>({id:'overdue:deposit',source:'overdue',group:'reminder',title:'訂金逾期未清',case_no:'116000001',reference_id:null,
  person:'',summary:'本期未繳 NT$ 3,000',reason:'各期獨立判斷',time:'2026-10-24',tag:'待處理',recipient:'客戶私人聊天室',message:'目前訂金餘額',unavailable_reason:'客戶尚未綁定 LINE',expected_version:null,
  delivery_status:null,payment:{case_no:'116000001',payment_stage:'deposit',obligation_identity:'case1:deposit',projection_version:1,obligation_event_id:10,due_date:'2026-10-24',remaining_amount_ntd:3000},log:null,information:null,...patch});
beforeEach(()=>{
  window.matchMedia=vi.fn().mockReturnValue({matches:false}) as unknown as typeof matchMedia;
  vi.spyOn(client,'catalog').mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'}]);
  vi.spyOn(client,'list').mockResolvedValue({items:[item()],total:1,next_cursor:null});
  vi.spyOn(lineDeliveryQueryClient,'list').mockResolvedValue({items:[],total:0,page:1,page_size:6,total_pages:1});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();window.history.replaceState(null,'','/');});
describe('通知事項實際接線',()=>{
  it('建立前受阻的通知可核對與補送；排送中保留待辦，成功後由原來源移除',async()=>{
    vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session');
    const key='ci_'+'1'.repeat(64);
    const failure=item({id:'notification_failure:'+key,source:'notification_failure',group:'support',title:'LINE 通知建立異常',
      unavailable_reason:null,payment:null,failure:{issue_key:key,notification_reason:'recipient_unavailable',related_task_ids:[7]}});
    vi.mocked(client.catalog).mockResolvedValue([{source:'notification_failure',label:'LINE 通知建立異常',group:'support'},{source:'delivery',label:'寄送異常',group:'support'}]);
    let finished=false;
    vi.mocked(client.list).mockImplementation(async source=>({items:finished?[]:source==='notification_failure'?[failure]:[item({id:'delivery:7',source:'delivery',reference_id:7,title:'已涵蓋的工作'})],total:finished?0:1,next_cursor:null}));
    const details=(can:boolean,message:string|null)=>({data:{case_no:'116000001',notification_reason:'recipient_unavailable',related_task_ids:[7],sources:[{source_event_id:11,event_code:'client.second_payment_due',can_replay:can,unavailable_reason:message}]}});
    vi.spyOn(lineDeliveryQueryClient,'detail').mockResolvedValue({task:{id:7,task_id:7,task_type:'finance',source_type:'finance',status:'failed',scheduled_at:'2026-10-26T00:00:00Z',created_at:'2026-10-26T00:00:00Z',updated_at:'2026-10-26T00:00:00Z',completed_attempts:1,max_attempts:3,next_retry_at:null,sent_at:null,failed_at:'2026-10-26T00:00:00Z'},attempts:[]});
    const get=vi.spyOn(transport,'get').mockResolvedValue(details(false,'案件群組尚不可用。'));
    const post=vi.spyOn(transport,'post').mockResolvedValue({data:{source_event_id:11,replayed_source_event_id:22}});
    render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'LINE 通知建立異常'});
    expect(screen.getByLabelText('通知事項清單').querySelectorAll('[data-notification-id]')).toHaveLength(1);
    fireEvent.click(screen.getByRole('button',{name:'處理通知建立異常'}));
    expect(await screen.findByRole('button',{name:'補送原通知 #11'})).toBeDisabled();expect(post).not.toHaveBeenCalled();
    expect(await screen.findByRole('button',{name:'重試寄送工作'})).toBeEnabled();
    expect(screen.getByRole('link',{name:'通知內容與規則設定'})).toHaveAttribute('href','#line-management?tab=push_queue');
    get.mockResolvedValue(details(true,null));fireEvent.click(screen.getByRole('button',{name:'重新核對通知'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'補送原通知 #11'})).toBeEnabled());
    get.mockResolvedValue(details(false,'原補送工作尚未完成，請查看寄送狀況。'));
    fireEvent.click(screen.getByRole('button',{name:'補送原通知 #11'}));
    await screen.findByText('原補送工作尚未完成，請查看寄送狀況。');
    expect(screen.getByRole('button',{name:'補送原通知 #11'})).toBeDisabled();expect(post).toHaveBeenCalledTimes(1);
    finished=true;fireEvent.click(screen.getByRole('button',{name:'重新整理'}));
    await screen.findByRole('heading',{name:'目前沒有待辦事項'});
  });
  it.each(['customer_binding','staff_binding'] as const)('未綁定來源 %s 提供人工聯絡與複製，不建立 LINE 寄送工作',async source=>{
    const reminder=item({id:source+':7',source,group:'review',title:'人工提醒綁定 LINE',person:'合成姓名',
      case_no:source==='customer_binding'?'116000001':null,recipient:'0987654321',message:'請加入工會 LINE 官方帳號並完成綁定。',payment:null});
    vi.mocked(client.catalog).mockResolvedValue([{source,label:'綁定人工提醒',group:'review'}]);
    vi.mocked(client.list).mockResolvedValue({items:[reminder],total:1,next_cursor:null});
    const copy=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',{...navigator,clipboard:{writeText:copy}});
    const send=vi.spyOn(client,'send');render(<NotificationTasksPage />);
    await screen.findByRole('heading',{name:'人工提醒綁定 LINE'});
    if(source==='staff_binding')expect(screen.getAllByText('月嫂資料').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button',{name:'查看人工提醒方式'}));
    expect(screen.getByRole('link',{name:'電話聯絡 0987654321'})).toHaveAttribute('href','tel:0987654321');
    fireEvent.click(screen.getByRole('button',{name:'複製綁定提醒'}));
    await screen.findByText('已複製，請由您透過既有聯絡方式轉達。');
    expect(copy).toHaveBeenCalledWith(reminder.message);expect(send).not.toHaveBeenCalled();
    vi.mocked(client.list).mockResolvedValue({items:[],total:0,next_cursor:null});
    fireEvent.click(screen.getByRole('button',{name:'重新整理'}));
    await screen.findByRole('heading',{name:'目前沒有待辦事項'});
    vi.unstubAllGlobals();
  });
  it('同一客服聯絡需求只列一次',async()=>{
    vi.mocked(client.catalog).mockResolvedValue([{source:'recommendation',label:'推薦確認',group:'review'},{source:'customer_service',label:'客服',group:'support'}]);
    vi.mocked(client.list).mockImplementation(async source=>({items:[item({id:'customer_service:7',source,title:source==='customer_service'?'客服需求':'推薦聯絡需求',group:source==='customer_service'?'support':'review',reference_id:7})],total:1,next_cursor:null}));
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'客服需求'});
    expect(screen.getByLabelText('通知事項清單').querySelectorAll('[data-notification-id]')).toHaveLength(1);
    expect(screen.queryByRole('button',{name:/推薦聯絡需求/})).not.toBeInTheDocument();
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
    vi.mocked(client.catalog).mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'},{source:'profile',label:'客戶資料異動',group:'review'}]);
    vi.mocked(client.list).mockImplementation(async source=>{if(source==='profile')throw new Error('read failed');return {items:[item()],total:1,next_cursor:null};});
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    expect(await screen.findByRole('alert')).toHaveTextContent('部分事項未能載入');
    const retry=screen.getByRole('button',{name:'重試客戶資料異動'});fireEvent.click(retry);
    await waitFor(()=>expect(client.list).toHaveBeenCalledWith('profile'));
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
  it('寄送紀錄讀取原本工作清單，狀態篩選交由 server 分頁',async()=>{
    render(<NotificationTasksPage />);await screen.findByRole('heading',{name:'訂金逾期未清'});
    fireEvent.click(screen.getByRole('button',{name:/寄送紀錄/}));
    fireEvent.change(screen.getByRole('combobox',{name:'寄送狀態'}),{target:{value:'failed'}});
    await waitFor(()=>expect(lineDeliveryQueryClient.list).toHaveBeenLastCalledWith({page:1,pageSize:6,status:'failed'},expect.objectContaining({signal:expect.any(AbortSignal)})));
    expect(within(screen.getByLabelText('通知事項清單')).queryByText('筆範例')).not.toBeInTheDocument();
  });
});


it('客戶未綁定時顯示原因與下一步，只擋客戶；重新核對保留文案且不寄送',async()=>{
 const information={question_id:7,pool_id:1,request_kind:'information_question' as const,customer_answer_event_id:null,review_completed:false,
  case_no:'116000001',staff_name:'合成月嫂',issues:[],customer_answer:null,customer_message:null,customer_available:false};
 let bound=false;
 vi.mocked(client.catalog).mockResolvedValue([{source:'information',label:'確認資訊',group:'review'}]);
 vi.mocked(client.list).mockImplementation(async()=>({items:[item({id:'information:7',source:'information',group:'review',title:'確認資訊',reference_id:7,payment:null,
  unavailable_reason:bound?null:'客戶尚未綁定 LINE',information:{...information,customer_available:bound}})],total:1,next_cursor:null}));
 const post=vi.spyOn(transport,'post');
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'確認資訊'});
 fireEvent.click(screen.getByRole('button',{name:'處理確認與條件'}));
 const panel=screen.getByLabelText('月嫂確認與條件協調');
 fireEvent.change(within(panel).getByLabelText('發送文案'),{target:{value:'尚未發送的草稿'}});
 expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeDisabled();
 expect(within(panel).getByRole('button',{name:'發送給月嫂'})).toBeEnabled();
 expect(within(panel).getByText(/這位客戶尚未綁定 LINE/)).toHaveTextContent('請先聯絡客戶完成綁定');
 expect(within(panel).getByRole('link',{name:'查看客戶綁定方式與狀態'})).toBeVisible();
 fireEvent.click(within(panel).getByRole('button',{name:'發送給客戶'}));expect(post).not.toHaveBeenCalled();
 bound=true;fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));
 await waitFor(()=>expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeEnabled());
 expect(within(panel).getByLabelText('發送文案')).toHaveValue('尚未發送的草稿');
 vi.mocked(client.list).mockRejectedValueOnce(new ApiHttpError(503,'notification_source_unavailable','這類事項暫時無法讀取，請重試。'));
 fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));
 await within(panel).findByText('目前無法核對這筆需求，暫時不能發送。請重新核對後再試。');
 expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeDisabled();
 expect(within(panel).getByRole('button',{name:'發送給月嫂'})).toBeDisabled();
 expect(within(panel).getByLabelText('發送文案')).toHaveValue('尚未發送的草稿');
 fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));
 await waitFor(()=>expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeEnabled());
 expect(post).not.toHaveBeenCalled();
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

it('目前分類與寄送紀錄不受其他分類讀取失敗影響',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'overdue',label:'各期款項逾期',group:'reminder'},{source:'profile',label:'資料異動',group:'review'}]);
 vi.mocked(client.list).mockImplementation(async source=>{if(source==='profile')throw new Error('synthetic unavailable');return {items:[],total:0,next_cursor:null};});
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'目前無法完整讀取事項'});
 fireEvent.click(screen.getByRole('button',{name:/款項與日誌/}));
 await screen.findByRole('heading',{name:'目前沒有待辦事項'});
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/寄送紀錄/}));
 await screen.findByRole('heading',{name:'沒有符合條件的事項'});
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
