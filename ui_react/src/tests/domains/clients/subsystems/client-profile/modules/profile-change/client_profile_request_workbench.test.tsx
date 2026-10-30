import { cleanup,fireEvent,render,screen,waitFor } from '@testing-library/react';
import { afterEach,beforeEach,it,expect,vi } from 'vitest';
import { ClientRegistryPage } from '../../../../../../../pages/ClientRegistryPage';
import { RegistrationApplications } from '../../../../../../../components/RegistrationApplications';
import { registrationApplicationsClient } from '../../../../../../../api/registration_applications/client';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
const request={request_id:73,client_id:8,status:'pending',request_version:2,profile_version:4,before:{name:'原名'},requested:{name:'申請新名'},reason:''};
beforeEach(()=>vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session'));
afterEach(()=>{cleanup();vi.restoreAllMocks();window.history.replaceState(null,'','/');});
it('名冊深連結直接讀取不在第一頁的需求申請，開頁不核准',async()=>{
 window.location.hash='#clients?tab=applications&registration=73';
 vi.spyOn(registrationApplicationsClient,'pending').mockResolvedValue([]);
 const detail=vi.spyOn(registrationApplicationsClient,'detail').mockResolvedValue({registration_id:73,version:1,name:'測試需求',phone:'',approved:false,fields:[],registration_kind:'subsidy',case_no:null,approved_at_utc:null});
 const approve=vi.spyOn(registrationApplicationsClient,'approve');
 render(<ClientRegistryPage/>);await screen.findByRole('heading',{name:'申請 73：測試需求'});
 expect(screen.getByRole('tab',{name:'待核准需求'})).toHaveAttribute('aria-selected','true');
 expect(detail).toHaveBeenCalledWith(73);expect(approve).not.toHaveBeenCalled();
});
it('資料異動依指定申請單獨讀取，不受待審核清單分頁影響，核准仍走原 writer',async()=>{
 window.location.hash='#clients?tab=profile-requests&request=73';
 const get=vi.spyOn(transport,'get').mockImplementation(async path=>({data:String(path).endsWith('/73')?request:{items:[],total:30,page:1,page_size:25}}));
 const post=vi.spyOn(transport,'post').mockImplementation(async path=>({data:String(path).endsWith('/preview')?{preview_fingerprint:'a'.repeat(64),apply_ready:true}:{}}));
 render(<ClientRegistryPage/>);await screen.findByText('原名 → 申請新名');
 expect(get).toHaveBeenCalledWith('/api/v1/client-profile/requests/73',expect.anything());expect(post).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'核准資料異動'}));await screen.findByText('客戶資料已核准套用。');
 expect(post).toHaveBeenCalledWith('/api/v1/client-profile/requests/73/approve/apply',expect.objectContaining({expected_request_version:2,expected_profile_version:4}),expect.anything());
 await waitFor(()=>expect(get.mock.calls.filter(call=>call[0]==='/api/v1/client-profile/requests')).toHaveLength(2));
});
it('單筆回應不是指定申請時不提供審核操作',async()=>{
 window.location.hash='#clients?tab=profile-requests&request=73';
 vi.spyOn(transport,'get').mockImplementation(async path=>({data:String(path).endsWith('/73')?{...request,request_id:99}:{items:[],total:0,page:1,page_size:25}}));
 const post=vi.spyOn(transport,'post');render(<ClientRegistryPage/>);await screen.findByText('目前無法完成操作，請重新整理後再試。');
 expect(screen.queryByRole('button',{name:'核准資料異動'})).not.toBeInTheDocument();expect(post).not.toHaveBeenCalled();
});
it('需求申請切換後，晚到的舊申請不能覆寫目前事項',async()=>{
 vi.spyOn(registrationApplicationsClient,'pending').mockResolvedValue([]);
 const application={registration_id:73,version:1,name:'舊申請',phone:'',approved:false,fields:[],registration_kind:'subsidy' as const,case_no:null,approved_at_utc:null};
 let finish!:(value:typeof application)=>void;
 vi.spyOn(registrationApplicationsClient,'detail').mockImplementation(async id=>id===73?new Promise(resolve=>{finish=resolve;}):{...application,registration_id:74,name:'新申請'});
 const onEditStateChange=vi.fn();const view=render(<RegistrationApplications initialId={73} onEditStateChange={onEditStateChange}/>);
 await waitFor(()=>expect(registrationApplicationsClient.detail).toHaveBeenCalledWith(73));
 view.rerender(<RegistrationApplications initialId={74} onEditStateChange={onEditStateChange}/>);
 await screen.findByRole('heading',{name:'申請 74：新申請'});finish(application);
 await waitFor(()=>expect(screen.queryByRole('heading',{name:'申請 73：舊申請'})).not.toBeInTheDocument());
});
it('指定資料異動暫時讀取失敗，可重讀原申請而不選取其他資料',async()=>{
 window.location.hash='#clients?tab=profile-requests&request=73';let available=false;
 vi.spyOn(transport,'get').mockImplementation(async path=>{if(String(path).endsWith('/73')){if(!available)throw new Error('temporary');return {data:request};}return {data:{items:[],total:0,page:1,page_size:25}};});
 const post=vi.spyOn(transport,'post');render(<ClientRegistryPage/>);
 await screen.findByText('目前無法完成操作，請重新整理後再試。');available=true;
 fireEvent.click(screen.getByRole('button',{name:'重新讀取這筆申請'}));await screen.findByText('原名 → 申請新名');expect(post).not.toHaveBeenCalled();
});
