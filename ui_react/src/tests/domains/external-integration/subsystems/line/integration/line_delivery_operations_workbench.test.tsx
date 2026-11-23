import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { afterEach,beforeEach,it,expect,vi } from 'vitest';
import { LineDeliveryOperationsWorkbench } from '../../../../../../components/LineDeliveryOperationsWorkbench';
import { notificationTasksClient as client,type NotificationItem } from '../../../../../../api/line_notifications/notification_tasks_client';
import { lineDeliveryQueryClient } from '../../../../../../api/line_delivery/line_delivery_query_client';
import { transport } from '../../../../../../api/shared/transport';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { mapLineDeliveryQueryError } from '../../../../../../api/line_delivery/line_delivery_query_errors';
import { ApiHttpError } from '../../../../../../api/shared/typed_errors';
const item=(patch:Partial<NotificationItem>={}):NotificationItem=>({id:'notification_failure:1',source:'notification_failure',group:'support',title:'LINE 通知建立異常',case_no:'116000001',reference_id:null,person:'',summary:'原通知受阻',reason:'設定未齊',time:'',tag:'待處理',recipient:null,message:null,unavailable_reason:null,expected_version:null,delivery_status:null,payment:null,log:null,...patch});
beforeEach(()=>{vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session');vi.spyOn(client,'list').mockResolvedValue({items:[],total:0,next_cursor:null});vi.spyOn(lineDeliveryQueryClient,'list').mockResolvedValue({items:[],total:0,page:1,page_size:25,total_pages:1});});
afterEach(()=>{cleanup();vi.restoreAllMocks();window.history.replaceState(null,'','/');});
it.each([
  [410,'line_delivery_history_expired','此寄送紀錄已超過六個月，內容與嘗試明細已清除；必要處理憑證仍保留。'],
  [409,'line_delivery_history_expired','目前無法完成操作，請重新整理後再試。'],
  [410,'unrecognized_delivery_error','目前無法完成操作，請重新整理後再試。'],
] as const)('寄送詳情 HTTP %s / %s 僅顯示已知到期說明且不提供處理動作',async(status,code,message)=>{
  vi.spyOn(lineDeliveryQueryClient,'detail').mockRejectedValue(mapLineDeliveryQueryError(new ApiHttpError(status,code,'private provider diagnostic')));
  const post=vi.spyOn(transport,'post');
  window.location.hash='#line-notifications?tab=delivery&task=5';
  render(<LineDeliveryOperationsWorkbench/>);
  expect(await screen.findByText(message)).toBeInTheDocument();
  expect(screen.queryByText('private provider diagnostic')).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'重試寄送工作'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'不再寄送／結清'})).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});
it('保留舊簽署提醒的寄送紀錄，但不提供重試', async () => {
  const time = '2026-10-26T00:00:00Z';
  vi.spyOn(lineDeliveryQueryClient, 'detail').mockResolvedValue({
    task: {
      id: 7, task_id: 7, task_type: 'contract', source_type: 'contract', status: 'retryable_failed',
      scheduled_at: time, created_at: time, updated_at: time, completed_attempts: 1,
      max_attempts: 3, next_retry_at: time, sent_at: null, failed_at: time,
    },
    attempts: [],
    retry_allowed: false,
    handling:{target_kind:'delivery_task',target_identity:'7',needs_attention:true,allowed_actions:['close'],blocked_reason:null},
  });
  window.location.hash = '#line-management?tab=delivery&task=7';
  render(<LineDeliveryOperationsWorkbench />);
  expect(await screen.findByText('已嘗試 1／3 次')).toBeVisible();
  expect(screen.queryByRole('button', { name: '重試寄送工作' })).not.toBeInTheDocument();
  expect(screen.queryByText(/下次重試/)).not.toBeInTheDocument();
});

  it('建立前受阻的通知可核對與補送；排送中保留待辦，成功後由原來源移除',async()=>{
    vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session');
    const key='ci_'+'1'.repeat(64);
    const failure=item({id:'notification_failure:'+key,source:'notification_failure',group:'support',title:'LINE 通知建立異常',
      unavailable_reason:null,payment:null,failure:{issue_key:key,notification_reason:'recipient_unavailable',related_task_ids:[7]}});
    let finished=false;
    vi.mocked(client.list).mockImplementation(async source=>({items:finished?[]:source==='notification_failure'?[failure]:[item({id:'delivery:7',source:'delivery',reference_id:7,title:'已涵蓋的工作'})],total:finished?0:1,next_cursor:null}));
    const details=(can:boolean,message:string|null)=>({data:{case_no:'116000001',notification_reason:'recipient_unavailable',handling:{target_kind:'notification_failure',target_identity:key,needs_attention:true,allowed_actions:['close','replay'],blocked_reason:null},related_task_ids:[7],sources:[{source_event_id:11,event_code:'client.second_payment_due',can_replay:can,unavailable_reason:message}]}});
    vi.spyOn(lineDeliveryQueryClient,'detail').mockResolvedValue({task:{id:7,task_id:7,task_type:'finance',source_type:'finance',status:'failed',scheduled_at:'2026-10-26T00:00:00Z',created_at:'2026-10-26T00:00:00Z',updated_at:'2026-10-26T00:00:00Z',completed_attempts:1,max_attempts:3,next_retry_at:null,sent_at:null,failed_at:'2026-10-26T00:00:00Z'},attempts:[],handling:{target_kind:'delivery_task',target_identity:'7',needs_attention:true,allowed_actions:['retry'],blocked_reason:null}});
    const get=vi.spyOn(transport,'get').mockResolvedValue(details(false,'案件群組尚不可用。'));
    const post=vi.spyOn(transport,'post').mockResolvedValue({data:{source_event_id:11,replayed_source_event_id:22}});
    window.location.hash=`#line-management?tab=delivery&view=failures&issue=${key}`;
    render(<LineDeliveryOperationsWorkbench/>);
    expect(await screen.findByRole('button',{name:'補送原通知 #11'})).toBeDisabled();expect(post).not.toHaveBeenCalled();
    expect(await screen.findByRole('button',{name:'重試寄送工作'})).toBeEnabled();
    expect(screen.getByRole('link',{name:'通知內容與規則設定'})).toHaveAttribute('href','#line-management?tab=push_queue');
    get.mockResolvedValue(details(true,null));fireEvent.click(screen.getByRole('button',{name:'重新核對通知'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:'補送原通知 #11'})).toBeEnabled());
    get.mockResolvedValue(details(false,'原補送工作尚未完成，請查看寄送狀況。'));
    fireEvent.click(screen.getByRole('button',{name:'補送原通知 #11'}));
    await screen.findByText('原補送工作尚未完成，請查看寄送狀況。');
    expect(screen.getByRole('button',{name:'補送原通知 #11'})).toBeDisabled();expect(post).toHaveBeenCalledTimes(1);
    finished=true;get.mockResolvedValue({data:{case_no:'116000001',notification_reason:'recipient_unavailable',handling:{target_kind:'notification_failure',target_identity:key,needs_attention:false,allowed_actions:[],blocked_reason:null},related_task_ids:[],sources:[]}});
    fireEvent.click(screen.getByRole('button',{name:'重新核對通知'}));
    await waitFor(()=>expect(screen.queryByRole('button',{name:'補送原通知 #11'})).not.toBeInTheDocument());
  });

it('結清先核對範圍及原因，未知結果不假成功並沿用原命令',async()=>{
  const key='ci_'+'2'.repeat(64);
  vi.spyOn(transport,'get').mockResolvedValue({data:{case_no:'116000001',notification_reason:'recipient_unavailable',related_task_ids:[],sources:[],
    handling:{target_kind:'notification_failure',target_identity:key,needs_attention:true,allowed_actions:['close'],blocked_reason:null}}});
  const post=vi.spyOn(transport,'post').mockResolvedValueOnce({data:{issue_key:key,case_no:'116000001',notification_reason:'recipient_unavailable',
    owner_snapshot_token:'owner',preview_fingerprint:'fingerprint',source_event_ids:[11],tasks:[{task_id:7,status:'failed'}]}})
    .mockRejectedValue(new Error('unknown result'));
  window.location.hash=`#line-management?tab=delivery&view=failures&issue=${key}`;
  render(<LineDeliveryOperationsWorkbench/>);
  fireEvent.click(await screen.findByRole('button',{name:'不再寄送／結清'}));
  expect(await screen.findByText('寄送工作 #7：寄送失敗')).toBeVisible();
  expect(screen.getByRole('button',{name:'確認結清原通知'})).toBeDisabled();
  fireEvent.change(screen.getByRole('textbox',{name:'結清原因'}),{target:{value:'已人工通知'}});
  fireEvent.click(screen.getByRole('button',{name:'確認結清原通知'}));
  await screen.findByRole('alert');
  await waitFor(()=>expect(screen.getByRole('button',{name:'確認結清原通知'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'確認結清原通知'}));
  await waitFor(()=>expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls[1][0]).toContain('/skip/apply');
  expect(post.mock.calls[2][1]).toEqual(post.mock.calls[1][1]);
  expect(post.mock.calls[1][1]).toMatchObject({owner_snapshot_token:'owner',preview_fingerprint:'fingerprint',reason:'已人工通知'});
});
it('處理中依後端原因阻擋，不能以狀態推導結清或重試',async()=>{
  const time='2026-10-26T00:00:00Z';
  vi.spyOn(lineDeliveryQueryClient,'detail').mockResolvedValue({
    task:{id:7,task_id:7,task_type:'finance',source_type:'finance',status:'retryable_failed',scheduled_at:time,created_at:time,updated_at:time,
      completed_attempts:1,max_attempts:3,next_retry_at:time,sent_at:null,failed_at:time},attempts:[],
    handling:{target_kind:'delivery_task',target_identity:'7',needs_attention:true,allowed_actions:[],blocked_reason:'寄送結果尚未確認，請核對。'},
  });
  const post=vi.spyOn(transport,'post');
  window.location.hash='#line-management?tab=delivery&task=7';
  render(<LineDeliveryOperationsWorkbench/>);
  expect(await screen.findByText('寄送結果尚未確認，請核對。')).toBeVisible();
  expect(screen.queryByRole('button',{name:'不再寄送／結清'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'重試寄送工作'})).not.toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});


it('批次候選僅由使用者載入，去重同原通知且不預選', async () => {
  sessionStorage.clear();
  const key = 'ci_' + '3'.repeat(64), time = '2026-10-26T00:00:00Z';
  const task = { id: 7, task_id: 7, task_type: 'finance', source_type: 'finance', status: 'failed', scheduled_at: time, created_at: time, updated_at: time, completed_attempts: 1, max_attempts: 3, next_retry_at: null, sent_at: null, failed_at: time } satisfies import('../../../../../../api/line_delivery/line_delivery_query_schemas').LineDeliveryItem;
  vi.mocked(lineDeliveryQueryClient.list).mockImplementation(async query => ({ items: query?.status ? [task] : [], page: query?.page ?? 1, page_size: 25, total: 50, total_pages: 2 }));
  vi.spyOn(lineDeliveryQueryClient, 'detail').mockResolvedValue({ task, attempts: [], handling: { target_kind: 'notification_failure', target_identity: key, needs_attention: true, allowed_actions: ['close'], blocked_reason: null } });
  const post = vi.spyOn(transport, 'post').mockResolvedValue({ data: { issue_key: key, case_no: '116000001', notification_reason: 'recipient_unavailable', owner_snapshot_token: 'owner', preview_fingerprint: 'fingerprint', source_event_ids: [11], tasks: [{ task_id: 7, status: 'failed' }] } });
  render(<LineDeliveryOperationsWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '開啟批次結清' }));
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '載入結清候選' }));
  await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(1));
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('button', { name: '確認批次結清' })).toBeDisabled();
  expect(post).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(/目前環境|failed|Apply|操作識別/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', {name:'收起批次結清'})).toBeVisible();
  expect(screen.queryByRole('button', {name:'開啟批次結清'})).not.toBeInTheDocument();
  expect(vi.mocked(lineDeliveryQueryClient.list).mock.calls.filter(([query]) => query?.status).map(([query]) => query)).toEqual([
    { status: 'failed', page: 1, pageSize: 25 }, { status: 'retryable_failed', page: 1, pageSize: 25 },
  ]);
});

it('批次逐項保留成功收據，重新掛載後只重送未知且沿用原key', async () => {
  sessionStorage.clear();
  const time = '2026-10-26T00:00:00Z';
  const makeTask = (id: number) => ({ id, task_id: id, task_type: 'finance', source_type: 'finance', status: 'failed', scheduled_at: time, created_at: time, updated_at: time, completed_attempts: 1, max_attempts: 3, next_retry_at: null, sent_at: null, failed_at: time } satisfies import('../../../../../../api/line_delivery/line_delivery_query_schemas').LineDeliveryItem);
  vi.mocked(lineDeliveryQueryClient.list).mockImplementation(async query => ({ items: query?.status === 'failed' ? [makeTask(7), makeTask(8)] : [], page: 1, page_size: 25, total: 2, total_pages: 1 }));
  vi.spyOn(lineDeliveryQueryClient, 'detail').mockImplementation(async id => ({ task: makeTask(id), attempts: [], handling: { target_kind: 'delivery_task', target_identity: String(id), needs_attention: true, allowed_actions: ['close'], blocked_reason: null } }));
  const post = vi.spyOn(transport, 'post').mockResolvedValueOnce({ data: { task_id: 7, status: 'cancelled' } }).mockRejectedValueOnce(new Error('network')).mockResolvedValue({ data: { task_id: 8, status: 'cancelled' } });
  const view = render(<LineDeliveryOperationsWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '開啟批次結清' }));
  fireEvent.click(screen.getByRole('button', { name: '載入結清候選' }));
  await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2));
  for (const checkbox of screen.getAllByRole('checkbox')) fireEvent.click(checkbox);
  fireEvent.change(screen.getByRole('textbox', { name: '批次共同結清原因' }), { target: { value: '已人工通知' } });
  fireEvent.click(screen.getByRole('button', { name: '確認批次結清' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '僅重送未成功項目' })).toBeEnabled());
  expect(post).toHaveBeenCalledTimes(2);
  expect(screen.getByText(/寄送工作 #7 已取消/)).toBeVisible();
  view.unmount();
  render(<LineDeliveryOperationsWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '開啟批次結清' }));
  fireEvent.click(screen.getByRole('button', { name: '僅重送未成功項目' }));
  await screen.findByRole('button', { name: '建立下一批' });
  expect(post).toHaveBeenCalledTimes(3);
  expect(post.mock.calls[2][0]).toBe('/api/v1/line/tasks/8/cancel');
  expect(post.mock.calls[2][1]).toEqual(post.mock.calls[1][1]);
  sessionStorage.clear();
});


it('批次阻擋後端禁止操作的候選，沒有可勾選項目', async () => {
  sessionStorage.clear();
  const time = '2026-10-26T00:00:00Z';
  const task = { id: 9, task_id: 9, task_type: 'finance', source_type: 'finance', status: 'retryable_failed', scheduled_at: time, created_at: time, updated_at: time, completed_attempts: 1, max_attempts: 3, next_retry_at: null, sent_at: null, failed_at: time } satisfies import('../../../../../../api/line_delivery/line_delivery_query_schemas').LineDeliveryItem;
  vi.mocked(lineDeliveryQueryClient.list).mockImplementation(async query => ({ items: query?.status === 'retryable_failed' ? [task] : [], page: 1, page_size: 25, total: 1, total_pages: 1 }));
  vi.spyOn(lineDeliveryQueryClient, 'detail').mockResolvedValue({ task, attempts: [], handling: { target_kind: 'delivery_task', target_identity: '9', needs_attention: true, allowed_actions: [], blocked_reason: '寄送結果尚未確認' } });
  const post = vi.spyOn(transport, 'post');
  render(<LineDeliveryOperationsWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '開啟批次結清' }));
  fireEvent.click(screen.getByRole('button', { name: '載入結清候選' }));
  await screen.findByText('工作 #9：寄送結果尚未確認');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '確認批次結清' })).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
});

it('損壞的前次批次紀錄阻擋新命令，避免換key重送', async () => {
  sessionStorage.setItem('line-notification-closure-batch:v1', '{broken');
  const post = vi.spyOn(transport, 'post');
  render(<LineDeliveryOperationsWorkbench />);
  fireEvent.click(screen.getByRole('button', { name: '開啟批次結清' }));
  expect(screen.getByRole('alert')).toHaveTextContent('無法驗證前次批次紀錄');
  expect(screen.getByRole('button', { name: '載入結清候選' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '確認批次結清' })).toBeDisabled();
  expect(post).not.toHaveBeenCalled();
  sessionStorage.clear();
});
