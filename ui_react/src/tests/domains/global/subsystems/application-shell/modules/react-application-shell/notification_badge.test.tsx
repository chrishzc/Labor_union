import {act,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MasterLayout} from '../../../../../../../components/MasterLayout';
import {notificationTasksClient as client,notifyNotificationTasksChanged} from '../../../../../../../api/line_notifications/notification_tasks_client';
import * as system from '../../../../../../../api/system/system_status_client';
const props={currentSection:'operations' as const,currentPage:'order-workbench-v2' as const,onSelectSection:vi.fn(),onSelectPage:vi.fn(),onLogout:vi.fn()};
beforeEach(()=>{
 vi.spyOn(system,'fetchPerformanceSnapshot').mockRejectedValue(new Error('offline'));
});
afterEach(()=>vi.restoreAllMocks());
it('顯示完整待辦數量，處理後事件重新查詢，不以本機扣數',async()=>{
 const count=vi.spyOn(client,'pendingCount').mockResolvedValueOnce(28).mockResolvedValueOnce(3);
 render(<MasterLayout {...props}/>);
 expect(await screen.findByLabelText('28 項待辦')).toHaveTextContent('28');
 act(()=>notifyNotificationTasksChanged());
 expect(await screen.findByLabelText('3 項待辦')).toHaveTextContent('3');
 expect(count).toHaveBeenCalledTimes(2);
});
it('任一來源失敗顯示數量未知，不把失敗當零',async()=>{
 vi.spyOn(client,'pendingCount').mockRejectedValue(new Error('source unavailable'));
 render(<MasterLayout {...props}/>);
 expect(await screen.findByLabelText('待辦數量無法確認，點此查看')).toHaveTextContent('?');
 expect(screen.queryByLabelText('0 項待辦')).not.toBeInTheDocument();
});
it('同時刷新不併發，處理事件於既有查詢後補讀一次',async()=>{
 let finish!:(count:number)=>void;
 const count=vi.spyOn(client,'pendingCount').mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})).mockResolvedValue(4);
 render(<MasterLayout {...props}/>);
 act(()=>{window.dispatchEvent(new Event('focus'));notifyNotificationTasksChanged();notifyNotificationTasksChanged()});
 expect(count).toHaveBeenCalledTimes(1);
 await act(async()=>finish(8));
 await waitFor(()=>expect(count).toHaveBeenCalledTimes(2));
 expect(await screen.findByLabelText('4 項待辦')).toBeVisible();
});
it('離開通知頁會重新核對，其他頁面切換不重查',async()=>{
 const count=vi.spyOn(client,'pendingCount').mockResolvedValue(0);
 const view=render(<MasterLayout {...props}/>);
 await screen.findByLabelText('0 項待辦');
 view.rerender(<MasterLayout {...props} currentPage="clients"/>);
 expect(count).toHaveBeenCalledTimes(1);
 view.rerender(<MasterLayout {...props} currentPage="notifications"/>);
 await waitFor(()=>expect(count).toHaveBeenCalledTimes(2));
 view.rerender(<MasterLayout {...props} currentPage="clients"/>);
 await waitFor(()=>expect(count).toHaveBeenCalledTimes(3));
});
