/** Authenticated Staff personal profile fixture. */
import type { StaffProfile } from '../../../api/staff_profile/staff_profile_schemas';

export const STAFF_PROFILE: StaffProfile = {
  staff_id: 11,
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
};
