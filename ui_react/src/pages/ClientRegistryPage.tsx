import React, { useCallback, useEffect, useRef, useState } from 'react';
import { LegacyVirtualAccountImport } from '../components/LegacyVirtualAccountImport';
import { ClientRosterPage } from './ClientRosterPage';
import type { RegistryEditState } from '../components/ClientRegistryDetailEditor';
import './ClientRegistryPage.css';

type RegistryTab = 'roster' | 'virtual-accounts';

export const ClientRegistryPage: React.FC = () => {
  const readLocation = () => {
    const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    return { caseNo: params.get('case') ?? '', field: params.get('field') ?? '' };
  };
  const [location, setLocation] = useState(readLocation);
  const [activeTab, setActiveTab] = useState<RegistryTab>('roster');
  const editState = useRef<RegistryEditState>({ dirty: false, busy: false });
  const currentHash = useRef(window.location.hash);
  const onEditStateChange = useCallback((state: RegistryEditState) => { editState.current = state; }, []);
  const allowLeave = () => !editState.current.busy && (!editState.current.dirty || window.confirm('有尚未儲存的變更，確定放棄並切換？'));
  const selectTab = (tab: RegistryTab) => {
    if (tab === activeTab || !allowLeave()) return;
    editState.current = { dirty: false, busy: false };
    setActiveTab(tab);
  };
  useEffect(() => {
    const navigate = () => {
      if (!allowLeave()) { window.history.replaceState(null, '', currentHash.current); return; }
      currentHash.current = window.location.hash;
      const next = readLocation();
      setLocation(next);
      if (next.caseNo) setActiveTab('roster');
    };
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);

  return <div className="client-registry-hub">
    <header className="client-registry-hub__header">
      <div><h1>客戶名冊</h1><p>點選客戶清單中的案件，即可查看與編輯客戶、報名、照護及訂單條件。</p></div>
    </header>
    <div className="client-registry-tabs" role="tablist" aria-label="客戶名冊檢視">
      <button type="button" role="tab" aria-selected={activeTab === 'roster'} onClick={() => selectTab('roster')}>客戶清單</button>
      <button type="button" role="tab" aria-selected={activeTab === 'virtual-accounts'} onClick={() => selectTab('virtual-accounts')}>虛擬帳號匯入</button>
    </div>
    <section role="tabpanel" aria-label={activeTab === 'roster' ? '客戶清單' : '虛擬帳號匯入'}>
      {activeTab === 'roster' ? <ClientRosterPage embedded initialCaseNo={location.caseNo} focusField={location.field} onEditStateChange={onEditStateChange} /> : <LegacyVirtualAccountImport />}
    </section>
  </div>;
};

export default ClientRegistryPage;
