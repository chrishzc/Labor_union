/** Customer-service list, completion races, copy and bounded reader transport. */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LineCustomerServiceReminderWorkbench } from '../../../../../../components/LineCustomerServiceReminderWorkbench';
import { LineManagementPage } from '../../../../../../pages/LineManagementPage';
import { customerServiceClient } from '../../../../../../api/customer_service/customer_service_client';
import { sessionClient } from '../../../../../../api/auth/session_client';
import { transport } from '../../../../../../api/shared/transport';
import { CUSTOMER_SERVICE_REMINDER_PAGE_FIXTURE as page } from './fixtures/customer_service_reminder_fixtures';
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); window.history.replaceState(null, '', '/'); });
const detail = { ticket: { ticket_id:31,line_user_id:'U_SYNTHETIC',category:'other',status:'waiting',version:0,internal_note:'保留原有備註' },events:[] };
const empty = {...page,items:[],total:0,summary:{waiting:0,handling:0}};
function actionClient(){return {listReminders:vi.fn().mockResolvedValueOnce(page).mockResolvedValue(empty),getTicketDetail:vi.fn().mockResolvedValue(detail),previewUpdate:vi.fn().mockResolvedValue({preview_fingerprint:'a'.repeat(64)}),applyUpdate:vi.fn().mockResolvedValue({})};}
describe('客服案件六欄清單',()=>{
 it('通知待辦深連結帶入工單編號搜尋，開頁只讀客服清單',async()=>{
  window.location.hash='#line-management?tab=tickets&ticket_q=31';
  const client={listReminders:vi.fn().mockResolvedValue(page),getTicketDetail:vi.fn()};
  render(<LineManagementPage customerService={client}/>);await screen.findByText('測試客戶');
  expect(screen.getByRole('searchbox')).toHaveValue('31');
  expect(client.listReminders).toHaveBeenCalledWith(expect.objectContaining({search:'31',status:'open',page:1}),expect.any(Object));
  expect(client.getTicketDetail).not.toHaveBeenCalled();
 });
 it('開頁只有查詢，六欄與完成按鈕，不顯示狀態、來源篩選或抽屜',async()=>{
  const client={listReminders:vi.fn().mockResolvedValue(page),getTicketDetail:vi.fn()};
  render(<LineManagementPage customerService={client}/>);await screen.findByText('測試客戶');
  const workspace=screen.getByRole('region',{name:'客服案件提醒'});
  expect(within(workspace).getAllByRole('columnheader').map(x=>x.textContent)).toEqual(['客服對象','LINE 顯示名稱','進件來源','內容','申請時間','案件完成']);
  expect(within(workspace).queryByRole('combobox')).not.toBeInTheDocument();expect(within(workspace).queryByRole('button',{name:/待接手|處理中/})).not.toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();expect(client.getTicketDetail).not.toHaveBeenCalled();
  expect(screen.getByText('請協助確認服務安排。')).toBeInTheDocument();
  expect(client.listReminders).toHaveBeenCalledWith(expect.objectContaining({status:'open',page:1}),expect.any(Object));
 });
 it('複製真正 LINE 名稱；沒有名稱或留言不補造資料',async()=>{
  const writeText=vi.fn().mockResolvedValue(undefined);vi.stubGlobal('navigator',{...navigator,clipboard:{writeText}});
  render(<LineCustomerServiceReminderWorkbench client={{listReminders:vi.fn().mockResolvedValue({...page,items:[page.items[0],{...page.items[0],ticket_id:32,line_display_name:null,messages:[]}]})}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'複製工單 31 的 LINE 顯示名稱'}));
  await waitFor(()=>expect(writeText).toHaveBeenCalledWith('測試 LINE 名稱'));
  expect(screen.getByText('尚未取得')).toBeInTheDocument();expect(screen.getByText('尚未留言')).toBeInTheDocument();vi.unstubAllGlobals();
 });
 it('一次點擊完成，保留備註，正式回應後重查清單',async()=>{
  const client=actionClient();render(<LineCustomerServiceReminderWorkbench client={client}/>);
  fireEvent.click(await screen.findByRole('button',{name:'處理完成'}));await screen.findByText('目前沒有需要處理的客服案件');
  expect(client.previewUpdate).toHaveBeenCalledWith(31,{status:'resolved',internal_note:'保留原有備註',expected_version:0},expect.any(Object));
  expect(client.applyUpdate).toHaveBeenCalledExactlyOnceWith(31,expect.objectContaining({status:'resolved',preview_fingerprint:'a'.repeat(64)}),expect.objectContaining({idempotencyKey:expect.any(String)}));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
 });
 it('完成結果不明不移除，重按沿用同一 payload 和 key',async()=>{
  const client=actionClient();client.applyUpdate.mockRejectedValueOnce(new Error('timeout'));render(<LineCustomerServiceReminderWorkbench client={client}/>);
  fireEvent.click(await screen.findByRole('button',{name:'處理完成'}));await screen.findByRole('alert');expect(screen.getByText('測試客戶')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'確認完成結果'}));await screen.findByText('目前沒有需要處理的客服案件');
  expect(client.applyUpdate.mock.calls[0]).toEqual(client.applyUpdate.mock.calls[1]);expect(client.previewUpdate).toHaveBeenCalledTimes(1);
 });
 it('有新留言版本時先重查，不把新需求直接結案',async()=>{
  const client=actionClient();client.getTicketDetail.mockResolvedValue({...detail,ticket:{...detail.ticket,version:1}});client.listReminders.mockResolvedValue(page);
  render(<LineCustomerServiceReminderWorkbench client={client}/>);fireEvent.click(await screen.findByRole('button',{name:'處理完成'}));
  await screen.findByText('案件有新內容，請查看最新留言後再決定是否完成。');expect(client.applyUpdate).not.toHaveBeenCalled();expect(client.previewUpdate).not.toHaveBeenCalled();
 });
 it('搜尋交給 server；legacy 狀態與來源不成為隱藏篩選',async()=>{
  window.location.hash='#line-management?ticket_state=waiting&ticket_source=feedback';const listReminders=vi.fn().mockResolvedValue(page);
  render(<LineCustomerServiceReminderWorkbench client={{listReminders}}/>);await screen.findByText('測試客戶');
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'測試'}});
  await waitFor(()=>expect(listReminders).toHaveBeenLastCalledWith(expect.objectContaining({search:'測試',status:'open'}),expect.any(Object)));expect(window.location.hash).not.toContain('ticket_state');expect(window.location.hash).not.toContain('ticket_source');
 });
 it('真實分頁、取消與晚到回應不覆蓋新結果',async()=>{
  let finish!:(value:typeof page)=>void;const listReminders=vi.fn().mockReturnValueOnce(new Promise(resolve=>{finish=resolve;})).mockImplementation(async query=>({...page,page:query.page,total:26,items:[{...page.items[0],client_name:'新結果'}]}));
  render(<LineCustomerServiceReminderWorkbench client={{listReminders}}/>);await waitFor(()=>expect(listReminders).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByRole('searchbox'),{target:{value:'0031'}});await screen.findByText('新結果');finish(page);await waitFor(()=>expect(screen.queryByText('測試客戶')).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button',{name:'下一頁'}));await screen.findByText('第 2／2 頁');
 });
 it('查詢失敗不冒充零筆，重查可恢復',async()=>{
  render(<LineCustomerServiceReminderWorkbench client={{listReminders:vi.fn().mockRejectedValueOnce(new Error('private SQL')).mockResolvedValue(page)}}/>);
  await screen.findByRole('alert');expect(screen.queryByText('目前沒有需要處理的客服案件')).not.toBeInTheDocument();expect(screen.queryByText('private SQL')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'重新整理'}));await screen.findByText('測試客戶');
 });
});
describe('客服清單 typed client',()=>{
 it('唯讀 GET，拒絕 raw 身分與已結案資料',async()=>{
  vi.spyOn(sessionClient,'getToken').mockReturnValue('unit-test-session');const get=vi.spyOn(transport,'get').mockResolvedValue({success:true,message:'ok',error:null,data:page});
  expect(await customerServiceClient.listReminders()).toEqual(page);
  get.mockResolvedValue({success:true,message:'ok',error:null,data:{...page,items:[{...page.items[0],line_user_id:'forbidden'}]}});await expect(customerServiceClient.listReminders()).rejects.toThrow();
  get.mockResolvedValue({success:true,message:'ok',error:null,data:{...page,items:[{...page.items[0],status:'resolved'}]}});await expect(customerServiceClient.listReminders()).rejects.toThrow();
 });
});
