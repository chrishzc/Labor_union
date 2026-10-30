import { useEffect, useState } from 'react';
import { Database, Save } from 'lucide-react';
import { databaseBackupClient as client, type DatabaseBackupStatus } from '../api/database_backup_client';
import { useUnsavedDraft } from '../components/UnsavedChanges';
import './DatabaseBackupPage.css';

const localDate = (value: string | null) => value ? new Date(value).toLocaleString('zh-TW') : '尚無成功備份';

export function DatabaseBackupPage() {
  const [status, setStatus] = useState<DatabaseBackupStatus | null>(null);
  const [time, setTime] = useState('18:00');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useUnsavedDraft('每日資料庫備份時間', { time }, { baseline: { time: status?.time ?? '18:00' }, enabled: !!status, busy });

  useEffect(() => {
    let active = true;
    client.read().then(data => { if (active) { setStatus(data); setTime(data.time); } })
      .catch(() => { if (active) setError('無法讀取備份狀態，請稍後重新開啟此頁。'); });
    return () => { active = false; };
  }, []);

  async function save() {
    if (!status || busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await client.save(time, status.version);
      setStatus(data); setTime(data.time); setNotice(`已設定每天 ${data.time} 自動備份。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '備份時間未儲存，請稍後重試。');
    } finally { setBusy(false); }
  }

  return <div className="database-backup-page">
    <header><Database size={28} aria-hidden="true" /><div><h1>資料庫備份</h1><p>每天保留一份資料，供需要時復原。</p></div></header>
    {error && <div className="backup-message backup-error" role="alert">{error}</div>}
    {notice && <div className="backup-message backup-success" role="status">{notice}</div>}
    {!status && !error && <p role="status">正在讀取備份狀態…</p>}
    {status && <>
      <section className="backup-card" aria-labelledby="backup-status-title">
        <h2 id="backup-status-title">備份狀態</h2>
        <dl><div><dt>每日自動備份</dt><dd>{status.enabled ? `每天 ${status.time}` : '尚未啟用'}</dd></div>
          <div><dt>最近成功備份</dt><dd>{localDate(status.last_backup)}</dd></div></dl>
        {status.last_result?.status === 'failed' && <p className="backup-error" role="alert">最近一次備份失敗，請通知維護人員。先前成功的備份仍保留。</p>}
      </section>
      <section className="backup-card" aria-labelledby="backup-schedule-title">
        <h2 id="backup-schedule-title">每日備份時間</h2>
        {!status.configured && <p className="backup-message">尚未完成正式電腦的 NAS 備份設定，請由維護人員設定一次後再啟用。</p>}
        <p>請選擇工會電腦通常還在開機、並已登入 Windows 的時間。電腦關機時無法備份，重新登入後會補執行。</p>
        <form onSubmit={event => { event.preventDefault(); void save(); }}>
          <label htmlFor="daily-backup-time">每天執行時間</label>
          <div className="backup-time-row"><input id="daily-backup-time" type="time" required value={time} disabled={busy || !status.configured} onChange={event => setTime(event.target.value)} />
            <button type="submit" disabled={busy || !status.configured || !time}><Save size={17} aria-hidden="true" />{busy ? '儲存中…' : status.enabled ? '儲存時間' : '啟用每日備份'}</button></div>
        </form>
      </section>
      <section className="backup-card"><h2>需要升級或復原時</h2><p>請先停止工會系統，使用電腦上的「資料庫安全升級」或「復原資料庫備份」腳本，依中文提示操作。這兩項操作需要人工確認。</p>
        <p>備份包含資料庫資料。照片、附件及登入驗證金鑰，請依正式電腦的備份安排一併保存。</p></section>
    </>}
  </div>;
}
