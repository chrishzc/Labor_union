/** Synthetic Staff-owned option metadata shared by Staff UI flow tests. */
import type { StaffCasePreferenceOptions } from '../../../../../../../api/staff_case_preferences/staff_case_preferences_schemas';
export const STAFF_MANUAL_OPTIONS: StaffCasePreferenceOptions = {
  service_regions: ['東區', '北區', '香山區', '竹北市', '竹東鎮', '新埔鎮', '關西鎮', '湖口鄉', '新豐鄉', '芎林鄉', '橫山鄉', '北埔鄉', '寶山鄉', '峨眉鄉', '尖石鄉', '五峰鄉'],
  service_periods: ['4小時', '8小時', '24小時'],
  cooking_skills: ['葷食', '素食'],
  holiday_availability: ['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'],
  rest_schedule: ['週休一日', '週休二日', '連續服務'],
  baby_types: ['單胞胎', '雙胞胎'],
};
