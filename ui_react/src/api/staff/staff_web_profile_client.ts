import { z } from 'zod';
import { notificationOptions } from '../line_notifications/notification_tasks_client';
import { transport } from '../shared/transport';
import { ApiHttpError, ApiNetworkError, ApiTimeoutError } from '../shared/typed_errors';

const id = z.number().int().positive();
const fileId = z.string().regex(/^cf_[a-f0-9]{32}$/);
const category = z.enum(['photo', 'certificate', 'other', 'feedback']);
const templatesPath = '/api/v1/admin/staff-web-profile/templates';
const rosterPath = (staffId: number) => `/api/v1/admin/staff-web-profile/${staffId}`;
const reviewPath = (id: number) => `/api/v1/admin/staff-profile-change-requests/${id}`;
const reviewPhotoPath = (requestId: number, index: number) => `${reviewPath(requestId)}/web-photos/${index}`;

export const webProfileCategories = category.options;
export const webProfileCategoryLabels = { photo: '照片', certificate: '證照', other: '其他', feedback: '客戶反饋' } satisfies Record<WebProfileCategory, string>;
const entryVersionSchema = z.strictObject({ entry_id: id, entry_version: id });
const folderFileSchema = entryVersionSchema.extend({ filename: z.string().min(1), expiry_date: z.iso.date().nullable() });
const folderSchema = z.strictObject({
  template_item_id: id,
  template_version: id,
  name: z.string().min(1),
  category,
  count: z.number().int().nonnegative(),
  files: z.array(folderFileSchema),
}).refine(folder => folder.count === folder.files.length && (folder.category !== 'other' || folder.count <= 1));
const foldersSchema = z.strictObject({ items: z.array(folderSchema) });
const uploadedPhotoSchema = z.strictObject({ file_id: fileId, filename: z.string().min(1) });
const publicationsSchema = z.strictObject({ files: z.array(entryVersionSchema).min(1).max(50) });
const removedFileSchema = z.strictObject({ entry_id: id });
const templateSchema = z.object({
  item_id: id,
  version: id,
  name: z.string(),
  category,
  display_order: z.number().int().nonnegative(),
  reminder_enabled: z.boolean(),
  reminder_lead: z.object({ months: z.number().int().nonnegative(), days: z.number().int().nonnegative() }),
});
const publishedImageSchema = z.object({ item_name: z.string(), image_entry: id, image_version: id });
const publishedProfileSchema = z.object({
  name: z.string(),
  groups: z.array(z.object({ category, images: z.array(publishedImageSchema) })).max(webProfileCategories.length),
});
const pendingPhotoSchema = z.object({
  template_item_id: id,
  template_version: id,
  original_file_id: fileId,
  crop_file_id: fileId.nullable(),
  expiry_date: z.iso.date().nullable(),
  entry_id: id.nullable(),
  entry_version: id.nullable(),
});
const values = z.record(z.string(), z.unknown());
const fieldChange = z.object({ before: values.nullable(), after: values.nullable() });
const reviewSchema = z.object({
  id,
  staff_id: id,
  version: id,
  status: z.enum(['pending', 'approving', 'approved', 'rejected', 'conflict']),
  changes: z.object({
    profile: fieldChange.optional(),
    bank: fieldChange.optional(),
    relations: fieldChange.optional(),
    transportation: fieldChange.optional(),
    matching: fieldChange.optional(),
    web_contents: z.array(pendingPhotoSchema).optional(),
  }).nullable(),
  publications: z.array(z.object({ entry_id: id, version: id, template_item_id: id, file_id: fileId })).optional(),
});

export type WebProfileCategory = z.infer<typeof category>;
export type WebProfileFolder = z.infer<typeof folderSchema>;
export type WebProfileFolderFile = z.infer<typeof folderFileSchema>;
export type WebProfilePublicationInput = {
  operation_id: string;
  template_item_id: number;
  template_version: number;
  files: { file_id: string; expiry_date: string | null }[];
  expected_current: z.infer<typeof entryVersionSchema> | null;
};
export type WebProfileTemplate = z.infer<typeof templateSchema>;
export type PublishedWebProfile = z.infer<typeof publishedProfileSchema>;
export type StaffProfileReview = z.infer<typeof reviewSchema>;
export type PendingWebPhoto = z.infer<typeof pendingPhotoSchema>;
export type CropBox = { left: number; top: number; right: number; bottom: number };
export type WebProfileTemplateInput = Pick<WebProfileTemplate, 'name' | 'category' | 'display_order' | 'reminder_enabled' | 'version'> & {
  reminder_months: number;
  reminder_days: number;
};

export function staffWebError(error: unknown, fallback: string): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 401) return '登入已失效，請重新登入。';
    if (error.status === 403) return '目前帳號沒有此操作的權限。';
    if (error.status === 404) return '找不到資料，請重新讀取。';
    if (error.status === 409) return '資料已更新，請重新讀取後再操作。';
    if (error.status === 422) return '請核對欄位、照片與日期後再試。';
  }
  return fallback;
}

export function staffWebFileError(error: unknown, fallback: string): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 413) return '照片超過上傳大小上限，請縮小後重新選擇。';
    if (error.code.startsWith('staff_web_') || error.retryable) return error.message;
  }
  if (error instanceof ApiTimeoutError) return '操作逾時，結果尚未確認，可用原操作重試。';
  if (error instanceof ApiNetworkError) return '連線中斷，請檢查網路後重試。';
  return staffWebError(error, fallback);
}

async function fetchImage(path: string, signal: AbortSignal): Promise<Blob> {
  const result = await transport.get<unknown>(path, {
    ...notificationOptions(signal), responseType: 'blob', cache: 'no-store',
  });
  if (!(result instanceof Blob) || !result.type.startsWith('image/')) throw new Error('invalid_image_response');
  return result;
}

export function publishedStaffWebProfilePath(staffId: number): string {
  return `/api/v1/admin/staff-web-profile/${staffId}/preview`;
}

export const staffWebProfileClient = {
  async folders(staffId: number, signal?: AbortSignal) {
    const result = await transport.get<{ data: unknown }>(`${rosterPath(staffId)}/folders`, {
      ...notificationOptions(signal), cache: 'no-store',
    });
    return foldersSchema.parse(result.data).items;
  },
  async uploadForStaff(staffId: number, file: File, uploadId: string, signal?: AbortSignal) {
    const body = new FormData();
    body.set('upload_id', uploadId);
    body.set('photograph', file);
    const result = await transport.post<{ data: unknown }>(`${rosterPath(staffId)}/uploads`, body, notificationOptions(signal));
    return uploadedPhotoSchema.parse(result.data);
  },
  async publishForStaff(staffId: number, command: WebProfilePublicationInput, signal?: AbortSignal) {
    const result = await transport.post<{ data: unknown }>(
      `${rosterPath(staffId)}/publications`, command, notificationOptions(signal),
    );
    return publicationsSchema.parse(result.data);
  },
  async removeForStaff(staffId: number, folder: WebProfileFolder, file: WebProfileFolderFile, signal?: AbortSignal) {
    const result = await transport.delete<{ data: unknown }>(
      `${rosterPath(staffId)}/folders/${folder.template_item_id}/entries/${file.entry_id}`,
      {
        ...notificationOptions(signal),
        params: { template_version: folder.template_version, entry_version: file.entry_version },
      },
    );
    return removedFileSchema.parse(result.data);
  },
  async templates(signal?: AbortSignal) {
    const result = await transport.get<{ data: unknown }>(templatesPath, notificationOptions(signal));
    return z.array(templateSchema).parse(result.data);
  },
  async saveTemplate(itemId: number | null, input: WebProfileTemplateInput) {
    const options = notificationOptions();
    const result = itemId === null
      ? await transport.post<{ data: unknown }>(templatesPath, input, options)
      : await transport.put<{ data: unknown }>(`${templatesPath}/${itemId}`, input, options);
    return templateSchema.parse(result.data);
  },
  async review(requestId: number, signal?: AbortSignal) {
    const result = await transport.get<{ data: unknown }>(reviewPath(requestId), notificationOptions(signal));
    return reviewSchema.parse(result.data);
  },
  async decide(requestId: number, version: number, action: 'approve' | 'reject') {
    const result = await transport.post<{ data: unknown }>(
      `${reviewPath(requestId)}/decision`, { version, action }, notificationOptions(),
    );
    return reviewSchema.parse(result.data);
  },
  async changeCrop(requestId: number, index: number, version: number, box: CropBox | null) {
    const path = `${reviewPhotoPath(requestId, index)}/crop`;
    const options = notificationOptions();
    const result = box
      ? await transport.put<{ data: unknown }>(path, { version, crop_id: crypto.randomUUID(), ...box }, options)
      : await transport.delete<{ data: unknown }>(path, { ...options, params: { version } });
    return reviewSchema.parse(result.data);
  },
  reviewImage(requestId: number, index: number, original: boolean, signal: AbortSignal) {
    return fetchImage(`${reviewPhotoPath(requestId, index)}?original=${original}`, signal);
  },
  async publishedProfile(path: string, signal: AbortSignal) {
    if (!/^\/api\/v1\/admin\/staff-web-profile\/[1-9]\d*\/preview$/.test(path)) {
      throw new Error('invalid_preview_path');
    }
    const result = await transport.get<{ data: unknown }>(path, { ...notificationOptions(signal), cache: 'no-store' });
    return publishedProfileSchema.parse(result.data);
  },
  publishedImage(path: string, image: z.infer<typeof publishedImageSchema>, signal: AbortSignal) {
    return fetchImage(`${path}/images/${image.image_entry}/${image.image_version}`, signal);
  },
};
