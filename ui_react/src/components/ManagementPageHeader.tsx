import type { ReactNode } from 'react';
import './ManagementPageHeader.css';

interface ManagementPageHeaderProps {
  title: ReactNode;
  description?: string;
  titleId?: string;
  className?: string;
  children?: ReactNode;
}

export function ManagementPageHeader({ title, description, titleId, className, children }: ManagementPageHeaderProps) {
  return (
    <header className={className ? `management-page-header ${className}` : 'management-page-header'}>
      <div className="management-page-header-copy">
        <h1 id={titleId}>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {children}
    </header>
  );
}
