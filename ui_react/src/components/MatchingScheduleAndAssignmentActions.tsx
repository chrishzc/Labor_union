import React from 'react';
import { ServiceStartSubstituteWorkbench } from './ServiceStartSubstituteWorkbench';
interface PlanSegment {
  segmentId: number;
  sequence: number;
  staffId: number;
  assignedStartDate: string;
  assignedEndDate: string;
}

interface Props {
  caseNo: string;
  planId: number;
  planSegments: readonly PlanSegment[];
  waitingLockAcquired: boolean;
  assignmentExists: boolean;
  officialServiceDates?: readonly string[];
  contractReady?: boolean;
  depositReady?: boolean;
  onOpenDates?: () => void;
  onOpenRecommendation?: () => void;
  onAssignmentCompleted: () => Promise<void>;
  staffNames?: Readonly<Record<number, string>>;
  onEditStateChange?: (state: { dirty: boolean; busy: boolean }) => void;
}

export const MatchingScheduleAndAssignmentActions: React.FC<Props> = ({caseNo,assignmentExists,officialServiceDates=[],onAssignmentCompleted}) => (
  <section aria-label="服務開始與排班結果">
    <p>{assignmentExists ? '正式排班已生效。' : '客戶與月嫂在服務群組協調後，由月嫂提交開始日期；通過檢查即自動更新排班。'}</p>
    {officialServiceDates.length>0 && <details><summary>查看目前正式服務日期</summary><p>{officialServiceDates.join('、')}</p></details>}
    <ServiceStartSubstituteWorkbench caseNo={caseNo} onCompleted={onAssignmentCompleted}/>
  </section>
);
