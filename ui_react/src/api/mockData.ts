/**
 * @file mockData.ts
 * @description 定義前端視覺基線之型別化 Mock 資料集，維持業務頁面於記憶體中隔離展示。
 */

export type WorkflowStage = 
  | 'intake_terms'          // 1. 進件與需求確認
  | 'matching_willingness'  // 2. 媒合月嫂與詢問意願
  | 'client_review'         // 3. 寄送履歷與客戶確認
  | 'contract_deposit'      // 4. 雙邊簽約與定金核銷
  | 'date_confirmation'     // 5. 確認實際服務日期 (精算日程雙方確認)
  | 'active_service'        // 6. 正式服務中
  | 'settlement_payout';    // 7. 完工結案與款項結算

export interface CandidatePoolItem {
  staffId: string;
  staffName: string;
  staffPhone: string;
  experienceYears: number;
  location: string;
  skills: string[];
  matchScore: number;
  goodConductValid: boolean;
  medicalExamValid: boolean;
  serviceRange: string;
  info1Sent: boolean;
  info1SentAt?: string;
  info2Sent: boolean;
  info2SentAt?: string;
  willingness: 'pending' | 'willing' | 'unwilling';
  willingnessReason?: string;
  selectedForResume: boolean;
}

export interface MatchingPlanState {
  planId: string;
  status: 'draft' | 'communicating' | 'all_willing' | 'resumes_sent' | 'customer_accepted' | 'locked' | 'cancelled';
  candidatePool: CandidatePoolItem[];
  resumeNote?: string;
  resumesSentAt?: string;
  customerDecision: 'pending' | 'accepted' | 'contact_requested' | 'declined';
  customerDecisionReason?: string;
  waitingLockAcquired: boolean;
}

export interface ServiceDateConfirmationState {
  actualStartDate: string;
  calculatedEndDate: string;
  calculatedServiceDays: number;
  restDaysSummary: string;
  bufferDateRange: string;
  scheduleSentAt?: string;
  customerConfirmed: boolean;
  customerConfirmedAt?: string;
  staffConfirmed: boolean;
  staffConfirmedAt?: string;
  gatePassed: boolean;
}

export interface WorkflowStepItem {
  stepNo: number;
  name: string;
  status: 'completed' | 'in_progress' | 'pending';
  timestamp?: string;
  notes?: string;
}

export interface OrderItem {
  id: string;
  clientName: string;
  clientPhone: string;
  serviceRange: string;
  serviceDays: number;
  serviceAddress: string;
  contractAmount: number;
  depositAmount: number;
  depositSettled: boolean;
  stage: WorkflowStage;
  currentStepDesc: string;
  waitingFor: string;
  actualStartDate?: string;
  
  // Strict Order Terms according to 01_Orders_Domain.md
  serviceTimeTuple: {
    startTime: string;        // e.g. "08:30"
    endTime: string;          // e.g. "17:30"
    dayOffset: 0 | 1;         // 0: same day, 1: next day
    dailyHours: number;       // e.g. 9 hours
  };
  requiresCooking: boolean | null;
  floorFee: number;

  // Contract Completion Evidence
  staffContractSigned: boolean;
  clientContractSigned: boolean;

  assignedDoula?: {
    id: string;
    name: string;
    phone: string;
    matchScore: number;
  };
  missingFields: string[];
  matchingPlan?: MatchingPlanState;
  dateConfirmation?: ServiceDateConfirmationState;
  stepsChecklist: WorkflowStepItem[];
}

export interface StaffItem {
  id: string;
  name: string;
  phone: string;
  experienceYears: number;
  location: string;
  skills: string[];
  goodConductValid: boolean;
  medicalExamValid: boolean;
  activeStatus: '在職' | '請假中' | '暫停接案';
  questionnaireScore: number;
  specialNotes?: string; // 📝 偏好備註 (例如: 不接需要料理的訂單、不接雙胞胎等)
}

export interface AnomalyItem {
  id: string;
  domain: '財務對帳' | '匯入資料' | '排班契約' | '系統整合';
  subType: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  description: string;
  relatedEntity: string;
  resolved: boolean;
}

export interface FinanceTransaction {
  id: string;
  type: '客戶退款' | '月嫂請款' | '政府補助';
  recipient: string;
  bankAccount: string;
  amount: number;
  status: '待審核' | '已核算' | '已撥款';
  createdAt: string;
}

export interface UserAccount {
  id: string;
  username: string;
  name: string;
  role: '超級管理員' | '工會行政' | '會計財務' | '系統稽核';
  totpEnabled: boolean;
  status: '啟用' | '停用';
  lastLogin: string;
}

export const MOCK_STAFF: StaffItem[] = [
  {
    id: 'STF-001',
    name: '王美惠 阿姨',
    phone: '0918-999-888',
    experienceYears: 8,
    location: '台北市大安區、新北市板橋區',
    skills: ['保母專業證照', '雙胞胎照護', '坐月子膳食調配', 'CPR合格證'],
    goodConductValid: true,
    medicalExamValid: true,
    activeStatus: '在職',
    questionnaireScore: 98,
    specialNotes: '優先承接大安與信義區，具備金牌藥膳證照，擅長雙胞胎照護。'
  },
  {
    id: 'STF-002',
    name: '張秀梅 阿姨',
    phone: '0928-777-666',
    experienceYears: 6,
    location: '新北市板橋區、中和區',
    skills: ['保母專業證照', '月子餐料理', '新生兒急救'],
    goodConductValid: true,
    medicalExamValid: true,
    activeStatus: '在職',
    questionnaireScore: 95,
    specialNotes: '❌ 不接需要繁複大菜料理的訂單；偏好 8~9 小時日間純照護案件。'
  },
  {
    id: 'STF-003',
    name: '李淑貞 阿姨',
    phone: '0937-666-555',
    experienceYears: 4,
    location: '台北市內湖區、南港區',
    skills: ['保母專業證照', '泌乳指導'],
    goodConductValid: false,
    medicalExamValid: true,
    activeStatus: '請假中',
    questionnaireScore: 91,
    specialNotes: '⚠️ 目前服喪請假中至 8/22，且良民證需催補影本。'
  },
  {
    id: 'STF-004',
    name: '陳金枝 阿姨',
    phone: '0956-333-222',
    experienceYears: 12,
    location: '台北/新北全區',
    skills: ['金牌月嫂認證', '藥膳月子餐', '產婦產後復原指導', '早產兒護理'],
    goodConductValid: true,
    medicalExamValid: true,
    activeStatus: '在職',
    questionnaireScore: 100,
    specialNotes: '資深特級金牌月嫂，可承接 24 小時全日住家、雙胞胎與早產兒特護。'
  }
];

export const MOCK_ORDERS: OrderItem[] = [
  {
    id: 'ORD-2026-0801',
    clientName: '林佩萱 小姐',
    clientPhone: '0912-345-678',
    serviceRange: '2026/09/01 ~ 2026/09/30',
    serviceDays: 30,
    serviceAddress: '台北市大安區新生南路二段',
    contractAmount: 78000,
    depositAmount: 15000,
    depositSettled: false,
    stage: 'intake_terms',
    currentStepDesc: '步驟 1/11: 客戶報名資料缺失補件中',
    waitingFor: '等待客戶回覆緊急聯絡電話與每日服務時段',
    serviceTimeTuple: {
      startTime: '',
      endTime: '',
      dayOffset: 0,
      dailyHours: 0
    },
    requiresCooking: null,
    floorFee: 0,
    staffContractSigned: false,
    clientContractSigned: false,
    missingFields: ['缺少緊急聯絡人電話', '每日服務時段三欄未確認'],
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'in_progress', notes: '⚠️ 缺少緊急電話，阻擋後續媒合' },
      { stepNo: 2, name: '媒合月嫂候選人', status: 'pending' },
      { stepNo: 3, name: '發送訂單資訊詢問月嫂意願 (LINE)', status: 'pending' },
      { stepNo: 4, name: '月嫂回傳接案意願', status: 'pending' },
      { stepNo: 5, name: '寄送月嫂履歷給客戶確認', status: 'pending' },
      { stepNo: 6, name: '產生並寄送月嫂服務契約 (月嫂簽回)', status: 'pending' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'pending' },
      { stepNo: 8, name: '產生並寄送客戶契約 (客戶簽回)', status: 'pending' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'pending' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'pending' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0802',
    clientName: '陳詩涵 小姐',
    clientPhone: '0922-555-789',
    serviceRange: '2026/08/25 ~ 2026/09/23',
    serviceDays: 30,
    serviceAddress: '新北市板橋區文化路一段',
    contractAmount: 82000,
    depositAmount: 18000,
    depositSettled: false,
    stage: 'matching_willingness',
    currentStepDesc: '步驟 3/11: 意願池已推播詢問，等待月嫂回傳意願中',
    waitingFor: '意願池有 2 位候選人：王美惠(待回覆)、張秀梅(願意)，待勾選推薦人選',
    serviceTimeTuple: {
      startTime: '09:00',
      endTime: '18:00',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: true,
    floorFee: 2000,
    staffContractSigned: false,
    clientContractSigned: false,
    missingFields: [],
    assignedDoula: {
      id: 'STF-001',
      name: '王美惠 阿姨',
      phone: '0918-999-888',
      matchScore: 98
    },
    matchingPlan: {
      planId: 'PLAN-8802',
      status: 'communicating',
      candidatePool: [
        {
          staffId: 'STF-001',
          staffName: '王美惠 阿姨',
          staffPhone: '0918-999-888',
          experienceYears: 8,
          location: '台北市大安區、新北市板橋區',
          skills: ['保母專業證照', '雙胞胎照護', '坐月子膳食調配'],
          matchScore: 98,
          goodConductValid: true,
          medicalExamValid: true,
          serviceRange: '8/25 ~ 9/23 (30天)',
          info1Sent: true,
          info1SentAt: '2026-08-14 11:35',
          info2Sent: false,
          willingness: 'pending',
          selectedForResume: false
        },
        {
          staffId: 'STF-002',
          staffName: '張秀梅 阿姨',
          staffPhone: '0928-777-666',
          experienceYears: 6,
          location: '新北市板橋區、中和區',
          skills: ['保母專業證照', '月子餐料理', '新生兒急救'],
          matchScore: 95,
          goodConductValid: true,
          medicalExamValid: true,
          serviceRange: '8/25 ~ 9/23 (30天)',
          info1Sent: true,
          info1SentAt: '2026-08-14 11:40',
          info2Sent: true,
          info2SentAt: '2026-08-14 12:00',
          willingness: 'willing',
          selectedForResume: true
        }
      ],
      resumeNote: '張阿姨具備 6 年專業月嫂年資與新生兒急救合格證，擅長藥膳料理，溝通親切。',
      customerDecision: 'pending',
      waitingLockAcquired: false
    },
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed', timestamp: '2026/08/14 10:00' },
      { stepNo: 2, name: '媒合月嫂加入意願池 (王美惠、張秀梅)', status: 'completed', timestamp: '2026/08/14 11:30' },
      { stepNo: 3, name: '發送訂單資訊-1 詢問意願', status: 'completed', timestamp: '2026/08/14 11:35' },
      { stepNo: 4, name: '月嫂回傳接案意願 (張秀梅已同意)', status: 'in_progress', notes: '張阿姨已同意，王阿姨待回覆' },
      { stepNo: 5, name: '勾選並寄送月嫂履歷給客戶確認', status: 'pending' },
      { stepNo: 6, name: '產生並寄送月嫂服務契約 (月嫂簽回)', status: 'pending' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'pending' },
      { stepNo: 8, name: '產生並寄送客戶契約 (客戶簽回)', status: 'pending' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'pending' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'pending' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0805',
    clientName: '黃雅玲 小姐',
    clientPhone: '0966-777-888',
    serviceRange: '2026/08/28 ~ 2026/09/26',
    serviceDays: 30,
    serviceAddress: '台北市松山區民生東路',
    contractAmount: 85000,
    depositAmount: 18000,
    depositSettled: false,
    stage: 'client_review',
    currentStepDesc: '步驟 5/11: 已從意願池勾選月嫂履歷並寄送給客戶確認',
    waitingFor: '等待客戶「黃雅玲 小姐」於 LINE 確認是否接受「張秀梅 阿姨」之履歷',
    serviceTimeTuple: {
      startTime: '08:30',
      endTime: '17:30',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: true,
    floorFee: 0,
    staffContractSigned: false,
    clientContractSigned: false,
    missingFields: [],
    assignedDoula: {
      id: 'STF-002',
      name: '張秀梅 阿姨',
      phone: '0928-777-666',
      matchScore: 95
    },
    matchingPlan: {
      planId: 'PLAN-8805',
      status: 'resumes_sent',
      candidatePool: [
        {
          staffId: 'STF-002',
          staffName: '張秀梅 阿姨',
          staffPhone: '0928-777-666',
          experienceYears: 6,
          location: '新北市板橋區、中和區',
          skills: ['保母專業證照', '月子餐料理', '新生兒急救'],
          matchScore: 95,
          goodConductValid: true,
          medicalExamValid: true,
          serviceRange: '8/28 ~ 9/26 (30天)',
          info1Sent: true,
          info1SentAt: '2026-08-14 13:30',
          info2Sent: true,
          info2SentAt: '2026-08-14 13:50',
          willingness: 'willing',
          selectedForResume: true
        }
      ],
      resumeNote: '張阿姨具備保母證照與新生兒急救合格證，擅長藥膳月子餐。',
      resumesSentAt: '2026-08-14 14:15',
      customerDecision: 'pending',
      waitingLockAcquired: false
    },
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed' },
      { stepNo: 2, name: '媒合月嫂候選人 (張秀梅)', status: 'completed' },
      { stepNo: 3, name: '發送訂單資訊-1 & 資訊-2', status: 'completed' },
      { stepNo: 4, name: '月嫂回傳接案意願 (願意接案)', status: 'completed', timestamp: '2026/08/14 14:00' },
      { stepNo: 5, name: '寄送月嫂履歷給客戶確認', status: 'in_progress', notes: '📨 已發送至客戶 LINE，等待客戶確認' },
      { stepNo: 6, name: '產生並寄送月嫂服務契約 (月嫂簽回)', status: 'pending' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'pending' },
      { stepNo: 8, name: '產生並寄送客戶契約 (客戶簽回)', status: 'pending' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'pending' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'pending' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0806',
    clientName: '何美玲 小姐',
    clientPhone: '0977-888-999',
    serviceRange: '2026/08/20 ~ 2026/09/19',
    serviceDays: 30,
    serviceAddress: '台北市中山區南京東路',
    contractAmount: 88000,
    depositAmount: 20000,
    depositSettled: true,
    stage: 'contract_deposit',
    currentStepDesc: '步驟 7/11: 定金已核銷，雙邊契約已簽回',
    waitingFor: '已簽約核銷定金，待產婦生產填寫 actual_start_date',
    serviceTimeTuple: {
      startTime: '09:00',
      endTime: '18:00',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: true,
    floorFee: 3000,
    staffContractSigned: true,
    clientContractSigned: true,
    missingFields: [],
    assignedDoula: {
      id: 'STF-004',
      name: '陳金枝 阿姨',
      phone: '0956-333-222',
      matchScore: 100
    },
    matchingPlan: {
      planId: 'PLAN-8806',
      status: 'locked',
      candidatePool: [
        {
          staffId: 'STF-004',
          staffName: '陳金枝 阿姨',
          staffPhone: '0956-333-222',
          experienceYears: 12,
          location: '台北/新北全區',
          skills: ['金牌月嫂認證', '藥膳月子餐'],
          matchScore: 100,
          goodConductValid: true,
          medicalExamValid: true,
          serviceRange: '8/20 ~ 9/19 (30天)',
          info1Sent: true,
          info2Sent: true,
          willingness: 'willing',
          selectedForResume: true
        }
      ],
      customerDecision: 'accepted',
      waitingLockAcquired: true
    },
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed' },
      { stepNo: 2, name: '媒合月嫂候選人 (陳金枝)', status: 'completed' },
      { stepNo: 3, name: '發送訂單資訊詢問月嫂意願', status: 'completed' },
      { stepNo: 4, name: '月嫂回傳願意接案', status: 'completed' },
      { stepNo: 5, name: '寄送月嫂履歷給客戶確認 (已確認)', status: 'completed' },
      { stepNo: 6, name: '月嫂服務契約寄送與簽回 (已簽回)', status: 'completed', timestamp: '2026/08/14 16:30' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'completed', notes: '✅ 定金 $20,000 已核銷' },
      { stepNo: 8, name: '客戶服務契約寄送與簽回 (已簽回)', status: 'completed', notes: '✅ 雙邊已完成簽署' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'in_progress', notes: '📝 待產婦生產填寫實際開始日並雙方確認' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'pending' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0807',
    clientName: '徐曉雯 小姐',
    clientPhone: '0988-123-456',
    serviceRange: '2026/08/18 ~ 2026/09/16',
    serviceDays: 30,
    serviceAddress: '台北市內湖區成功路三段',
    contractAmount: 86000,
    depositAmount: 18000,
    depositSettled: true,
    stage: 'date_confirmation',
    actualStartDate: '2026-08-18',
    currentStepDesc: '步驟 9/11: 已產出精算日程表，等待客戶與月嫂雙邊確認無異議',
    waitingFor: '已推播精算日程表，等待客戶(徐曉雯)與月嫂(陳金枝)於 LINE 點擊確認',
    serviceTimeTuple: {
      startTime: '09:00',
      endTime: '18:00',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: true,
    floorFee: 0,
    staffContractSigned: true,
    clientContractSigned: true,
    assignedDoula: {
      id: 'STF-004',
      name: '陳金枝 阿姨',
      phone: '0956-333-222',
      matchScore: 100
    },
    dateConfirmation: {
      actualStartDate: '2026-08-18',
      calculatedEndDate: '2026-09-21',
      calculatedServiceDays: 30,
      restDaysSummary: '4天週日休 + 1天客戶回娘家請假 (共5天排休)',
      bufferDateRange: '2026/09/22 ~ 2026/09/28 (7天)',
      scheduleSentAt: '2026-08-15 08:30',
      customerConfirmed: true,
      customerConfirmedAt: '2026-08-15 08:45',
      staffConfirmed: false,
      gatePassed: false
    },
    missingFields: [],
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed' },
      { stepNo: 2, name: '媒合月嫂候選人', status: 'completed' },
      { stepNo: 3, name: '發送詢問月嫂意願', status: 'completed' },
      { stepNo: 4, name: '月嫂回傳願意接案', status: 'completed' },
      { stepNo: 5, name: '客戶確認月嫂履歷', status: 'completed' },
      { stepNo: 6, name: '月嫂契約簽回', status: 'completed' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'completed' },
      { stepNo: 8, name: '客戶契約簽回', status: 'completed' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'in_progress', notes: '⏳ 客戶已確認，待月嫂確認' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'pending' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0803',
    clientName: '張雅婷 小姐',
    clientPhone: '0933-111-222',
    serviceRange: '2026/08/01 ~ 2026/08/30',
    serviceDays: 30,
    serviceAddress: '台北市信義區松德路',
    contractAmount: 90000,
    depositAmount: 20000,
    depositSettled: true,
    stage: 'active_service',
    actualStartDate: '2026-08-01',
    currentStepDesc: '步驟 10/11: 正式服務履約中 (第 15/30 天)',
    waitingFor: '服務正常進行中，月嫂每日打卡簽到',
    serviceTimeTuple: {
      startTime: '08:00',
      endTime: '17:00',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: true,
    floorFee: 0,
    staffContractSigned: true,
    clientContractSigned: true,
    assignedDoula: {
      id: 'STF-001',
      name: '王美惠 阿姨',
      phone: '0918-999-888',
      matchScore: 98
    },
    dateConfirmation: {
      actualStartDate: '2026-08-01',
      calculatedEndDate: '2026-08-30',
      calculatedServiceDays: 30,
      restDaysSummary: '正常無排休',
      bufferDateRange: '2026/08/31 ~ 2026/09/06 (7天)',
      customerConfirmed: true,
      customerConfirmedAt: '2026-07-28 10:00',
      staffConfirmed: true,
      staffConfirmedAt: '2026-07-28 10:15',
      gatePassed: true
    },
    missingFields: [],
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed' },
      { stepNo: 2, name: '媒合月嫂候選人', status: 'completed' },
      { stepNo: 3, name: '發送詢問月嫂意願', status: 'completed' },
      { stepNo: 4, name: '月嫂回傳願意接案', status: 'completed' },
      { stepNo: 5, name: '客戶確認月嫂履歷', status: 'completed' },
      { stepNo: 6, name: '月嫂契約簽回', status: 'completed' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'completed' },
      { stepNo: 8, name: '客戶契約簽回', status: 'completed' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'completed', notes: '✅ 雙方均已確認無異議' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'in_progress', timestamp: '2026/08/01 09:00', notes: '🟢 履約中' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'pending' }
    ]
  },
  {
    id: 'ORD-2026-0804',
    clientName: '李佳玲 小姐',
    clientPhone: '0955-444-333',
    serviceRange: '2026/07/10 ~ 2026/08/09',
    serviceDays: 30,
    serviceAddress: '新北市中和區中正路',
    contractAmount: 75000,
    depositAmount: 15000,
    depositSettled: true,
    stage: 'settlement_payout',
    actualStartDate: '2026-07-10',
    currentStepDesc: '步驟 11/11: 服務已完工，待時數核對與薪資發放',
    waitingFor: '等待會計核對實際簽到時數與發放月嫂薪資 $62,000',
    serviceTimeTuple: {
      startTime: '09:00',
      endTime: '18:00',
      dayOffset: 0,
      dailyHours: 9
    },
    requiresCooking: false,
    floorFee: 0,
    staffContractSigned: true,
    clientContractSigned: true,
    assignedDoula: {
      id: 'STF-002',
      name: '張秀梅 阿姨',
      phone: '0928-777-666',
      matchScore: 95
    },
    missingFields: [],
    stepsChecklist: [
      { stepNo: 1, name: '進件報名與資料完整性驗證', status: 'completed' },
      { stepNo: 2, name: '媒合月嫂候選人', status: 'completed' },
      { stepNo: 3, name: '發送詢問月嫂意願', status: 'completed' },
      { stepNo: 4, name: '月嫂回傳願意接案', status: 'completed' },
      { stepNo: 5, name: '客戶確認月嫂履歷', status: 'completed' },
      { stepNo: 6, name: '月嫂契約簽回', status: 'completed' },
      { stepNo: 7, name: '客戶定金核銷 (訂單成立)', status: 'completed' },
      { stepNo: 8, name: '客戶契約簽回', status: 'completed' },
      { stepNo: 9, name: '填寫實際開始日 & 雙方確認實際服務日期', status: 'completed' },
      { stepNo: 10, name: '轉換正式排班與服務履約', status: 'completed', timestamp: '2026/08/09 18:00' },
      { stepNo: 11, name: '完工驗收、時數核對與尾款/薪資結清', status: 'in_progress', notes: '💰 待會計核算發放' }
    ]
  }
];

export const MOCK_ANOMALIES: AnomalyItem[] = [
  {
    id: 'ANM-001',
    domain: '財務對帳',
    subType: '溢繳短繳不符',
    severity: 'CRITICAL',
    description: '訂單 #ORD-2026-0801 實收訂金 $15,000 與合約載明訂金 $20,000 不一致，差額 $5,000',
    relatedEntity: 'ORD-2026-0801',
    resolved: false
  },
  {
    id: 'ANM-002',
    domain: '排班契約',
    subType: 'G05請假競爭衝突',
    severity: 'CRITICAL',
    description: '月嫂 李淑貞 於 2026/08/12 申請喪假，造成訂單 #ORD-2026-0803 該時段無代班月嫂',
    relatedEntity: 'STF-003',
    resolved: false
  },
  {
    id: 'ANM-003',
    domain: '匯入資料',
    subType: 'BeClass欄位缺失',
    severity: 'WARNING',
    description: 'BeClass 報名匯入批次 #BC-8821 包含 2 筆無聯絡電話之過渡資料',
    relatedEntity: 'BC-8821',
    resolved: false
  },
  {
    id: 'ANM-004',
    domain: '系統整合',
    subType: 'LINE Outbox滯留',
    severity: 'INFO',
    description: 'LINE 派單推播佇列有 1 筆訊息等待 Worker 重試中',
    relatedEntity: 'MSG-9921',
    resolved: false
  }
];

export const MOCK_FINANCE: FinanceTransaction[] = [
  {
    id: 'TX-202608-01',
    type: '客戶退款',
    recipient: '黃雅玲 小姐',
    bankAccount: '台新銀行 (812) ****5678',
    amount: 15000,
    status: '待審核',
    createdAt: '2026-08-14'
  },
  {
    id: 'TX-202608-02',
    type: '月嫂請款',
    recipient: '王美惠 阿姨',
    bankAccount: '台北富邦 (012) ****1234',
    amount: 62000,
    status: '已核算',
    createdAt: '2026-08-13'
  },
  {
    id: 'TX-202608-03',
    type: '政府補助',
    recipient: '勞動部月子津貼專案',
    bankAccount: '工會專戶 (004) ****9999',
    amount: 30000,
    status: '待審核',
    createdAt: '2026-08-12'
  }
];

export const MOCK_ACCOUNTS: UserAccount[] = [
  {
    id: 'USR-01',
    username: 'admin',
    name: '系統管理員 (Super Admin)',
    role: '超級管理員',
    totpEnabled: true,
    status: '啟用',
    lastLogin: '2026-08-14 20:45'
  },
  {
    id: 'USR-02',
    username: 'operator_lin',
    name: '林美雲 (行政秘書)',
    role: '工會行政',
    totpEnabled: true,
    status: '啟用',
    lastLogin: '2026-08-14 17:30'
  },
  {
    id: 'USR-03',
    username: 'finance_chen',
    name: '陳會計',
    role: '會計財務',
    totpEnabled: false,
    status: '啟用',
    lastLogin: '2026-08-14 15:10'
  },
  {
    id: 'USR-04',
    username: 'auditor_wu',
    name: '吳稽核委員',
    role: '系統稽核',
    totpEnabled: true,
    status: '啟用',
    lastLogin: '2026-08-13 11:20'
  }
];
