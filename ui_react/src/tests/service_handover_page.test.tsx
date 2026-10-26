import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {ServiceHandoverPage} from '../pages/ServiceHandoverPage';
import {serviceStartClient,type ServiceStartView,type HandoverContext} from '../api/scheduling/service_start_client';
import {ApiHttpError} from '../api/shared/typed_errors';
import {parseServiceHandoverLink,serviceHandoverHref} from '../adapters/scheduling/service_handover_navigation';
const request:ServiceStartView={request_id:8,case_no:'CASE',staff_id:1,staff_name:'原月嫂',segment_id:null,order_version:2,version:4,status:'substitute_required',requested_start_date:null,
 selected_staff_id:2,selected_staff_name:'接任月嫂',willingness:'pending',invitation_status:null,joined:false,result:null,proposed_start_date:'2027-01-05',proposed_end_date:'2027-01-07',
 workflow_kind:'handover',leave_dates:[],handover_dates:['2027-01-05','2027-01-06','2027-01-07'],conflict_message:null};
const facts:HandoverContext={case_no:'CASE',assignment_id:31,staff_id:1,staff_name:'原月嫂',order_version:2,scheduling_version:3,service_dates:request.handover_dates,request:null};
function setup(value:HandoverContext=facts){
 window.location.hash=serviceHandoverHref('CASE',31);
 const query=vi.spyOn(serviceStartClient,'handoverContext').mockResolvedValue(value);
 vi.spyOn(serviceStartClient,'options').mockResolvedValue({items:[{staff_id:1,name:'原月嫂'},{staff_id:2,name:'接任月嫂'},{staff_id:3,name:'其他月嫂'}]});
 return query;
}
afterEach(()=>{sessionStorage.clear();vi.restoreAllMocks();});
it('原案件與指定原區段精確帶入；讀取不自動建待辦或寄送',async()=>{
 const query=setup();
 const inquire=vi.spyOn(serviceStartClient,'inquireHandover').mockResolvedValue(request);
 const command=vi.spyOn(serviceStartClient,'command');
 expect(parseServiceHandoverLink(window.location.hash)?.assignmentId).toBe(31);
 render(<ServiceHandoverPage/>);
 await screen.findByText(/原區段剩餘 3 個服務日/);
 expect(query).toHaveBeenCalledWith('CASE',31);expect(inquire).not.toHaveBeenCalled();expect(command).not.toHaveBeenCalled();
 expect(screen.queryByRole('option',{name:'原月嫂'})).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('接任月嫂'),{target:{value:'2'}});
 fireEvent.click(screen.getByRole('button',{name:'詢問該月嫂意願'}));
 await screen.findByText(/等待月嫂回覆/);
 expect(inquire).toHaveBeenCalledWith(expect.objectContaining({case_no:'CASE',assignment_id:31,staff_id:2,expected_order_version:2,expected_scheduling_version:3}));
 expect(screen.queryByLabelText('交接日')).not.toBeInTheDocument();
});
it('初次詢問結果未明，重整後沿原操作確認，不另建詢問',async()=>{
 setup();const inquire=vi.spyOn(serviceStartClient,'inquireHandover').mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(request);
 const view=render(<ServiceHandoverPage/>);
 fireEvent.change(await screen.findByLabelText('接任月嫂'),{target:{value:'2'}});fireEvent.click(screen.getByRole('button',{name:'詢問該月嫂意願'}));
 await screen.findByRole('button',{name:'確認原操作結果'});view.unmount();
 render(<ServiceHandoverPage/>);fireEvent.click(await screen.findByRole('button',{name:'確認原操作結果'}));
 await screen.findByText(/等待月嫂回覆/);expect(inquire.mock.calls[0]).toEqual(inquire.mock.calls[1]);
});
it('願意後只開放單人邀請，真正加入後才顯示交接日',async()=>{
 setup({...facts,request:{...request,willingness:'willing'}});
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...request,willingness:'willing',invitation_status:'pending',version:5});
 vi.spyOn(serviceStartClient,'detail').mockResolvedValue({...request,willingness:'willing',joined:true,version:5});
 render(<ServiceHandoverPage/>);fireEvent.click(await screen.findByRole('button',{name:'寄送本案群組邀請連結'}));
 await waitFor(()=>expect(command).toHaveBeenCalledWith(8,'invite',expect.objectContaining({expected_version:4})));
 expect(screen.queryByLabelText('交接日')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'重新查詢加入狀態'}));await screen.findByLabelText('交接日');
});
it('工會填交接日，顯示全部剩餘日，一次儲存且不新增確認步驟',async()=>{
 setup({...facts,request:{...request,willingness:'willing',joined:true}});
 const command=vi.spyOn(serviceStartClient,'command').mockResolvedValue({...request,status:'applied',result:{actual_start_date:'2026-12-20',actual_end_date:'2027-01-07',order_version:3,
 first_payment_due_date:'2026-12-20',group_record_queued:true,assignments:[{staff_id:2,staff_name:'接任月嫂',service_dates:['2027-01-06','2027-01-07']}]}});
 render(<ServiceHandoverPage/>);fireEvent.change(await screen.findByLabelText('交接日'),{target:{value:'2027-01-06'}});
 expect(screen.getByText('交接日起接任 2 個服務日：2027-01-06、2027-01-07')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByText('正式排班已完成');expect(command).toHaveBeenCalledTimes(1);
 expect(command).toHaveBeenCalledWith(8,'dates',expect.objectContaining({start_date:'2027-01-06',expected_version:4}));
 expect(screen.getByRole('status')).toHaveTextContent('日期表已交付寄送');
});
it('衝突保留原作業，可改交接日或改問其他月嫂；已無剩餘日不能儲存',async()=>{
 setup({...facts,request:{...request,willingness:'willing',joined:true,conflict_message:'接任月嫂的排程有衝突，原排班與帳務尚未變更'}});
 const command=vi.spyOn(serviceStartClient,'command').mockRejectedValue(new ApiHttpError(409,'conflict','原排班已更新，請重新查詢'));
 render(<ServiceHandoverPage/>);const date=await screen.findByLabelText('交接日');
 fireEvent.change(date,{target:{value:'2027-02-01'}});expect(screen.getByRole('button',{name:'儲存交接日並更新排班與帳務'})).toBeDisabled();
 fireEvent.change(date,{target:{value:'2027-01-06'}});fireEvent.click(screen.getByRole('button',{name:'儲存交接日並更新排班與帳務'}));
 await screen.findByRole('alert');expect(command).toHaveBeenCalledTimes(1);fireEvent.click(screen.getByRole('button',{name:'改問其他月嫂'}));
 expect(screen.getByLabelText('代班月嫂')).toBeInTheDocument();expect(screen.queryByLabelText('交接日')).not.toBeInTheDocument();
});
it('缺少案件來源不允許旁路換人流程',()=>{
 window.location.hash='';render(<ServiceHandoverPage/>);
 expect(screen.getByRole('alert')).toHaveTextContent('請從案件服務安排的服務中換人按鈕開啟');
});
