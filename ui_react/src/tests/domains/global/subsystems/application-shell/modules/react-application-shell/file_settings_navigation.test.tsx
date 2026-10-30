import { describe, expect, it } from 'vitest';
import { NAV_ITEMS, PAGE_SECTION_MAP } from '../../../../../../../components/MasterLayout';

describe('Audit & System navigation retirement', () => {
  it('excludes storage-management and file-settings from navigation and section map (2026-10-30 decision)', () => {
    const rawIds = NAV_ITEMS.map(item => item.id as string);
    expect(rawIds).not.toContain('file-settings');
    expect(rawIds).not.toContain('storage-management');

    const rawSectionMap = PAGE_SECTION_MAP as Record<string, string>;
    expect(rawSectionMap['file-settings']).toBeUndefined();
    expect(rawSectionMap['storage-management']).toBeUndefined();

    // Audit section only contains account-management and contract-templates
    const auditItems = NAV_ITEMS.filter(item => item.section === 'audit');
    expect(auditItems.map(item => item.id)).toEqual(['account-management', 'contract-templates']);
  });
});
