import { useCallback, useEffect, useState } from 'react';
import {
  staffWebError, staffWebProfileClient, webProfileCategoryLabels, type PublishedWebProfile,
} from '../api/staff/staff_web_profile_client';
import './StaffWebProfile.css';

type PhotoState = { kind: 'loading' } | { kind: 'ready'; url: string } | { kind: 'error' };

export function useStaffPhoto(load: (signal: AbortSignal) => Promise<Blob>): PhotoState {
  const [image, setImage] = useState<{ loader: typeof load; state: PhotoState } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let url: string | undefined;
    void load(controller.signal).then(blob => {
      if (controller.signal.aborted) return;
      url = URL.createObjectURL(blob);
      setImage({ loader: load, state: { kind: 'ready', url } });
    }).catch(() => {
      if (!controller.signal.aborted) setImage({ loader: load, state: { kind: 'error' } });
    });
    return () => {
      controller.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [load]);
  return image?.loader === load ? image.state : { kind: 'loading' };
}

function PublishedPhoto({ path, photo }: {
  path: string;
  photo: PublishedWebProfile['groups'][number]['images'][number];
}) {
  const load = useCallback((signal: AbortSignal) => staffWebProfileClient.publishedImage(path, photo, signal), [path, photo]);
  const image = useStaffPhoto(load);
  return <figure>
    {image.kind === 'ready' ? <img src={image.url} alt={photo.item_name} /> : <p className="staff-web-image-message" role="status">
      {image.kind === 'loading' ? '讀取圖片中…' : '無法載入圖片'}
    </p>}
  </figure>;
}

function PreviewPage({ path, headingLevel }: { path: string; headingLevel: 'h3' | 'h4' }) {
  const [profile, setProfile] = useState<PublishedWebProfile | null>(null);
  const [error, setError] = useState('');
  const [generation, setGeneration] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void staffWebProfileClient.publishedProfile(path, controller.signal).then(result => {
      if (!controller.signal.aborted) setProfile(result);
    }).catch(caught => {
      if (!controller.signal.aborted) setError(staffWebError(caught, '無法讀取月嫂個人網頁。'));
    });
    return () => controller.abort();
  }, [path, generation]);

  if (error) return <div role="alert"><p>{error}</p><button type="button" onClick={() => {
    setError('');
    setGeneration(value => value + 1);
  }}>重新讀取</button></div>;
  if (!profile) return <p role="status">正在讀取月嫂個人網頁…</p>;
  const Heading = headingLevel;
  const GroupHeading = headingLevel === 'h3' ? 'h4' : 'h5';
  return <article className="staff-web-preview" aria-label={profile.name}>
    <Heading>{profile.name}</Heading>
    {Object.entries(webProfileCategoryLabels).map(([category, label]) => {
      const group = profile.groups.find(item => item.category === category);
      return group?.images.length ? <section key={category} aria-label={label}>
        <GroupHeading>{label}</GroupHeading>
        <div className="staff-web-slider" role="group" aria-label={label} tabIndex={0}
          onPointerDown={event => event.stopPropagation()} onTouchStart={event => event.stopPropagation()}
          onKeyDown={event => {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') event.stopPropagation();
          }}>
          {group.images.map(photo => <PublishedPhoto
            key={`${photo.image_entry}:${photo.image_version}`} path={path} photo={photo} />)}
        </div>
      </section> : null;
    })}
  </article>;
}

export function StaffWebProfilePreview({ path, headingLevel = 'h3' }: { path: string; headingLevel?: 'h3' | 'h4' }) {
  return <PreviewPage key={path} path={path} headingLevel={headingLevel} />;
}
