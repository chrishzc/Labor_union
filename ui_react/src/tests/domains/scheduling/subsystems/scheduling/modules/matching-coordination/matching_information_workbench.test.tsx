import { cleanup,fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import { afterEach,beforeEach,it,expect,vi } from 'vitest';
import { MatchingInformationWorkbench } from '../../../../../../../components/MatchingInformationWorkbench';
import { sessionClient } from '../../../../../../../api/auth/session_client';
import { transport } from '../../../../../../../api/shared/transport';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
const info={question_id:73,pool_id:1,request_kind:'information_question',customer_answer_event_id:null,review_completed:false,
 case_no:'116000001',staff_name:'合成月嫂',issues:[{label:'服務地區',detail:'請問實際地區？'}],customer_answer:null,customer_message:null,customer_available:false};
beforeEach(()=>vi.spyOn(sessionClient,'getToken').mockReturnValue('synthetic-session'));
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it('指定問題獨立查詢，核對失敗保留草稿並停止發送',async()=>{
 let bound=false,failed=false;
 const get=vi.spyOn(transport,'get').mockImplementation(async path=>{
  if(String(path).endsWith('/query')){if(failed)throw new ApiHttpError(503,'unavailable','這筆需求暫時無法讀取。');return {data:{...info,customer_available:bound}};}
  return {data:{items:[{...info,question_id:2}],total:26,page:1,page_size:25}};
 });
 const post=vi.spyOn(transport,'post');render(<MatchingInformationWorkbench caseNo="116000001" questionId="73"/>);
 await screen.findByText('請問實際地區？');expect(get).toHaveBeenCalledWith(expect.stringContaining('/73/query'),expect.objectContaining({params:{case_no:'116000001'}}));
 const panel=screen.getByLabelText('月嫂確認與條件協調');
 fireEvent.change(within(panel).getByLabelText('發送文案'),{target:{value:'尚未發送的草稿'}});
 expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeDisabled();expect(within(panel).getByRole('button',{name:'發送給月嫂'})).toBeEnabled();
 expect(within(panel).getByRole('link',{name:'查看客戶綁定方式與狀態'})).toBeVisible();expect(post).not.toHaveBeenCalled();
 bound=true;fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));
 await waitFor(()=>expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeEnabled());
 expect(within(panel).getByLabelText('發送文案')).toHaveValue('尚未發送的草稿');
 failed=true;fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));
 await within(panel).findByText('目前無法核對這筆需求，暫時不能發送。請重新核對後再試。');
 expect(within(panel).getByRole('button',{name:'發送給月嫂'})).toBeDisabled();expect(within(panel).getByLabelText('發送文案')).toHaveValue('尚未發送的草稿');
 failed=false;fireEvent.click(within(panel).getByRole('button',{name:'重新核對'}));await waitFor(()=>expect(within(panel).getByRole('button',{name:'發送給客戶'})).toBeEnabled());expect(post).not.toHaveBeenCalled();
});
it.each([['不同案件',{case_no:'OTHER'}],['不同問題',{question_id:2}]])('%s 回應不能提供原問題的處理操作',async(_label,patch)=>{
 vi.spyOn(transport,'get').mockImplementation(async path=>({data:String(path).endsWith('/query')?{...info,...patch}:{items:[],total:0,page:1,page_size:25}}));
 const post=vi.spyOn(transport,'post');render(<MatchingInformationWorkbench caseNo="116000001" questionId="73"/>);
 await screen.findByRole('alert');expect(screen.queryByLabelText('發送文案')).not.toBeInTheDocument();expect(post).not.toHaveBeenCalled();
});
it('原問題已失效時保留原因，不改開同頁其他問題',async()=>{
 vi.spyOn(transport,'get').mockImplementation(async path=>{if(String(path).endsWith('/query'))throw new ApiHttpError(404,'unavailable','原問題已處理或更新。');return {data:{items:[{...info,question_id:2}],total:1,page:1,page_size:25}};});
 render(<MatchingInformationWorkbench caseNo="116000001" questionId="73"/>);await screen.findByText('原問題已處理或更新。');expect(screen.queryByLabelText('發送文案')).not.toBeInTheDocument();
});
