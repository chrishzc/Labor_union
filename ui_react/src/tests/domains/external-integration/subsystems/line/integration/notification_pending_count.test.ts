import {afterEach,expect,it,vi} from 'vitest';
import {notificationTasksClient as client,type NotificationItem,type NotificationSource} from '../../../../../../api/line_notifications/notification_tasks_client';
const item=(source:NotificationSource,id:string,reference_id:number|null=null):NotificationItem=>({id,source,group:'review',title:'待辦',summary:'待辦',reason:'待辦',case_no:null,reference_id,person:'',time:'',tag:'',recipient:null,message:null,unavailable_reason:null,expected_version:null,delivery_status:null,payment:null,log:null});
afterEach(()=>vi.restoreAllMocks());
it('走完空頁與所有cursor，再依原工作ID去除寄送重複事項',async()=>{
 vi.spyOn(client,'catalog').mockResolvedValue([{source:'delivery',label:'寄送',group:'support'},{source:'notification_failure',label:'異常',group:'support'},{source:'customer_binding',label:'綁定',group:'review'}]);
 const failure={...item('notification_failure','notification_failure:one'),failure:{issue_key:'ci_'+'a'.repeat(64),notification_reason:'recipient_unavailable' as const,related_task_ids:[2]}};
 const list=vi.spyOn(client,'list').mockImplementation(async(source,cursor=0)=>{
  if(source==='notification_failure')return cursor===0?{items:[],total:null,next_cursor:'next'}:{items:[failure],total:null,next_cursor:null};
  if(source==='customer_binding')return {items:[item(source,'customer_binding:1')],total:1,next_cursor:null};
  return cursor===0?{items:[item(source,'delivery:1',1),item(source,'delivery:2',2)],total:null,next_cursor:1}:{items:[item(source,'delivery:1',1),item(source,'delivery:3',3)],total:null,next_cursor:null};
 });
 expect(await client.pendingCount()).toBe(4);
 expect(list).toHaveBeenCalledTimes(5);
});
it('來源讀取失敗不能回傳部分總數',async()=>{
 vi.spyOn(client,'catalog').mockResolvedValue([{source:'delivery',label:'寄送',group:'support'}]);
 vi.spyOn(client,'list').mockRejectedValue(new Error('unavailable'));
 await expect(client.pendingCount()).rejects.toThrow('unavailable');
});
it('重複cursor以失敗結束，避免無限讀取或假完整數量',async()=>{
 vi.spyOn(client,'catalog').mockResolvedValue([{source:'delivery',label:'寄送',group:'support'}]);
 vi.spyOn(client,'list').mockResolvedValue({items:[],total:null,next_cursor:0});
 await expect(client.pendingCount()).rejects.toThrow('分頁無法確認');
});
