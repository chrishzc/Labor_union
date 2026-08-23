/**
 * File: customer_service_escalation_errors.ts
 * Description: 將 M4 escalation 的認證、衝突、outcome unknown 與契約錯誤型別化。
 */

import { ApiAbortError, ApiError, ApiHttpError, ApiNetworkError, ApiTimeoutError, extractErrorMessage } from '../shared/typed_errors';

export type CustomerServiceEscalationErrorCode =
  | 'CUSTOMER_SERVICE_ESCALATION_UNAUTHENTICATED'
  | 'CUSTOMER_SERVICE_ESCALATION_FORBIDDEN'
  | 'CUSTOMER_SERVICE_ESCALATION_NOT_FOUND'
  | 'CUSTOMER_SERVICE_ESCALATION_VALIDATION'
  | 'CUSTOMER_SERVICE_ESCALATION_CONFLICT'
  | 'CUSTOMER_SERVICE_ESCALATION_IDEMPOTENCY_MISMATCH'
  | 'CUSTOMER_SERVICE_ESCALATION_UNAVAILABLE'
  | 'CUSTOMER_SERVICE_ESCALATION_OUTCOME_UNKNOWN'
  | 'CUSTOMER_SERVICE_ESCALATION_CONTRACT'
  | 'CUSTOMER_SERVICE_ESCALATION_ABORTED'
  | 'CUSTOMER_SERVICE_ESCALATION_NETWORK';

export type CustomerServiceEscalationOperation = 'create' | 'detail' | 'claim' | 'handling' | 'resolve';

export class CustomerServiceEscalationError extends ApiError {
  public readonly name = 'CustomerServiceEscalationError';
  public readonly code: CustomerServiceEscalationErrorCode;
  public readonly options: {
    status?: number;
    retryable?: boolean;
    outcomeUnknown?: boolean;
    publicCode?: string;
    originalError?: unknown;
  };

  constructor(
    code: CustomerServiceEscalationErrorCode,
    message: string,
    options: {
      status?: number;
      retryable?: boolean;
      outcomeUnknown?: boolean;
      publicCode?: string;
      originalError?: unknown;
    } = {},
  ) {
    super(message);
    this.code = code;
    this.options = options;
  }

  get status(): number | undefined { return this.options.status; }
  get retryable(): boolean { return this.options.retryable ?? false; }
  get outcomeUnknown(): boolean { return this.options.outcomeUnknown ?? false; }
  get publicCode(): string | undefined { return this.options.publicCode; }
}

function isMutation(operation: CustomerServiceEscalationOperation): boolean {
  return operation !== 'detail';
}

export function mapCustomerServiceEscalationError(error: unknown, operation: CustomerServiceEscalationOperation): CustomerServiceEscalationError {
  if (error instanceof CustomerServiceEscalationError) return error;
  if (error instanceof ApiAbortError) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_ABORTED', error.message, { originalError: error });
  if (error instanceof ApiTimeoutError || error instanceof ApiNetworkError) {
    const unknown = isMutation(operation);
    return new CustomerServiceEscalationError(unknown ? 'CUSTOMER_SERVICE_ESCALATION_OUTCOME_UNKNOWN' : 'CUSTOMER_SERVICE_ESCALATION_NETWORK', error.message, { retryable: true, outcomeUnknown: unknown, originalError: error });
  }
  if (error instanceof ApiHttpError) {
    const options = { status: error.status, retryable: error.retryable, publicCode: error.code, originalError: error };
    if (isMutation(operation) && [502, 503, 504].includes(error.status)) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_OUTCOME_UNKNOWN', error.message, { ...options, retryable: true, outcomeUnknown: true });
    if (error.status === 401) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_UNAUTHENTICATED', error.message, options);
    if (error.status === 403) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_FORBIDDEN', error.message, options);
    if (error.status === 404) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_NOT_FOUND', error.message, options);
    if (error.status === 409 && error.code.includes('idempotency')) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_IDEMPOTENCY_MISMATCH', error.message, options);
    if (error.status === 409) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_CONFLICT', error.message, options);
    if ([502, 503, 504].includes(error.status)) return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_UNAVAILABLE', error.message, { ...options, retryable: true });
    return new CustomerServiceEscalationError('CUSTOMER_SERVICE_ESCALATION_VALIDATION', error.message, options);
  }
  return new CustomerServiceEscalationError(
    isMutation(operation) ? 'CUSTOMER_SERVICE_ESCALATION_OUTCOME_UNKNOWN' : 'CUSTOMER_SERVICE_ESCALATION_NETWORK',
    extractErrorMessage(error),
    { retryable: true, outcomeUnknown: isMutation(operation), originalError: error },
  );
}
