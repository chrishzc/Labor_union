import { fireEvent,render,screen,waitFor,within } from '@testing-library/react';
import { describe,it,expect,vi } from 'vitest';
import { PaymentReceiptNoticeWorkbench } from '../../../../../../../components/PaymentReceiptNoticeWorkbench';
import type { PaymentReceiptClient,PaymentReceiptTodo } from '../../../../../../../api/line_order_groups/payment_receipt_notification_client';
import { ApiHttpError } from '../../../../../../../api/shared/typed_errors';
const todo:PaymentReceiptTodo={payment:{case_no:'DEMO-001',payment_stage:'deposit',settlement_identity:'a'.repeat(64),amount_ntd:12000,source_version:2,source_reference:'source'},can_send:true,unavailable_reason:null,delivery_status:null};
function client(item=todo):PaymentReceiptClient{return {list:vi.fn().mockResolvedValue({items:[item],total:1,page:1,page_size:25}),send:vi.fn().mockResolvedValue({task_id:1,status:'pending'})};}

describe('入帳通知由人員發送',()=>{
  it('收到帳款只跳提示，關閉後待辦保留，查詢與重新整理不送出',async()=>{
    const api=client();render(<PaymentReceiptNoticeWorkbench revision={0} expanded client={api}/>);
    const dialog=await screen.findByRole('dialog');expect(dialog).toHaveTextContent('DEMO-001');expect(api.send).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole('button',{name:'稍後處理，保留待辦'}));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'發送入帳通知'})).toBeEnabled();
    fireEvent.click(screen.getByRole('button',{name:'重新整理入帳待辦'}));
    await waitFor(()=>expect(api.list).toHaveBeenCalledTimes(2));
    expect(api.send).not.toHaveBeenCalled();expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('只有按下發送才建立工作，連點不重複送出，狀態不假稱送達',async()=>{
    const api=client();let finish!:(value:{task_id:number;status:string})=>void;
    vi.mocked(api.send).mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    render(<PaymentReceiptNoticeWorkbench revision={0} client={api}/>);
    const button=within(await screen.findByRole('dialog')).getByRole('button',{name:'發送入帳通知'});
    fireEvent.click(button);fireEvent.click(button);expect(api.send).toHaveBeenCalledExactlyOnceWith(todo);
    finish({task_id:1,status:'pending'});
    expect(await screen.findByRole('status')).toHaveTextContent('尚未證明送達');
  });
  it('核銷完成刷新後才跳出新入帳提示，沒有待辦不彈窗',async()=>{
    const api=client();vi.mocked(api.list).mockResolvedValueOnce({items:[],total:0,page:1,page_size:25});
    const view=render(<PaymentReceiptNoticeWorkbench revision={0} client={api}/>);
    await waitFor(()=>expect(screen.getByRole('button',{name:'入帳通知待辦（0）'})).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    view.rerender(<PaymentReceiptNoticeWorkbench revision={1} client={api}/>);
    expect(await screen.findByRole('dialog')).toHaveTextContent('帳款已入帳');expect(api.send).not.toHaveBeenCalled();
  });
  it('未綁定仍保留待辦，不能點發送',async()=>{
    const api=client({...todo,can_send:false,unavailable_reason:'客戶尚未綁定 LINE'});
    render(<PaymentReceiptNoticeWorkbench revision={0} client={api}/>);
    const dialog=await screen.findByRole('dialog');expect(within(dialog).getByRole('button',{name:'發送入帳通知'})).toBeDisabled();
    expect(dialog).toHaveTextContent('客戶尚未綁定 LINE');expect(api.send).not.toHaveBeenCalled();
  });
  it('帳款異動回傳衝突時重新查詢，不自動再送',async()=>{
    const api=client();vi.mocked(api.send).mockRejectedValue(new ApiHttpError(409,'stale','private detail'));
    render(<PaymentReceiptNoticeWorkbench revision={0} client={api}/>);
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button',{name:'發送入帳通知'}));
    await waitFor(()=>expect(api.list).toHaveBeenCalledTimes(2));expect(api.send).toHaveBeenCalledTimes(1);expect(document.body).not.toHaveTextContent('private detail');
  });
});
