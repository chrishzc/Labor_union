import { cleanup,fireEvent,render,screen } from '@testing-library/react';
import { afterEach,beforeEach,expect,it,vi } from 'vitest';
import { NotificationTasksPage } from '../../../../../../pages/NotificationTasksPreviewPage';
import { notificationTasksClient as client,type NotificationItem,type NotificationSource } from '../../../../../../api/line_notifications/notification_tasks_client';
import { lineDeliveryQueryClient } from '../../../../../../api/line_delivery/line_delivery_query_client';
import { transport } from '../../../../../../api/shared/transport';
const key='ci_'+'1'.repeat(64);
const item=(source:NotificationSource):NotificationItem=>({id:`${source}:73`,source,group:'review',title:'指定事項',case_no:'116000001',reference_id:73,person:'測試對象',summary:'摘要',reason:'待辦原因',time:'',tag:'待處理',recipient:null,message:'人工操作指引',unavailable_reason:null,expected_version:null,delivery_status:null,payment:null,log:null,information:null,failure:source==='notification_failure'?{issue_key:key,notification_reason:'recipient_unavailable',related_task_ids:[]}:null});
beforeEach(()=>{
 window.matchMedia=vi.fn().mockReturnValue({matches:false}) as unknown as typeof matchMedia;
 vi.spyOn(client,'catalog');vi.spyOn(client,'list');
 vi.spyOn(lineDeliveryQueryClient,'list').mockResolvedValue({items:[],total:0,page:1,page_size:6,total_pages:1});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();window.history.replaceState(null,'','/');});
it.each([
 ['registration','查看申請','#clients?tab=applications&registration=73'],
 ['profile','審核資料異動','#clients?tab=profile-requests&request=73'],
 ['information','處理確認與條件','#order-workbench-v2?case=116000001&work=matching&question=73'],
 ['service_start','處理日期與代班','#scheduling?tab=coordination&case_no=116000001&request=73'],
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
it.each(['customer_binding','staff_binding','group'] as const)('%s 保留人工操作指引，開啟時不執行異動',async source=>{
 vi.mocked(client.catalog).mockResolvedValue([{source,label:'人工事項',group:'review'}]);
 vi.mocked(client.list).mockResolvedValue({items:[item(source)],total:1,next_cursor:null});
 const post=vi.spyOn(transport,'post');render(<NotificationTasksPage/>);await screen.findByRole('heading',{name:'指定事項'});
 fireEvent.click(screen.getByRole('button',{name:source==='group'?'查看建群指令':'查看人工提醒方式'}));
 expect(screen.getByRole('heading',{name:source==='group'?'建立與綁定案件群組':'聯絡 測試對象'})).toBeVisible();
 expect(post).not.toHaveBeenCalled();
});
