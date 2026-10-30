import {readFileSync} from 'node:fs';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup,within} from '@testing-library/react';
import {NotificationTasksPage} from '../../../../../../pages/NotificationTasksPreviewPage';
import {notificationTasksClient as client, type NotificationItem} from '../../../../../../api/line_notifications/notification_tasks_client';
import {lineDeliveryQueryClient as delivery} from '../../../../../../api/line_delivery/line_delivery_query_client';
import type {LineDeliveryItem} from '../../../../../../api/line_delivery/line_delivery_query_schemas';
const item=(source:NotificationItem['source']):NotificationItem=>({id:'customer_service:7',source,group:'support',title:'同一聯絡需求',case_no:'115000001',
 reference_id:7,person:'合成人物',summary:'待處理',reason:'原 owner 待辦',time:'',tag:'待處理',recipient:null,message:null,
 unavailable_reason:null,expected_version:null,delivery_status:null,payment:null,log:null,information:null});
const task:LineDeliveryItem={task_id:1,id:1,task_type:'finance',source_type:'finance',status:'failed',updated_at:'2026-10-26T00:00:00Z',
 scheduled_at:'2026-10-26T00:00:00Z',created_at:'2026-10-26T00:00:00Z',completed_attempts:1,max_attempts:3,next_retry_at:null,sent_at:null,failed_at:'2026-10-26T00:00:00Z'};
beforeEach(()=>{
 window.matchMedia=vi.fn().mockReturnValue({matches:false}) as unknown as typeof matchMedia;
 vi.spyOn(client,'catalog').mockResolvedValue([]);vi.spyOn(client,'list').mockResolvedValue({items:[],total:0,next_cursor:null});
 vi.spyOn(delivery,'list').mockResolvedValue({items:[task],total:1,page:1,page_size:6,total_pages:1});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();window.history.replaceState(null,'','/');});
it('正式頁完成後返回通知，重新查詢共享推薦與客服來源',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'recommendation',label:'推薦',group:'review'},{source:'customer_service',label:'客服',group:'support'}]);
 vi.mocked(client.list).mockImplementation(async source=>({items:[item(source)],total:1,next_cursor:null}));
 const view=render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'同一聯絡需求'});view.unmount();
 vi.mocked(client.list).mockResolvedValue({items:[],total:0,next_cursor:null});render(<NotificationTasksPage/>);
 await screen.findByRole('heading',{name:'目前沒有待辦事項'});
 expect(vi.mocked(client.list).mock.calls.filter(x=>x[0]==='recommendation')).toHaveLength(2);
 expect(vi.mocked(client.list).mock.calls.filter(x=>x[0]==='customer_service')).toHaveLength(2);
});
it('款項分類交給原寄送 API 全部資料分頁篩選，不只篩目前六筆',async()=>{
 render(<NotificationTasksPage/>);fireEvent.click(screen.getByRole('button',{name:/寄送紀錄/}));
 await screen.findByRole('heading',{name:'LINE 寄送工作'});
 vi.mocked(delivery.list).mockResolvedValue({items:[task],total:41,page:1,page_size:6,total_pages:7});
 fireEvent.click(screen.getByRole('button',{name:/款項與日誌/}));
 await waitFor(()=>expect(delivery.list).toHaveBeenLastCalledWith({page:1,pageSize:6,status:undefined,category:'reminder'},expect.anything()));
 expect(await screen.findByText('共 41 筆')).toBeVisible();
 expect(screen.getByRole('heading',{name:'LINE 寄送工作'})).toBeVisible();
});
it('寄送紀錄前往正式寄送工作，不在通知頁提供重試操作',async()=>{
 render(<NotificationTasksPage/>);fireEvent.click(screen.getByRole('button',{name:/寄送紀錄/}));
 await screen.findByRole('heading',{name:'LINE 寄送工作'});fireEvent.click(screen.getByRole('button',{name:'查看寄送工作'}));
 expect(window.location.hash).toBe('#line-management?tab=delivery&task=1');
 expect(screen.queryByRole('button',{name:'重試寄送工作'})).not.toBeInTheDocument();
});

it('手機空候選頁不顯示已無事項，跨多個空頁後只計算實際卡片',async()=>{
 const source=readFileSync('../line/static/mobile_admin.html','utf8');
 const start=source.indexOf('let notificationSequence = 0;');
 const end=source.indexOf('async function openNotificationItem(item,cursor)');
 const emptyStart=source.indexOf('function showEmpty(');
 const emptyEnd=source.indexOf('function updateReviewTotal(');
 const host=document.createElement('div');
 host.innerHTML='<div id="depositStatus"></div><div id="reviewTotal"></div><section id="reviewPane"><div class="workstream-list"></div></section><div id="notificationOperations"></div><div id="notificationSources"></div>';
 document.body.appendChild(host);
 const responses=[
  {items:[],total:null,next_cursor:'first-native-cursor'},
  {items:[],total:null,next_cursor:'second-native-cursor'},
  {items:[{...item('notification_failure'),id:'notification_failure:one',title:'有效通知'}],total:null,next_cursor:null},
 ];
 const post=vi.fn(async(path:string)=>path.endsWith('/notification-tasks')?
  [{source:'notification_failure',label:'通知異常',group:'support'}]:responses.shift());
 const load=new Function('document','postJson',"const target='staff_review';const showStatus=()=>{};"+
  source.slice(emptyStart,emptyEnd)+source.slice(start,end)+';return loadReviewWorkbench;')(document,post) as ()=>Promise<void>;
 try{
  await load();
  const section=host.querySelector('details')!;section.open=true;
  expect(within(host).queryByText('目前沒有此類待辦。')).not.toBeInTheDocument();
  expect(section.querySelector('small')).toHaveTextContent('已載入 0 件，尚有其他事項');
  fireEvent.click(within(host).getByRole('button',{name:'載入更多'}));
  await waitFor(()=>expect(post).toHaveBeenCalledTimes(3));
  await waitFor(()=>expect(within(host).getByRole('button',{name:'載入更多'})).toBeEnabled());
  fireEvent.click(within(host).getByRole('button',{name:'載入更多'}));
  await waitFor(()=>expect(host.querySelectorAll('[data-notification-id]')).toHaveLength(1));
  expect(section.querySelector('small')).toHaveTextContent('已載入 1 件');
  expect(within(host).queryByText('目前沒有此類待辦。')).not.toBeInTheDocument();
  expect(host.querySelector('#reviewTotal')).toHaveTextContent('1');
  expect(post.mock.calls.map(call=>call[0])).toEqual([
   '/api/v1/line/mobile-admin/notification-tasks',
   '/api/v1/line/mobile-admin/notification-tasks/notification_failure',
   '/api/v1/line/mobile-admin/notification-tasks/notification_failure',
   '/api/v1/line/mobile-admin/notification-tasks/notification_failure']);
 }finally{host.remove();}
});


it('LIFF 說明客戶未綁定並提供核對，核對保留草稿且不送出；讀取失敗不誤開放發送',async()=>{
 const source=readFileSync('../line/static/mobile_admin.html','utf8');
 const helpers=source.slice(source.indexOf('let notificationSequence = 0;'),source.indexOf('async function openNotificationItem(item,cursor)'));
 const factory=source.slice(source.indexOf('function candidateInformationCard(item)'),source.indexOf('let notificationSequence = 0;'));
 const info={question_id:7,pool_id:1,request_kind:'information_question',customer_answer_event_id:null,review_completed:false,
  case_no:'SYNTHETIC',staff_name:'合成月嫂',issues:[],customer_answer:null,customer_message:null,customer_available:false};
 const post=vi.fn().mockResolvedValue({items:[{reference_id:7,information:{...info,customer_available:true}}]});
 const card=new Function('document','postJson','initial',"const target='staff_review';let candidateInformationPage=1;const showStatus=()=>{};"+
  helpers+factory+';return candidateInformationCard(initial);')(document,post,info) as HTMLElement;
 document.body.appendChild(card);
 try{
  fireEvent.input(within(card).getByRole('textbox'),{target:{value:'原文案保留'}});
  expect(within(card).getByRole('button',{name:'發送給客戶'})).toBeDisabled();
  expect(within(card).getByRole('button',{name:'發送給月嫂'})).toBeEnabled();
  expect(within(card).getByText(/這位客戶尚未綁定 LINE/)).toHaveTextContent('請先聯絡客戶完成綁定');
  fireEvent.click(within(card).getByRole('button',{name:'重新核對'}));
  await waitFor(()=>expect(within(card).getByRole('button',{name:'發送給客戶'})).toBeEnabled());
  expect(within(card).getByRole('textbox')).toHaveValue('原文案保留');
  expect(post).toHaveBeenCalledWith('/api/v1/line/mobile-admin/notification-tasks/information',{cursor:0});
  post.mockRejectedValueOnce(new Error('暫時無法讀取資料，請重試。'));
  fireEvent.click(within(card).getByRole('button',{name:'重新核對'}));
  await within(card).findByText('暫時無法讀取資料，請重試。');
  expect(within(card).getByRole('button',{name:'發送給客戶'})).toBeDisabled();
  expect(within(card).getByRole('button',{name:'發送給月嫂'})).toBeDisabled();
  expect(within(card).getByText(/目前無法核對這筆需求/)).toBeVisible();
  expect(within(card).getByRole('textbox')).toHaveValue('原文案保留');
  expect(post.mock.calls.every(call=>!String(call[0]).endsWith('/send'))).toBe(true);
 }finally{card.remove();}
});
