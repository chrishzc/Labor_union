/** Map an authenticated Staff profile into user-facing values. */
import type { StaffProfile } from '../../api/staff_profile/staff_profile_schemas';

export interface StaffProfileViewModel extends StaffProfile {
  registeredAtLabel: string;
  identityCardLabel: string;
  phoneLabel: string;
  telephoneLabel: string;
  emailLabel: string;
  birthdayLabel: string;
  addressLabel: string;
  educationLabel: string;
  emergencyContactLabel: string;
  adminNotesLabel: string;
}

const empty = (value: string | null): string => value ?? '尚未登錄';

export function adaptStaffProfile(profile: StaffProfile): StaffProfileViewModel {
  const telephone = profile.telephone
    ? `${profile.telephone}${profile.telephone_extension ? ` 分機 ${profile.telephone_extension}` : ''}`
    : '尚未登錄';
  const addressParts = [profile.zip_code, profile.city, profile.address].filter(
    (value): value is string => Boolean(value),
  );
  const emergency = profile.emergency_contact_name || profile.emergency_contact_phone
    ? [profile.emergency_contact_name, profile.emergency_contact_phone].filter(Boolean).join('／')
    : '尚未登錄';
  return {
    ...profile,
    registeredAtLabel: profile.registered_at ? profile.registered_at.slice(0, 10) : '尚未登錄',
    identityCardLabel: empty(profile.identity_card),
    phoneLabel: empty(profile.phone),
    telephoneLabel: telephone,
    emailLabel: empty(profile.email),
    birthdayLabel: empty(profile.birthday),
    addressLabel: addressParts.join(' ') || '尚未登錄',
    educationLabel: empty(profile.education),
    emergencyContactLabel: emergency,
    adminNotesLabel: empty(profile.admin_notes),
  };
}
