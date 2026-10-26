import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {it,expect,vi,afterEach} from 'vitest';
import {ServiceStartSubstituteWorkbench} from '../../../../../../../components/ServiceStartSubstituteWorkbench';
import {serviceStartClient,type ServiceStartView} from '../../../../../../../api/scheduling/service_start_client';
const item:ServiceStartView={handover_dates:[],workflow_kind:"service_start",leave_dates:[],conflict_message:null,request_id:8,case_no:'CASE',staff_id:1,staff_name:'原月嫂',segment_id:3,order_version:2,version:4,status:'substitute_required',requested_start_date:null,selected_staff_id:2,selected_staff_name:'代班月嫂',willingness:'willing',invitation_status:'sent',joined:true,proposed_start_date:'2027-01-05',proposed_end_date:'2027-02-03',result:null};
afterEach(()=>{sessionStorage.clear();vi.restoreAllMocks();});
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
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...leave,status:'applied',result:{actual_start_date:'2027-01-06',actual_end_date:'2027-02-11',order_version:3,first_payment_due_date:'2027-01-06',group_record_queued:true,assignments:[]}});
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
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...leave,status:'applied',result:{actual_start_date:'2027-01-06',actual_end_date:'2027-02-11',order_version:3,first_payment_due_date:'2027-01-06',group_record_queued:true,assignments:[]}});
 render(<ServiceStartSubstituteWorkbench/>);
 await screen.findByRole('button',{name:'儲存並更新排班'});
 fireEvent.change(screen.getByLabelText('2027-01-05 實際服務日'),{target:{value:'2027-02-11'}});
 fireEvent.click(screen.getByRole('button',{name:'儲存並更新排班'}));
 await waitFor(()=>expect(command).toHaveBeenCalledWith(8,'dates',expect.objectContaining({start_date:'2027-02-11',date_changes:[{original_date:'2027-01-05',new_date:'2027-02-11'}]})));
});
