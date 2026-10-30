import {act,render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import {ServiceStartSubstituteWorkbench} from '../../../../../../../components/ServiceStartSubstituteWorkbench';
import {SchedulingPage} from '../../../../../../../pages/SchedulingPage';
import {serviceStartClient,type ServiceStartView} from '../../../../../../../api/scheduling/service_start_client';
import {ApiHttpError} from '../../../../../../../api/shared/typed_errors';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
const item:ServiceStartView={handover_dates:[],workflow_kind:"service_start",leave_dates:[],conflict_message:null,request_id:8,case_no:'CASE',staff_id:1,staff_name:'原月嫂',segment_id:3,order_version:2,version:4,status:'substitute_required',requested_start_date:null,selected_staff_id:2,selected_staff_name:'代班月嫂',willingness:'willing',invitation_status:'sent',joined:true,proposed_start_date:'2027-01-05',proposed_end_date:'2027-02-03',result:null};
beforeEach(()=>{
 vi.spyOn(ordersQueryClient,'getAssignmentPlan').mockImplementation(async()=>({case_no:'CASE',order_version:3,scheduling_version:2,scheduling_generation:1,client_finance_version:1,payroll_version:1,contracted_service_days:1,service_hours_per_day:8,service_started:false,
  assignments:[{assignment_id:7,candidate_key:null,staff_id:2,sequence:1,assigned_start_date:'2027-01-05',assigned_end_date:'2027-01-05',official_service_dates:['2027-01-05'],actual_hours:null,lineage_source_assignment_ids:[]}]}));
});
afterEach(()=>{sessionStorage.clear();vi.restoreAllMocks();});
it('通知深連結在正式排班頁只讀指定需求，不受第一頁清單影響',async()=>{
 window.location.hash='#scheduling?tab=coordination&case_no=CASE&request=8';
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(item);
 const todos=vi.spyOn(serviceStartClient,'todos');const command=vi.spyOn(serviceStartClient,'command');
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 render(<SchedulingPage/>);await screen.findByRole('button',{name:'儲存並更新排班'});
 expect(detail).toHaveBeenCalledWith(8);expect(todos).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
 window.history.replaceState(null,'','/');
});
it('指定需求屬於別案時停止呈現，不改開其他需求',async()=>{
 vi.spyOn(serviceStartClient,'detail').mockResolvedValue({...item,case_no:'OTHER'});
 const todos=vi.spyOn(serviceStartClient,'todos');const command=vi.spyOn(serviceStartClient,'command');
 render(<ServiceStartSubstituteWorkbench caseNo="CASE" requestId={8}/>);
 await screen.findByText('指定需求與案件不一致，請從通知事項重新開啟。');
 expect(screen.queryByRole('button',{name:'儲存並更新排班'})).not.toBeInTheDocument();expect(todos).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
});
it('結果未明時重送相同操作識別，正式結果回讀後才解除凍結',async()=>{
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[item],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 const command=vi.spyOn(serviceStartClient,'command').mockRejectedValueOnce(new Error('network interrupted')).mockResolvedValueOnce({...item,status:'applied',result:{actual_start_date:'2027-01-05',actual_end_date:'2027-02-03',order_version:3,first_payment_due_date:'2027-01-05',group_record_queued:true,assignments:[{staff_id:2,staff_name:'代班月嫂',service_dates:['2027-01-05']}]}});
 render(<ServiceStartSubstituteWorkbench/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await screen.findByRole('button',{name:'確認原操作結果'});
 expect(screen.getByRole('button',{name:'儲存並更新排班'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'確認原操作結果'}));
 await screen.findByText('正式排班已完成');
 expect(command.mock.calls[0]).toEqual(command.mock.calls[1]);
 await waitFor(()=>expect(sessionStorage.getItem('service-start-command:8')).toBeNull());
});
it('尚未願意或加入時沒有填日期與邀請旁路',async()=>{
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[{...item,willingness:'pending',joined:false}],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 render(<ServiceStartSubstituteWorkbench/>);await screen.findByText(/等待月嫂回覆/);
 expect(screen.queryByRole('button',{name:'儲存並更新排班'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'寄送本案群組邀請連結'})).not.toBeInTheDocument();
});

it('請假衝突只記錄雙方新協議，直接提交逐日日期且不詢問客戶',async()=>{
 const leave={...item,workflow_kind:'leave' as const,leave_dates:[{original_date:'2027-01-05',new_date:'2027-02-10'}],
   conflict_message:'提出的日期有排程衝突，原排班尚未變更',selected_staff_id:null,selected_staff_name:null,willingness:null,joined:false};
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[leave],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValue({...await ordersQueryClient.getAssignmentPlan('CASE'),assignments:[{assignment_id:7,candidate_key:null,staff_id:leave.selected_staff_id??leave.staff_id,sequence:1,assigned_start_date:'2027-02-11',assigned_end_date:'2027-02-11',official_service_dates:['2027-02-11'],actual_hours:null,lineage_source_assignment_ids:[]}]});
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...leave,status:'applied',result:{actual_start_date:'2027-01-06',actual_end_date:'2027-02-11',order_version:3,first_payment_due_date:'2027-01-06',group_record_queued:true,assignments:[{staff_id:leave.selected_staff_id??leave.staff_id,staff_name:'實際服務月嫂',service_dates:['2027-02-11']}]}});
 render(<ServiceStartSubstituteWorkbench/>);
 const date=await screen.findByLabelText('2027-01-05 實際服務日');
 expect(command).not.toHaveBeenCalled();
 fireEvent.change(date,{target:{value:'2027-02-11'}});
 fireEvent.click(screen.getByRole('button',{name:'儲存順延日期並更新排班'}));
 await screen.findByText('正式排班已完成');
 expect(command).toHaveBeenCalledWith(8,'defer',expect.objectContaining({expected_version:4,dates:[{original_date:'2027-01-05',new_date:'2027-02-11'}]}));
 expect(screen.queryByText('請客戶確認')).not.toBeInTheDocument();
});

it('請假代班須願意並加入，才可記錄實際逐日服務日期',async()=>{
 const leave={...item,workflow_kind:'leave' as const,leave_dates:[{original_date:'2027-01-05',new_date:null}]};
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[leave],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValue({...await ordersQueryClient.getAssignmentPlan('CASE'),assignments:[{assignment_id:7,candidate_key:null,staff_id:leave.selected_staff_id??leave.staff_id,sequence:1,assigned_start_date:'2027-02-11',assigned_end_date:'2027-02-11',official_service_dates:['2027-02-11'],actual_hours:null,lineage_source_assignment_ids:[]}]});
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...leave,status:'applied',result:{actual_start_date:'2027-01-06',actual_end_date:'2027-02-11',order_version:3,first_payment_due_date:'2027-01-06',group_record_queued:true,assignments:[{staff_id:leave.selected_staff_id??leave.staff_id,staff_name:'實際服務月嫂',service_dates:['2027-02-11']}]}});
 render(<ServiceStartSubstituteWorkbench/>);
 await screen.findByRole('button',{name:'儲存並更新排班'});
 fireEvent.change(screen.getByLabelText('2027-01-05 實際服務日'),{target:{value:'2027-02-11'}});
 fireEvent.click(screen.getByRole('button',{name:'儲存並更新排班'}));
 await waitFor(()=>expect(command).toHaveBeenCalledWith(8,'dates',expect.objectContaining({start_date:'2027-02-11',date_changes:[{original_date:'2027-01-05',new_date:'2027-02-11'}]})));
});

function complete():ServiceStartView {
 return {...item,status:'applied',result:{actual_start_date:'2027-01-05',actual_end_date:'2027-02-03',order_version:3,first_payment_due_date:'2027-01-05',group_record_queued:true,assignments:[{staff_id:2,staff_name:'代班月嫂',service_dates:['2027-01-05']}]}};
}
function installCommand(result=complete()) {
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[item],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 return vi.spyOn(serviceStartClient,'command').mockResolvedValue(result);
}
it.each(['case','person','request'] as const)('完成回應的 %s 不符時不顯示成功，保留只讀查核而非重送',async(kind)=>{
 const result=complete();
 if(kind==='case')result.case_no='OTHER';
 if(kind==='person')result.selected_staff_id=999;
 if(kind==='request')result.request_id=999;
 const command=installCommand(result);const onCompleted=vi.fn().mockResolvedValue(undefined);
 render(<ServiceStartSubstituteWorkbench caseNo='CASE' onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('排班結果尚未完成正式回讀。');
 expect(screen.queryByText('正式排班已完成')).not.toBeInTheDocument();
 expect(onCompleted).not.toHaveBeenCalled();expect(command).toHaveBeenCalledOnce();
 expect(ordersQueryClient.getAssignmentPlan).not.toHaveBeenCalled();
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 expect(screen.getByRole('button',{name:'重新讀取排班結果'})).toBeEnabled();
});
it.each(['person','date','version'] as const)('正式 owner 的 %s 與完成回應不同時不可宣告完成',async(kind)=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 if(kind==='person')plan.assignments=[{...plan.assignments[0],staff_id:999}];
 if(kind==='date')plan.assignments=[{...plan.assignments[0],official_service_dates:['2027-01-06']}];
 if(kind==='version')plan.order_version=2;
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValue(plan);
 installCommand();const onCompleted=vi.fn().mockResolvedValue(undefined);
 render(<ServiceStartSubstituteWorkbench onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('排班結果尚未完成正式回讀。');
 expect(screen.queryByText('正式排班已完成')).not.toBeInTheDocument();expect(onCompleted).not.toHaveBeenCalled();
 expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledOnce();
});
it.each([false,true])('收據後回讀失敗，重新開頁 %s 也只重新讀取、不重複寫入',async(remount)=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(new ApiHttpError(503,'read_unavailable','unavailable')).mockResolvedValue(plan);
 const command=installCommand();const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 const onCompleted=vi.fn().mockResolvedValue(undefined);
 let view=render(<ServiceStartSubstituteWorkbench caseNo='CASE' onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await screen.findByRole('alert');expect(onCompleted).not.toHaveBeenCalled();
 if(remount){view.unmount();vi.mocked(serviceStartClient.todos).mockResolvedValue({items:[],total:0,page:1,page_size:25});view=render(<ServiceStartSubstituteWorkbench caseNo='CASE' onCompleted={onCompleted}/>);}
 const retry=await screen.findByRole('button',{name:'重新讀取排班結果'});fireEvent.click(retry);
 await waitFor(()=>expect(onCompleted).toHaveBeenCalledOnce());
 expect(await screen.findByText('正式排班已完成')).toBeInTheDocument();
 expect(command).toHaveBeenCalledOnce();expect(detail).toHaveBeenCalledTimes(remount?2:1);
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});
it('正式回讀尚未返回就離開，不通知另一個畫面完成且保留只讀恢復標記',async()=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 let resolve!:(value:typeof plan)=>void;vi.mocked(ordersQueryClient.getAssignmentPlan).mockReturnValue(new Promise(done=>{resolve=done;}));
 const command=installCommand();const onCompleted=vi.fn().mockResolvedValue(undefined);
 const view=render(<ServiceStartSubstituteWorkbench onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await waitFor(()=>expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledOnce());view.unmount();
 await act(async()=>{resolve(plan);});
 expect(onCompleted).not.toHaveBeenCalled();expect(command).toHaveBeenCalledOnce();
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
});

it('結果未明後一般查詢讀到完成結果，即使正式回讀失敗也不再重送命令',async()=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(new Error('readback unavailable')).mockResolvedValue(plan);
 const command=installCommand();command.mockRejectedValue(new Error('outcome unknown'));
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 const onCompleted=vi.fn().mockResolvedValue(undefined);
 render(<ServiceStartSubstituteWorkbench onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await screen.findByRole('button',{name:'確認原操作結果'});
 fireEvent.click(screen.getByRole('button',{name:'重新查詢加入狀態'}));
 await screen.findByText('排班結果尚未完成正式回讀。');
 expect(onCompleted).not.toHaveBeenCalled();
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'重新讀取排班結果'}));
 await screen.findByText('正式排班已完成');
 expect(command).toHaveBeenCalledOnce();expect(detail).toHaveBeenCalledTimes(2);
 expect(onCompleted).toHaveBeenCalledOnce();
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});

it('重新開頁查到完成結果時將原未明命令轉為只讀恢復',async()=>{
 sessionStorage.setItem('service-start-command:8',JSON.stringify({id:8,action:'dates',body:{expected_version:4,idempotency_key:'original-command'}}));
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[],total:0,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 const command=vi.spyOn(serviceStartClient,'command').mockRejectedValue(new Error('must not repeat'));
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValue(new Error('readback unavailable'));
 render(<ServiceStartSubstituteWorkbench/>);
 await screen.findByText('排班結果尚未完成正式回讀。');
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 expect(screen.getByRole('button',{name:'重新讀取排班結果'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:'確認原操作結果'})).not.toBeInTheDocument();
 expect(command).not.toHaveBeenCalled();
});

it('結果未明後查詢完成並核對正式排班，直接同步待辦總數而不重送',async()=>{
 const command=installCommand();command.mockRejectedValue(new Error('outcome unknown'));
 vi.mocked(serviceStartClient.todos).mockResolvedValueOnce({items:[item],total:1,page:1,page_size:25})
  .mockResolvedValue({items:[],total:0,page:1,page_size:25});
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 const onCompleted=vi.fn().mockResolvedValue(undefined);
 render(<ServiceStartSubstituteWorkbench onCompleted={onCompleted}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await screen.findByRole('button',{name:'確認原操作結果'});
 fireEvent.click(screen.getByRole('button',{name:'重新查詢加入狀態'}));
 await screen.findByText('正式排班已完成');
 expect(screen.getByText('0 件待處理')).toBeInTheDocument();
 expect(command).toHaveBeenCalledOnce();expect(detail).toHaveBeenCalledOnce();
 expect(onCompleted).toHaveBeenCalledOnce();
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
 expect(screen.queryByRole('button',{name:'確認原操作結果'})).not.toBeInTheDocument();
});

it('同案多月嫂分段及不連續服務日期與正式排班一致時可完成回讀',async()=>{
 const result=complete();
 result.result!.assignments=[
  {staff_id:1,staff_name:'原月嫂',service_dates:['2027-01-03']},
  {staff_id:2,staff_name:'代班月嫂',service_dates:['2027-01-07','2027-01-05']},
 ];
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');
 const row=plan.assignments[0];
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValue({...plan,assignments:[
  {...row,assignment_id:9,official_service_dates:['2027-01-07']},
  {...row,assignment_id:8,staff_id:1,official_service_dates:['2027-01-03']},
  {...row,official_service_dates:['2027-01-05']},
 ]});
 installCommand(result);
 render(<ServiceStartSubstituteWorkbench/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存並更新排班'}));
 await screen.findByText('正式排班已完成');
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});
