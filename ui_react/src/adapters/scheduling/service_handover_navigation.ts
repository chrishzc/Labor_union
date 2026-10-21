export function serviceHandoverHref(caseNo: string, assignmentId?: number): string {
  return `#scheduling?tab=handover&case_no=${encodeURIComponent(caseNo)}${assignmentId ? `&assignment_id=${assignmentId}` : ''}`;
}

export function parseServiceHandoverLink(hash: string) {
  const params = new URLSearchParams(hash.split('?')[1] ?? '');
  if (params.getAll('case_no').length !== 1 || params.getAll('assignment_id').length > 1) return null;
  const caseNo = params.get('case_no') ?? '';
  const assignmentId = params.get('assignment_id');
  if (!caseNo || caseNo !== caseNo.trim() || caseNo.length > 50 || /[\u0000-\u001f\u007f-\u009f]/.test(caseNo)) return null;
  if (assignmentId !== null && (!/^[1-9]\d*$/.test(assignmentId) || !Number.isSafeInteger(Number(assignmentId)))) return null;
  return { caseNo, assignmentId: assignmentId === null ? null : Number(assignmentId) };
}
