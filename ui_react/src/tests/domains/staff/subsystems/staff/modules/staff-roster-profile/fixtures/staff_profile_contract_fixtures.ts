/** Authenticated Staff personal profile fixture. */
import type { StaffProfile } from '../../../../../../../../api/staff_profile/staff_profile_schemas';

export const STAFF_PROFILE: StaffProfile = {
  staff_id: 11,
  name: '王小美',
  profile_version: 2,
  bank_accounts_version: 3,
  registered_at: '2025-05-06T09:30:00',
  identity_card: 'A123456789',
  phone: '0912345678',
  telephone: '035551234',
  telephone_extension: '66',
  email: 'staff@example.test',
  birthday: '1980-01-02',
  city: '新竹市',
  zip_code: '300',
  address: '北區測試路 1 號',
  education: '大學',
  emergency_contact_name: '王家人',
  emergency_contact_phone: '0987654321',
  admin_notes: '僅供內部排班聯絡',
  bank_accounts: [
    { account_id: 3, bank_code: '812', branch_code: '0012', account_last4: '9012', is_primary: true, is_active: true },
    { account_id: 4, bank_code: '004', branch_code: '0001', account_last4: '1098', is_primary: false, is_active: false },
  ],
};
