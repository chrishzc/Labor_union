import { useCallback, useRef, useState, type PointerEvent } from 'react';
import { staffWebProfileClient, type CropBox, type PendingWebPhoto } from '../api/staff/staff_web_profile_client';
import { useStaffPhoto } from './StaffWebProfilePreview';
import './StaffWebProfile.css';

type Point = { x: number; y: number };
type Size = { width: number; height: number };
const edges = [
  { field: 'left', label: '左側' }, { field: 'top', label: '上方' },
  { field: 'right', label: '右側' }, { field: 'bottom', label: '下方' },
] as const;

export function StaffWebPhotoReview({ requestId, index, photo, title, editable, locked, changeCrop }: {
  requestId: number;
  index: number;
  photo: PendingWebPhoto;
  title: string;
  editable: boolean;
  locked: boolean;
  changeCrop: (box: CropBox | null) => Promise<boolean>;
}) {
  const [mode, setMode] = useState<'current' | 'original' | 'crop'>('current');
  const [size, setSize] = useState<Size | null>(null);
  const [box, setBox] = useState<CropBox | null>(null);
  const start = useRef<Point | null>(null);
  const original = mode !== 'current' || photo.crop_file_id === null;
  const load = useCallback((signal: AbortSignal) => staffWebProfileClient.reviewImage(requestId, index, original, signal),
    [requestId, index, original, photo.crop_file_id]);
  const image = useStaffPhoto(load);
  const selecting = mode === 'crop' && !locked;
  const validBox = box && size && box.left >= 0 && box.left < box.right && box.right <= size.width
    && box.top >= 0 && box.top < box.bottom && box.bottom <= size.height ? box : null;

  function setImageSize(width: number, height: number) {
    setSize({ width, height });
    setBox({ left: 0, top: 0, right: width, bottom: height });
  }

  function point(event: PointerEvent<HTMLDivElement>): Point | null {
    if (!size) return null;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return {
      x: Math.round(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * size.width),
      y: Math.round(Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) * size.height),
    };
  }

  function drawBox(event: PointerEvent<HTMLDivElement>) {
    const from = start.current;
    const to = point(event);
    if (!from || !to) return;
    setBox({
      left: Math.min(from.x, to.x), top: Math.min(from.y, to.y),
      right: Math.max(from.x, to.x), bottom: Math.max(from.y, to.y),
    });
  }

  return <section className="staff-web-review-photo" aria-label={title}>
    <h4>{title}</h4>
    {photo.expiry_date && <p>到期日 {photo.expiry_date}</p>}
    <div className="staff-op-actions">
      {photo.crop_file_id && mode !== 'crop' && <button type="button" className="staff-secondary-btn" disabled={locked}
        onClick={() => setMode(original ? 'current' : 'original')}>{original ? '查看裁切結果' : '查看原圖'}</button>}
      {editable && mode !== 'crop' && <button type="button" className="staff-secondary-btn" disabled={locked}
        onClick={() => { setSize(null); setBox(null); setMode('crop'); }}>裁切照片</button>}
      {editable && mode !== 'crop' && photo.crop_file_id && <button type="button" className="staff-secondary-btn" disabled={locked}
        onClick={() => void changeCrop(null).then(done => { if (done) setMode('current'); })}>移除已套用裁切</button>}
    </div>
    {image.kind === 'loading' && <p role="status">正在讀取照片…</p>}
    {image.kind === 'error' && <p role="alert">無法讀取照片，請重新讀取申請。</p>}
    {image.kind === 'ready' && <div className="staff-web-crop-image" data-selecting={selecting}
      onPointerDown={event => {
        if (!selecting || event.button !== 0) return;
        start.current = point(event);
        if (start.current) event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => { if (selecting) drawBox(event); }}
      onPointerUp={event => {
        if (selecting) drawBox(event);
        start.current = null;
      }}
      onPointerCancel={() => { start.current = null; }}>
      <img key={`${image.url}:${mode === 'crop'}`} src={image.url} draggable={false} alt={`${title} ${original ? '原圖' : '裁切結果'}`}
        onLoad={event => {
          if (mode === 'crop') setImageSize(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight);
        }} />
      {mode === 'crop' && validBox && size && <div className="staff-web-crop-overlay" aria-hidden="true" style={{
        left: `${validBox.left / size.width * 100}%`, top: `${validBox.top / size.height * 100}%`,
        width: `${(validBox.right - validBox.left) / size.width * 100}%`,
        height: `${(validBox.bottom - validBox.top) / size.height * 100}%`,
      }} />}
    </div>}
    {mode === 'crop' && <>
      {box && size && <fieldset className="staff-web-crop-fields" disabled={locked}>
        <legend>裁切邊界（像素）</legend>
        {edges.map(({ field, label }) => <label key={field}>{label}<input
          type="number" min={0} max={field === 'left' || field === 'right' ? size.width : size.height}
          value={box[field]} onChange={event => {
            const value = event.target.valueAsNumber;
            if (Number.isInteger(value)) setBox(current => current ? { ...current, [field]: value } : current);
          }} /></label>)}
      </fieldset>}
      <div className="staff-op-actions">
        <button type="button" className="staff-primary-btn" disabled={locked || !validBox}
          onClick={() => { if (validBox) void changeCrop(validBox).then(done => { if (done) setMode('current'); }); }}>套用裁切</button>
        <button type="button" className="staff-secondary-btn" disabled={locked} onClick={() => setMode('current')}>取消裁切</button>
      </div>
    </>}
  </section>;
}
