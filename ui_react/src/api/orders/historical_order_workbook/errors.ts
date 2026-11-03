/**
 * File: errors.ts
 * Description: 將Historical Orders Preview／Apply失敗分流為去敏typed錯誤，標示安全重試狀態。
 */
import { ApiAbortError, ApiDecodeError, ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../../shared/typed_errors';

export class HistoricalOrderWorkbookPreviewError extends Error {
  public readonly code: string;
  public readonly retryable: boolean;
  public readonly status: number | null;

  constructor(
    code: string,
    message: string,
    retryable = false,
    status: number | null = null
  ) {
    super(message);
    this.name = 'HistoricalOrderWorkbookPreviewError';
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class HistoricalOrderWorkbookContractError extends HistoricalOrderWorkbookPreviewError {}
export class HistoricalOrderWorkbookFileError extends HistoricalOrderWorkbookPreviewError {}

export class HistoricalOrderWorkbookApplyError extends HistoricalOrderWorkbookPreviewError {
  constructor(code: string, message: string, retryable = false, status: number | null = null) {
    super(code, message, retryable, status);
    this.name = 'HistoricalOrderWorkbookApplyError';
  }
}

export class HistoricalOrderWorkbookUnauthenticatedError extends HistoricalOrderWorkbookPreviewError {
  constructor(operation: 'preview' | 'apply' = 'preview') {
    super(
      `historical_order_${operation}_unauthenticated`,
      operation === 'apply' ? '管理員 Session 已失效，無法套用歷史訂單檔案。' : '管理員 Session 已失效，無法預覽歷史訂單檔案。'
    );
  }
}

const DATABASE_ERROR_MESSAGES: Record<string, string> = {
  historical_order_database_connect_failed: '無法連接資料庫；請檢查資料庫服務、主機、連接埠與網路。',
  historical_order_database_host_not_found: '無法解析資料庫主機名稱；請檢查主機設定與 DNS。',
  historical_order_database_connection_lost: '資料庫連線在處理期間中斷；請檢查服務狀態與連線紀錄。',
  historical_order_database_tls_failed: '資料庫加密連線失敗；請檢查憑證與加密連線設定。',
  historical_order_database_authentication_failed: '資料庫登入失敗；請管理員檢查連線帳號與驗證設定。',
  historical_order_database_permission_denied: '資料庫操作權限不足；請管理員核對匯入帳號的必要權限。',
  historical_order_database_not_found: '指定的資料庫不存在；請檢查資料庫名稱與部署設定。',
  historical_order_database_table_missing: '缺少必要資料表；請檢查連線目標與資料庫升級狀態。',
  historical_order_database_column_missing: '缺少必要資料欄位；請檢查程式與資料庫版本是否一致。',
  historical_order_database_routine_missing: '缺少必要資料庫程序；請檢查資料庫升級與程序安裝狀態。',
  historical_order_database_lock_wait_exceeded: '等待資料庫資料鎖逾時；請查核佔鎖交易，再確認原匯入結果。',
  historical_order_database_deadlock: '資料庫交易發生死結；請查核交易紀錄，再確認原匯入結果。',
  historical_order_database_connection_limit_reached: '資料庫連線已達上限；請檢查連線使用量與連線限制。',
  historical_order_database_query_invalid: '資料庫指令語法錯誤；請系統人員檢查程式與資料庫相容性。',
  historical_order_database_data_rejected: '資料超過資料庫欄位長度；請核對來源資料與欄位設定。',
  historical_order_database_constraint_rejected: '資料庫唯一性或關聯限制拒絕寫入；請查核既有資料與匯入規則。',
  historical_order_database_upgrade_required: '歷史訂單資料庫結構尚未升級；請由系統管理員完成資料庫更新後，再確認匯入結果。',
  historical_order_database_unknown_error: '資料庫未提供可辨識的錯誤號碼；請系統人員查核該次錯誤紀錄。',
  historical_order_import_database_unavailable: '歷史訂單的資料庫操作失敗；請由系統管理員檢查資料庫連線與權限，並查核該次資料庫錯誤紀錄，再確認匯入結果。',
};

function databaseErrorMessage(error: ApiHttpError): string | undefined {
  const message = DATABASE_ERROR_MESSAGES[error.code] ?? (/^historical_order_database_mysql_\d{1,5}$/.test(error.code)
    ? '資料庫回報未分類錯誤；請系統人員依錯誤代碼查核。' : undefined);
  if (!message) return undefined;
  // Only preserve the backend's numeric diagnostic, never SQL, names or provider text.
  const diagnostic = error.message.match(/（MySQL ([1-9]\d{0,4})）/)?.[1];
  return `${message}${diagnostic ? `（MySQL ${diagnostic}）` : ''}`;
}

export function mapHistoricalOrderWorkbookPreviewError(error: unknown): Error {
  if (error instanceof HistoricalOrderWorkbookPreviewError || error instanceof ApiDecodeError) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HistoricalOrderWorkbookUnauthenticatedError();
    const databaseMessage = databaseErrorMessage(error);
    if (databaseMessage) return new HistoricalOrderWorkbookPreviewError(error.code, databaseMessage, error.retryable, error.status);
    const message = error.code === 'historical_assignment_required_for_actual_start'
      ? '歷史訂單缺少已完成的歷史服務指派，無法重建實際開工資料。'
      : error.status === 403
      ? '目前 Session 沒有預覽歷史訂單檔案的權限。'
      : error.status === 422
        ? '歷史訂單檔案未通過伺服器預覽驗證。'
        : '歷史訂單檔案預覽目前無法完成。';
    return new HistoricalOrderWorkbookPreviewError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_timeout', '歷史訂單檔案預覽逾時。', true);
  if (error instanceof ApiNetworkError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_network_error', '歷史訂單檔案預覽連線失敗。', true);
  if (error instanceof ApiAbortError) return new HistoricalOrderWorkbookPreviewError('historical_order_preview_aborted', '歷史訂單檔案預覽已取消。', true);
  return new HistoricalOrderWorkbookPreviewError('historical_order_preview_unexpected_error', '歷史訂單檔案預覽發生未預期錯誤。');
}

export function mapHistoricalOrderWorkbookApplyError(error: unknown): Error {
  if (
    error instanceof HistoricalOrderWorkbookApplyError
    || error instanceof HistoricalOrderWorkbookContractError
    || error instanceof HistoricalOrderWorkbookFileError
    || error instanceof HistoricalOrderWorkbookUnauthenticatedError
    || error instanceof ApiDecodeError
  ) return error;
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return new HistoricalOrderWorkbookUnauthenticatedError('apply');
    const databaseMessage = databaseErrorMessage(error);
    // A row-atomic import may already contain committed rows even for a configuration error.
    if (databaseMessage) return new HistoricalOrderWorkbookApplyError(error.code, databaseMessage, true, error.status);
    if (error.code === 'historical_client_payment_terms_missing') return new HistoricalOrderWorkbookApplyError(error.code, '歷史案件缺少客戶付款條款，無法建立應收應付；本次匯入未完成，請先補齊付款條款。', false, error.status);
    if (error.code === 'historical_payroll_rate_policy_missing') return new HistoricalOrderWorkbookApplyError(error.code, '歷史案件缺少月嫂薪資費率，無法建立應付帳務；本次匯入未完成，請先補齊費率。', false, error.status);
    if (error.code === 'historical_default_accounting_unavailable') return new HistoricalOrderWorkbookApplyError(error.code, '歷史帳務建立服務未就緒，本次匯入未完成，請由系統管理員檢查服務設定。', false, error.status);
    if (error.code.endsWith('_lock_timeout')) return new HistoricalOrderWorkbookApplyError(error.code, '歷史訂單匯入等待處理鎖逾時，先前操作可能仍在處理；結果尚未確認，請保留本頁確認結果。', true, error.status);
    if (error.status === 502 || error.status === 504) return new HistoricalOrderWorkbookApplyError(error.code, error.status === 504 ? '等待歷史訂單匯入的閘道回應逾時（HTTP 504），結果尚未確認，請保留本頁確認結果。' : '歷史訂單匯入閘道無法取得後端有效回應（HTTP 502），結果尚未確認，請保留本頁確認結果。', error.retryable, error.status);
    const message = error.status === 403
      ? '目前 Session 沒有套用歷史訂單檔案的權限。'
      : error.status === 409
        ? '歷史訂單檔案套用與既有操作衝突，請重新預覽後再試。'
        : error.status === 422
          ? '歷史訂單檔案未通過套用驗證，請重新預覽。'
          : error.status === 503
            ? '歷史訂單匯入服務暫時無法回覆（HTTP 503），結果尚未確認，可稍後查詢這次匯入結果。'
            : '歷史訂單檔案套用目前無法完成。';
    return new HistoricalOrderWorkbookApplyError(error.code || `HTTP_${error.status}`, message, error.retryable, error.status);
  }
  if (error instanceof ApiTimeoutError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_timeout', '等待歷史訂單匯入回應逾時，結果尚未確認，資料可能已寫入。系統會自動確認，請保留本頁。', true);
  if (error instanceof ApiNetworkError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_network_error', '歷史訂單匯入連線中斷，結果尚未確認，資料可能已寫入。系統會自動確認，請保留本頁。', true);
  if (error instanceof ApiAbortError) return new HistoricalOrderWorkbookApplyError('historical_order_apply_aborted', '歷史訂單檔案套用已取消，請先確認結果再重試。', true);
  return new HistoricalOrderWorkbookApplyError('historical_order_apply_unexpected_error', '歷史訂單檔案套用發生未預期錯誤。');
}
