/** Synthetic Staff-owned option metadata shared by Staff UI flow tests. */
import type { StaffCasePreferenceOptions } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
export const STAFF_MANUAL_OPTIONS: StaffCasePreferenceOptions = {
  service_regions: ['台北市', '北區', '東區', '新竹縣'],
  service_periods: ['4小時', '8小時', '24小時'],
  cooking_skills: ['葷食', '素食'],
  holiday_availability: ['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'],
  rest_schedule: ['連續服務', '週休1日', '週休2日', '週一至週五', '休周六', '休周日'],
  baby_types: ['單胞胎', '雙胞胎'],
};
