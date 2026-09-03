import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ServiceBeforeReplacementActions } from '../components/ServiceBeforeReplacementActions';

describe('ServiceBeforeReplacementActions business entry', () => {
  it('keeps the technical replacement workbench hidden until the Orders business entry is opened', () => {
    render(
      <ServiceBeforeReplacementActions
        caseNo="CASE-RPRE-ENTRY"
        onCommitted={vi.fn()}
        onSubstitutionReferral={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: '服務前更換月嫂' })).toBeInTheDocument();
    expect(screen.queryByLabelText('異常情境')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('服務前換人人工修復')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '服務前更換月嫂' }));

    expect(screen.getByLabelText('異常情境')).toBeInTheDocument();
    expect(screen.getByLabelText('服務前換人人工修復')).toBeInTheDocument();
  });
});
