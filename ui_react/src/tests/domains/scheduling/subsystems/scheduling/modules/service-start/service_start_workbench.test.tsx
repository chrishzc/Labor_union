import {act,render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi,beforeEach,afterEach} from 'vitest';
import {ServiceStartSubstituteWorkbench} from '../../../../../../../components/ServiceStartSubstituteWorkbench';
import {SchedulingPage} from '../../../../../../../pages/SchedulingPage';
import {serviceStartClient,type ServiceStartView} from '../../../../../../../api/scheduling/service_start_client';
import {ApiHttpError} from '../../../../../../../api/shared/typed_errors';
import {sessionClient} from '../../../../../../../api/auth/session_client';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
const item:ServiceStartView={handover_dates:["2027-01-05"],workflow_kind:"handover",leave_dates:[],conflict_message:null,request_id:8,case_no:'CASE',staff_id:1,staff_name:'原月嫂',segment_id:3,order_version:2,version:4,status:'substitute_required',requested_start_date:null,selected_staff_id:2,selected_staff_name:'代班月嫂',willingness:'willing',invitation_status:'sent',joined:true,proposed_start_date:'2027-01-05',proposed_end_date:'2027-02-03',result:null};
beforeEach(()=>{
 vi.spyOn(ordersQueryClient,'getAssignmentPlan').mockImplementation(async()=>({case_no:'CASE',order_version:3,scheduling_version:2,scheduling_generation:1,client_finance_version:1,payroll_version:1,contracted_service_days:1,service_hours_per_day:8,service_started:false,
  assignments:[{assignment_id:7,candidate_key:null,staff_id:2,sequence:1,assigned_start_date:'2027-01-05',assigned_end_date:'2027-01-05',official_service_dates:['2027-01-05'],actual_hours:null,lineage_source_assignment_ids:[]}]}));
});
afterEach(()=>{sessionClient.clearSession();sessionStorage.clear();window.history.replaceState(null,'','/');vi.restoreAllMocks();});
it('通知深連結在正式排班頁只讀指定需求，不受第一頁清單影響',async()=>{
 window.location.hash='#scheduling?tab=coordination&case_no=CASE&request=8';
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(item);
 const todos=vi.spyOn(serviceStartClient,'todos');const command=vi.spyOn(serviceStartClient,'command');
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 render(<SchedulingPage/>);await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'});
 expect(detail).toHaveBeenCalledWith(8);expect(todos).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
 window.history.replaceState(null,'','/');
});
it('指定需求屬於別案時停止呈現，不改開其他需求',async()=>{
 vi.spyOn(serviceStartClient,'detail').mockResolvedValue({...item,case_no:'OTHER'});
 const todos=vi.spyOn(serviceStartClient,'todos');const command=vi.spyOn(serviceStartClient,'command');
 window.history.replaceState(null, '', '#scheduling?tab=coordination&case_no=CASE&request=8');
 render(<SchedulingPage/>);
 await screen.findByRole('alert');
 expect(screen.getByRole('alert')).toHaveTextContent('無法確認案件或排班權限');
 expect(screen.queryByRole('button',{name:'儲存交接日並更新排班與帳務'})).not.toBeInTheDocument();expect(todos).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
});
it('結果未明時重送相同操作識別，正式結果回讀後才解除凍結',async()=>{
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[item],total:1,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 const command=vi.spyOn(serviceStartClient,'command').mockRejectedValueOnce(new Error('network interrupted')).mockResolvedValueOnce({...item,status:'applied',result:{actual_start_date:'2027-01-05',actual_end_date:'2027-02-03',order_version:3,first_payment_due_date:'2027-01-05',group_record_queued:true,assignments:[{staff_id:2,staff_name:'代班月嫂',service_dates:['2027-01-05']}]}});
 render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByRole('button',{name:'確認原操作結果'});
 expect(screen.getByRole('button',{name:'儲存交接日並更新排班與帳務'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'確認原操作結果'}));
 await screen.findByText('正式排班已完成');
 expect(command.mock.calls[0]).toEqual(command.mock.calls[1]);
 await waitFor(()=>expect(sessionStorage.getItem('service-start-command:8')).toBeNull());
});
it('尚未願意或加入時沒有填日期與邀請旁路',async()=>{
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 render(<ServiceStartSubstituteWorkbench initial={{...item,willingness:'pending',joined:false}}/>);
 await screen.findByText(/等待月嫂回覆/);
 expect(screen.queryByRole('button',{name:'儲存交接日並更新排班與帳務'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'寄送本案群組邀請連結'})).not.toBeInTheDocument();
});

it.each(['service_start','leave'] as const)('舊 %s 需求導向已核對案件的多月嫂排班，開頁零寫入',async(workflow_kind)=>{
 sessionClient.setSession('synthetic-token', {id:1,username:'fixture',display_name:'Fixture',role:'system_admin',capabilities:['system.administration']});
 window.history.replaceState(null, '', '#scheduling?tab=coordination&case_no=CASE&request=8');
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue({...item,workflow_kind,joined:false});
 const ask=vi.spyOn(serviceStartClient,'options');
 const command=vi.spyOn(serviceStartClient,'command');
 render(<SchedulingPage/>);
 await waitFor(()=>expect(window.location.hash).toBe('#order-workbench-v2?case=CASE&work=service&staffing=upcoming'));
 expect(detail).toHaveBeenCalledWith(8);
 expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledWith('CASE', expect.anything());
 expect(ask).not.toHaveBeenCalled();
 expect(command).not.toHaveBeenCalled();
 expect(screen.queryByRole('button',{name:'儲存交接日並更新排班與帳務'})).not.toBeInTheDocument();
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
 const command=installCommand(result);
 render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('尚未確認最新排班結果。');
 expect(screen.queryByText('正式排班已完成')).not.toBeInTheDocument();
 expect(command).toHaveBeenCalledOnce();
 expect(ordersQueryClient.getAssignmentPlan).not.toHaveBeenCalled();
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 expect(screen.getByRole('button',{name:'查詢排班結果'})).toBeEnabled();
});
it.each(['person','date','version'] as const)('正式 owner 的 %s 與完成回應不同時不可宣告完成',async(kind)=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 if(kind==='person')plan.assignments=[{...plan.assignments[0],staff_id:999}];
 if(kind==='date')plan.assignments=[{...plan.assignments[0],official_service_dates:['2027-01-06']}];
 if(kind==='version')plan.order_version=2;
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockResolvedValue(plan);
 installCommand();
 render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('尚未確認最新排班結果。');
 expect(screen.queryByText('正式排班已完成')).not.toBeInTheDocument();
 expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledOnce();
});
it.each([false,true])('收據後回讀失敗，重新開頁 %s 也只重新讀取、不重複寫入',async(remount)=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(new ApiHttpError(503,'read_unavailable','unavailable')).mockResolvedValue(plan);
 const command=installCommand();const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 let view=render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByRole('alert');
 if(remount){view.unmount();view=render(<ServiceStartSubstituteWorkbench initial={complete()}/>);}
 const retry=await screen.findByRole('button',{name:'查詢排班結果'});fireEvent.click(retry);
 expect(await screen.findByText('正式排班已完成')).toBeInTheDocument();
 expect(command).toHaveBeenCalledOnce();expect(detail).toHaveBeenCalledTimes(1);
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});
it('正式回讀尚未返回就離開，保留只讀恢復標記',async()=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 let resolve!:(value:typeof plan)=>void;vi.mocked(ordersQueryClient.getAssignmentPlan).mockReturnValue(new Promise(done=>{resolve=done;}));
 const command=installCommand();
 const view=render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await waitFor(()=>expect(ordersQueryClient.getAssignmentPlan).toHaveBeenCalledOnce());view.unmount();
 await act(async()=>{resolve(plan);});
 expect(command).toHaveBeenCalledOnce();
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
});

it('結果未明後一般查詢讀到完成結果，即使正式回讀失敗也不再重送命令',async()=>{
 const plan=await ordersQueryClient.getAssignmentPlan('CASE');vi.mocked(ordersQueryClient.getAssignmentPlan).mockClear();
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValueOnce(new Error('readback unavailable')).mockResolvedValue(plan);
 const command=installCommand();command.mockRejectedValue(new Error('outcome unknown'));
 const detail=vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByRole('button',{name:'確認原操作結果'});
 fireEvent.click(screen.getByRole('button',{name:'重新查詢加入狀態'}));
 await screen.findByText('尚未確認最新排班結果。');

 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 fireEvent.click(screen.getByRole('button',{name:'查詢排班結果'}));
 await screen.findByText('正式排班已完成');
 expect(command).toHaveBeenCalledOnce();expect(detail).toHaveBeenCalledTimes(2);
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});

it('重新開頁查到完成結果時將原未明命令轉為只讀恢復',async()=>{
 sessionStorage.setItem('service-start-command:8',JSON.stringify({id:8,action:'dates',body:{expected_version:4,idempotency_key:'original-command'}}));
 vi.spyOn(serviceStartClient,'todos').mockResolvedValue({items:[],total:0,page:1,page_size:25});
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[]});
 vi.spyOn(serviceStartClient,'detail').mockResolvedValue(complete());
 const command=vi.spyOn(serviceStartClient,'command').mockRejectedValue(new Error('must not repeat'));
 vi.mocked(ordersQueryClient.getAssignmentPlan).mockRejectedValue(new Error('readback unavailable'));
 render(<ServiceStartSubstituteWorkbench initial={complete()}/>);
 await screen.findByText('尚未確認最新排班結果。');
 expect(JSON.parse(sessionStorage.getItem('service-start-command:8')!).observeOnly).toBe(true);
 expect(screen.getByRole('button',{name:'查詢排班結果'})).toBeEnabled();
 expect(screen.queryByRole('button',{name:'確認原操作結果'})).not.toBeInTheDocument();
 expect(command).not.toHaveBeenCalled();
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
 render(<ServiceStartSubstituteWorkbench initial={item}/>);
 fireEvent.click(await screen.findByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByText('正式排班已完成');
 expect(sessionStorage.getItem('service-start-command:8')).toBeNull();
});
