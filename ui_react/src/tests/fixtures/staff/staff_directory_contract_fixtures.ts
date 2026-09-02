/**
 * File: staff_directory_contract_fixtures.ts
 * Description: 提供 Staff 摘要 cursor 契約的去敏正向頁面與嚴格負向 payload。
 */
import type {
  StaffDirectoryPage,
  StaffDirectoryResponse,
} from '../../../api/staff_directory/staff_directory_schemas';

export const STAFF_PAGE_ONE: StaffDirectoryPage = {
  items: [
    { id: 11, name: '去敏人員甲', phone: '09********', education: null },
    { id: 12, name: null, phone: null, education: null },
  ],
  next_cursor: 12,
};

export const STAFF_PAGE_TWO: StaffDirectoryPage = {
  items: [{ id: 13, name: '去敏人員乙', phone: null, education: null }],
  next_cursor: null,
};

export const STAFF_PAGE_WITH_EDUCATION: StaffDirectoryPage = {
  items: [
    { id: 11, name: '去敏人員甲', phone: '09********', education: '大學' },
    { id: 12, name: null, phone: null, education: null },
  ],
  next_cursor: 12,
};

export const STAFF_RESPONSE_ONE: StaffDirectoryResponse = {
  success: true,
  message: '成功取得服務人員摘要',
  data: STAFF_PAGE_ONE,
  error: null,
};

export const STAFF_EMPTY_RESPONSE: StaffDirectoryResponse = {
  success: true,
  message: '成功取得服務人員摘要',
  data: { items: [], next_cursor: null },
  error: null,
};

export const STAFF_RESPONSE_TWO: StaffDirectoryResponse = {
  success: true,
  message: '成功取得服務人員摘要',
  data: STAFF_PAGE_TWO,
  error: null,
};

export const STAFF_RESPONSE_EXTRA_FIELD = {
  ...STAFF_RESPONSE_ONE,
  leaked_master: true,
};

export const STAFF_RESPONSE_DUPLICATE_IDS = {
  ...STAFF_RESPONSE_ONE,
  data: {
    items: [STAFF_PAGE_ONE.items[0], STAFF_PAGE_ONE.items[0]],
    next_cursor: null,
  },
};
