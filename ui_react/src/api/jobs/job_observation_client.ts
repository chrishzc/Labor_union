/**
 * File: job_observation_client.ts
 * Description: 以最新記憶體 Bearer 查詢單一背景工作安全狀態。
 */
import { sessionClient } from '../auth/session_client';
import { transport, type RequestOptions } from '../shared/transport';
import { ApiDecodeError } from '../shared/typed_errors';
import { JobObservationResponseSchema, type JobObservation } from './job_observation_schemas';
import { JobObservationError, mapJobObservationError } from './job_observation_errors';

export type JobObservationQueryOptions = Omit<
  RequestOptions,
  'method' | 'body' | 'token' | 'params'
>;

export interface JobObservationClient {
  query(jobId: string, options?: JobObservationQueryOptions): Promise<JobObservation>;
}

function requestOptions(options?: JobObservationQueryOptions): RequestOptions {
  const token = sessionClient.getToken();
  if (!token) throw new JobObservationError('JOB_OBSERVATION_UNAUTHENTICATED', '請先登入。', { status: 401 });
  const headers = { ...(options?.headers ?? {}) };
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'authorization') delete headers[key];
  }
  return { ...options, headers, token };
}

export async function queryJobObservation(
  jobId: string,
  options?: JobObservationQueryOptions,
): Promise<JobObservation> {
  const normalized = jobId.trim();
  if (!normalized || normalized.length > 191) {
    throw new JobObservationError('JOB_OBSERVATION_INVALID', 'job_id 不得為空且不得超過 191 字元。', { status: 422 });
  }
  const endpoint = `/api/v1/jobs/${encodeURIComponent(normalized)}/observation`;
  try {
    const raw = await transport.get<unknown>(endpoint, requestOptions(options));
    const decoded = JobObservationResponseSchema.safeParse(raw);
    if (!decoded.success) {
      throw new ApiDecodeError(
        '背景工作觀察回應結構不符 strict contract。',
        decoded.error.issues.map((issue) => ({
          path: issue.path.join('.') || '(root)',
          message: issue.message,
          code: issue.code,
        })),
        raw,
      );
    }
    if (!decoded.data.success) {
      throw new JobObservationError('JOB_OBSERVATION_INVALID', decoded.data.error ?? decoded.data.message);
    }
    if (decoded.data.data.job_id !== normalized) {
      throw new JobObservationError('JOB_OBSERVATION_INVALID', '背景工作回應 identity 與查詢不一致。');
    }
    return decoded.data.data;
  } catch (error) {
    throw mapJobObservationError(error);
  }
}

export function createJobObservationClient(): JobObservationClient {
  return { query: queryJobObservation };
}

export const jobObservationClient = createJobObservationClient();
