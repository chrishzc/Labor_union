/**
 * File: unsaved_changes.test.tsx
 * Description: 驗證未儲存變更守衛的差異呈現、繼續編輯、捨棄、儲存回讀與非同步載入不誤報。
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { StrictMode, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { Drawer } from '../../../../../../../components/Drawer';
import { ServiceBeforeReplacementActions } from '../../../../../../../components/ServiceBeforeReplacementActions';
import { UnsavedChangesProvider, useUnsavedDraft, useUnsavedNavigation } from '../../../../../../../components/UnsavedChanges';

function Editor({ fail = false, busy = false, directSave = true }: { fail?: boolean; busy?: boolean; directSave?: boolean }) {
  const [saved, setSaved] = useState('原本內容');
  const [draft, setDraft] = useState(saved);
  const [message, setMessage] = useState('');
  const [search, setSearch] = useState('');
  const [opened, setOpened] = useState(true);
  const { requestLeave } = useUnsavedNavigation();
  const save = async () => {
    if (fail) { setMessage('儲存失敗，輸入已保留'); return; }
    setSaved(draft);
  };
  const ref = useUnsavedDraft('測試編輯表單', { '行政註記': draft }, {
    baseline: { '行政註記': saved }, enabled: opened, busy,
    save: directSave ? save : undefined,
    discard: () => setDraft(saved),
  });
  return <><label>搜尋<input value={search} onChange={event => setSearch(event.target.value)} /></label>
    <button type="button" onClick={() => requestLeave(() => setOpened(false))}>切換頁面</button>
    <Drawer isOpen={opened} title="編輯資料" onClose={() => requestLeave(() => setOpened(false))} closeLabel="關閉編輯">
      <section ref={ref}><label>行政註記<input value={draft} onChange={event => setDraft(event.target.value)} /></label>
        <button type="button" onClick={() => void save()}>原表單儲存</button>{message && <p role="alert">{message}</p>}
      </section>
    </Drawer>{!opened && <p>已離開</p>}</>;
}

function mount(props: Parameters<typeof Editor>[0] = {}) {
  return render(<StrictMode><UnsavedChangesProvider><Editor {...props} /></UnsavedChangesProvider></StrictMode>);
}
const warning = () => screen.getByRole('dialog', { name: '尚有未儲存的變更' });
const change = () => fireEvent.change(screen.getByLabelText('行政註記'), { target: { value: '新的內容' } });

describe('未儲存變更離開防護', () => {
  it('沒有可呼叫的儲存流程時停用儲存離開，繼續編輯保留原輸入', () => {
    mount({ directSave: false }); change();
    fireEvent.click(screen.getByRole('button', { name: '關閉編輯' }));
    expect(within(warning()).getByRole('cell', { name: '原本內容' })).toBeInTheDocument();
    expect(within(warning()).getByRole('cell', { name: '新的內容' })).toBeInTheDocument();
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('行政註記')).toHaveValue('新的內容');
    fireEvent.click(screen.getByRole('button', { name: '關閉編輯' }));
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeDisabled();
    expect(warning()).toHaveTextContent('此處無法一次儲存這些變更');
    fireEvent.click(within(warning()).getByRole('button', { name: '繼續編輯' }));
    expect(screen.getByLabelText('行政註記')).toHaveFocus();
    expect(screen.queryByText('已離開')).not.toBeInTheDocument();
  });

  it('捨棄會執行原離開動作一次，巢狀關閉不重複詢問', () => {
    mount(); change(); fireEvent.click(screen.getByRole('button', { name: '關閉編輯' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '捨棄變更並離開' }));
    expect(screen.getByText('已離開')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '尚有未儲存的變更' })).not.toBeInTheDocument();
  });

  it('儲存成功後才完成原本要求的離開', async () => {
    mount(); change(); fireEvent.click(screen.getByRole('button', { name: '切換頁面' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    await screen.findByText('已離開');
    expect(screen.queryByRole('dialog', { name: '尚有未儲存的變更' })).not.toBeInTheDocument();
  });

  it('後端回應後仍等候 owner 回讀完成，期間不能離開或重複送出', async () => {
    let acknowledge!: () => void;
    let finishReadback!: () => void;
    const receipt = new Promise<void>(resolve => { acknowledge = resolve; });
    const readback = new Promise<void>(resolve => { finishReadback = resolve; });
    const leave = vi.fn();
    const save = vi.fn();
    function PendingEditor() {
      const [baseline, setBaseline] = useState('原值');
      const [busy, setBusy] = useState(false);
      const { requestLeave } = useUnsavedNavigation();
      useUnsavedDraft('等待後端與回讀', { '欄位': '新值' }, {
        baseline: { '欄位': baseline }, busy,
        save: async () => {
          save(); setBusy(true);
          await receipt;
          setBaseline('新值');
          void readback.then(() => setBusy(false));
        },
      });
      return <button onClick={() => requestLeave(leave)}>離開</button>;
    }
    render(<UnsavedChangesProvider><PendingEditor /></UnsavedChangesProvider>);
    fireEvent.click(screen.getByRole('button', { name: '離開' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    expect(leave).not.toHaveBeenCalled();
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeDisabled();
    await act(async () => { acknowledge(); await receipt; });
    expect(leave).not.toHaveBeenCalled();
    expect(within(warning()).getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    expect(warning()).toHaveTextContent('結果尚未確認');
    await act(async () => { finishReadback(); await readback; });
    await waitFor(() => expect(leave).toHaveBeenCalledOnce());
    expect(save).toHaveBeenCalledOnce();
  });

  it('儲存拋錯即使同時清除差異，也不得當作成功離開', async () => {
    const leave = vi.fn();
    function RejectedEditor() {
      const [value, setValue] = useState('新值');
      const { requestLeave } = useUnsavedNavigation();
      useUnsavedDraft('儲存失敗', { '欄位': value }, { baseline: { '欄位': '原值' },
        save: async () => { setValue('原值'); throw new Error('save rejected'); },
      });
      return <button onClick={() => requestLeave(leave)}>離開</button>;
    }
    render(<UnsavedChangesProvider><RejectedEditor /></UnsavedChangesProvider>);
    fireEvent.click(screen.getByRole('button', { name: '離開' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    expect(await within(warning()).findByRole('alert')).toHaveTextContent('尚未完成儲存');
    expect(leave).not.toHaveBeenCalled();
  });

  it('預覽使儲存能力改變時更新已開啟的提醒，不把舊回呼當作可儲存', () => {
    const save = vi.fn();
    function PreviewEditor({ ready }: { ready: boolean }) {
      const { requestLeave } = useUnsavedNavigation();
      useUnsavedDraft('需要預覽', { '欄位': '新值' }, { baseline: { '欄位': '原值' }, save: ready ? save : undefined });
      return <button onClick={() => requestLeave(vi.fn())}>離開</button>;
    }
    const view = (ready: boolean) => <UnsavedChangesProvider><PreviewEditor ready={ready} /></UnsavedChangesProvider>;
    const result = render(view(false));
    fireEvent.click(screen.getByRole('button', { name: '離開' }));
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeDisabled();
    result.rerender(view(true));
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeEnabled();
    result.rerender(view(false));
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeDisabled();
    expect(save).not.toHaveBeenCalled();
  });

  it('原儲存流程回報失敗時保留輸入，不能當作成功離開', async () => {
    mount({ fail: true }); change(); fireEvent.click(screen.getByRole('button', { name: '切換頁面' }));
    fireEvent.click(within(warning()).getByRole('button', { name: '儲存變更並離開' }));
    await waitFor(() => expect(within(warning()).getByRole('alert')).toHaveTextContent('尚有變更未儲存'));
    expect(screen.getByLabelText('行政註記')).toHaveValue('新的內容');
    expect(screen.queryByText('已離開')).not.toBeInTheDocument();
  });

  it('進行中的變更不允許捨棄或重複儲存', () => {
    mount({ busy: true }); change(); fireEvent.click(screen.getByRole('button', { name: '切換頁面' }));
    expect(within(warning()).getByRole('button', { name: '捨棄變更並離開' })).toBeDisabled();
    expect(within(warning()).getByRole('button', { name: '儲存變更並離開' })).toBeDisabled();
  });

  it('查詢條件、還原原值與已完成的正常儲存不會誤報', async () => {
    mount(); fireEvent.change(screen.getByLabelText('搜尋'), { target: { value: '搜尋文字' } });
    change(); fireEvent.change(screen.getByLabelText('行政註記'), { target: { value: '原本內容' } });
    const cleanUnload = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);
    change(); fireEvent.click(screen.getByRole('button', { name: '原表單儲存' }));
    fireEvent.click(screen.getByRole('button', { name: '切換頁面' }));
    await screen.findByText('已離開');
    expect(screen.queryByRole('dialog', { name: '尚有未儲存的變更' })).not.toBeInTheDocument();
  });

  it('重新整理／關閉分頁只在有未儲存變更時阻擋，卸載後解除', () => {
    const result = mount(); change();
    const dirtyUnload = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(dirtyUnload);
    expect(dirtyUnload.defaultPrevented).toBe(true);
    result.unmount();
    const afterUnmount = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(afterUnmount);
    expect(afterUnmount.defaultPrevented).toBe(false);
  });

  it('Escape 取消警告只返回原編輯，不關閉下層抽屜', () => {
    mount(); change(); fireEvent.click(screen.getByRole('button', { name: '關閉編輯' }));
    fireEvent(warning(), new Event('cancel', { cancelable: true }));
    expect(screen.getByRole('dialog', { name: '編輯資料' })).toBeInTheDocument();
    expect(screen.getByLabelText('行政註記')).toHaveValue('新的內容');
  });

  it('非同步載入與確認成功後建立新基準，後續修改仍會受到保護', () => {
    function LoadedEditor() {
      const [source, setSource] = useState<string | null>(null);
      const [text, setText] = useState('');
      const { requestLeave } = useUnsavedNavigation();
      useUnsavedDraft('非同步表單', { '資料': text }, { enabled: source !== null });
      return <><button onClick={() => { setSource('已載入'); setText('已載入'); }}>載入</button>
        <input aria-label="資料" value={text} onChange={event => setText(event.target.value)} />
        <button onClick={() => requestLeave(vi.fn())}>離頁</button></>;
    }
    render(<UnsavedChangesProvider><LoadedEditor /></UnsavedChangesProvider>);
    fireEvent.click(screen.getByRole('button', { name: '載入' }));
    fireEvent.click(screen.getByRole('button', { name: '離頁' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('資料'), { target: { value: '已修改' } });
    fireEvent.click(screen.getByRole('button', { name: '離頁' }));
    expect(within(warning()).getByRole('cell', { name: '已載入' })).toBeInTheDocument();
    expect(within(warning()).getByRole('cell', { name: '已修改' })).toBeInTheDocument();
  });

  it('服務前更換月嫂非同步帶入預設情境 R-04 時不誤報未儲存變更', () => {
    const leave = vi.fn();
    function ReplacementHost({ scenario }: { scenario?: 'R-04' }) {
      const { requestLeave } = useUnsavedNavigation();
      return <>
        <ServiceBeforeReplacementActions caseNo="TEST-CASE" initialScenario={scenario} hideScenarioPicker={scenario !== undefined} />
        <button type="button" onClick={() => requestLeave(leave)}>離開客戶抽屜</button>
      </>;
    }
    const result = render(<UnsavedChangesProvider><ReplacementHost /></UnsavedChangesProvider>);
    result.rerender(<UnsavedChangesProvider><ReplacementHost scenario="R-04" /></UnsavedChangesProvider>);
    fireEvent.click(screen.getByRole('button', { name: '離開客戶抽屜' }));
    expect(screen.queryByRole('dialog', { name: '尚有未儲存的變更' })).not.toBeInTheDocument();
    expect(leave).toHaveBeenCalledOnce();
  });
});
