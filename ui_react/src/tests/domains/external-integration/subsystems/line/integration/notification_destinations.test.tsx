/**
 * File: notification_destinations.test.tsx
 * Description: 驗證通知中心深連結導向、人工指引及入帳待辦標記已通知操作。
 */
import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { afterEach,beforeEach,expect,it,vi } from 'vitest';
import { NotificationTasksPage } from '../../../../../../pages/NotificationTasksPreviewPage';
import { notificationTasksClient as client,type NotificationItem,type NotificationSource } from '../../../../../../api/line_notifications/notification_tasks_client';
import { lineDeliveryQueryClient } from '../../../../../../api/line_delivery/line_delivery_query_client';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { transport } from '../../../../../../api/shared/transport';
const key='ci_'+'1'.repeat(64);
const item=(source:NotificationSource):NotificationItem=>({id:`${source}:73`,source,group:'review',title:'指定事項',case_no:'116000001',reference_id:73,person:'測試對象',summary:'摘要',reason:'待辦原因',time:'',tag:'待處理',recipient:null,message:'人工操作指引',unavailable_reason:null,expected_version:null,delivery_status:null,payment:null,log:null,failure:source==='notification_failure'?{issue_key:key,notification_reason:'recipient_unavailable',related_task_ids:[]}:null});
beforeEach(()=>{
 window.matchMedia=vi.fn().mockReturnValue({matches:false}) as unknown as typeof matchMedia;
 vi.spyOn(client,'catalog');vi.spyOn(client,'list');
 vi.spyOn(lineDeliveryQueryClient,'list').mockResolvedValue({items:[],total:0,page:1,page_size:6,total_pages:1});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();window.history.replaceState(null,'','/');});
it.each(['deposit','first','second'] as const)('%s 入帳通知只引導到帳務確認，不從通知中心寄送',async stage=>{
 const value={...item('payment_receipt'),receipt:{payment_stage:stage,settlement_identity:'a'.repeat(64)}};
 vi.mocked(client.catalog).mockResolvedValue([{source:'payment_receipt',label:'入帳待確認',group:'reminder'}]);
 vi.mocked(client.list).mockResolvedValue({items:[value],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post');render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 fireEvent.click(screen.getByRole('button',{name:'前往帳務確認'}));
 const query=new URLSearchParams(window.location.hash.split('?')[1]);
 expect(window.location.hash).toContain('#finance?');expect(query.get('tab')).toBe('accounting-warnings');
 expect(query.get('case_no')).toBe('116000001');expect(query.get('receipt_stage')).toBe(stage);
 expect(query.get('settlement_identity')).toBe('a'.repeat(64));expect(post).not.toHaveBeenCalled();
});
it('入帳待辦帶齊快照欄位時，可直接點選已於官方帳號發送／標記已通知並呼叫消除端點',async()=>{
 const value={...item('payment_receipt'),receipt:{payment_stage:'deposit' as const,settlement_identity:'a'.repeat(64),amount_ntd:12000,source_version:2,source_reference:'src-ref'}};
 vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-token');
 vi.mocked(client.catalog).mockResolvedValue([{source:'payment_receipt',label:'入帳待確認',group:'reminder'}]);
 vi.mocked(client.list).mockResolvedValue({items:[value],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post').mockResolvedValue({data:{task_id:1,status:'completed'}});
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 fireEvent.click(screen.getByRole('button',{name:/已於官方帳號發送／標記已通知/}));
 await waitFor(()=>expect(post).toHaveBeenCalledWith('/api/v1/line/payment-overdue-reminders/receipts/send',{
  case_no:'116000001',payment_stage:'deposit',settlement_identity:'a'.repeat(64),amount_ntd:12000,source_version:2,source_reference:'src-ref',
 },expect.any(Object)));
 expect(await screen.findByRole('status')).toHaveTextContent('已標記入帳通知為已發送');
});
it.each([
 ['registration','查看申請','#clients?tab=applications&registration=73'],
 ['service_start','處理換人交接','#scheduling?tab=coordination&case_no=116000001&request=73'],
 ['delivery','查看寄送工作','#line-management?tab=delivery&task=73'],
 ['notification_failure','處理通知建立異常',`#line-management?tab=delivery&view=failures&issue=${key}`],
] as const)('%s 只跳轉指定事項，不在通知頁查詢或執行原操作',async(source,button,href)=>{
 vi.mocked(client.catalog).mockResolvedValue([{source,label:'指定來源',group:'review'}]);
 vi.mocked(client.list).mockResolvedValue({items:[item(source)],total:1,next_cursor:null});
 const get=vi.spyOn(transport,'get'),post=vi.spyOn(transport,'post');
 render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 fireEvent.click(screen.getByRole('button',{name:button}));
 expect(window.location.hash).toBe(href);
 expect(document.querySelector('.notification-task-operation')).toBeNull();
 expect(get).not.toHaveBeenCalled();expect(post).not.toHaveBeenCalled();
});
it('客戶未綁定提醒只顯示單案移除操作，開啟時不執行異動',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'customer_binding',label:'客戶未綁定',group:'review'}]);
 vi.mocked(client.list).mockResolvedValue({items:[{...item('customer_binding'),can_dismiss:true,recipient:'0900000000'}],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post');render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 expect(screen.getByRole('button',{name:'移除提醒'})).toBeVisible();
 expect(screen.queryByRole('heading',{name:'聯絡 測試對象'})).not.toBeInTheDocument();
 expect(screen.queryByText('0900000000')).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/複製綁定提醒|查看人工提醒方式/})).not.toBeInTheDocument();
 expect(screen.queryByRole('link',{name:/查看綁定狀態|查看本案資料/})).not.toBeInTheDocument();
 expect(post).not.toHaveBeenCalled();
});
it('月嫂綁定提醒直接顯示人工聯絡與複製操作，開啟時不執行異動',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'staff_binding',label:'月嫂未綁定',group:'review'}]);
 vi.mocked(client.list).mockResolvedValue({items:[{...item('staff_binding'),recipient:'0900000000'}],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post');render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 expect(screen.getByRole('heading',{name:'聯絡 測試對象'})).toBeVisible();
 expect(screen.getByRole('link',{name:'電話聯絡 0900000000'})).toHaveAttribute('href','tel:0900000000');
 expect(screen.getByRole('button',{name:'複製綁定提醒'})).toBeVisible();
 expect(screen.queryByRole('button',{name:'移除提醒'})).not.toBeInTheDocument();
 expect(post).not.toHaveBeenCalled();
});
it('開啟案件建群指令時不執行異動',async()=>{
 vi.mocked(client.catalog).mockResolvedValue([{source:'group',label:'人工事項',group:'review'}]);
 vi.mocked(client.list).mockResolvedValue({items:[item('group')],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post');render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 fireEvent.click(screen.getByRole('button',{name:'查看建群指令'}));
 expect(screen.getByRole('heading',{name:'建立與綁定案件群組'})).toBeVisible();
 expect(post).not.toHaveBeenCalled();
});
