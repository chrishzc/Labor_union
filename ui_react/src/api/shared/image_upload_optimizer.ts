/**
 * File: image_upload_optimizer.ts
 * Description: 上傳前圖片尺寸縮放／壓縮及有上限並發執行工具（不建立 DOM 預覽或 base64）。
 */

export const MAX_PHOTO_LONG_EDGE = 2048;
export const PHOTO_OPTIMIZE_THRESHOLD_BYTES = 1024 * 1024;
export const PHOTO_ENCODE_QUALITY = 0.85;

const OPTIMIZABLE_MIMES = new Set(['image/jpeg', 'image/png', 'image/webp']);

async function renderScaledBlob(
  bitmap: ImageBitmap,
  targetWidth: number,
  targetHeight: number,
  mimeType: string,
): Promise<Blob | null> {
  const quality = mimeType === 'image/jpeg' || mimeType === 'image/webp' ? PHOTO_ENCODE_QUALITY : undefined;
  if (typeof OffscreenCanvas !== 'undefined') {
    const canvas = new OffscreenCanvas(targetWidth, targetHeight);
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.drawImage(bitmap, 0, 0, targetWidth, targetHeight);
    if (typeof canvas.convertToBlob === 'function') {
      return await canvas.convertToBlob({ type: mimeType, quality });
    }
  }
  if (typeof document !== 'undefined') {
    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const context = canvas.getContext('2d');
    if (!context) return null;
    context.drawImage(bitmap, 0, 0, targetWidth, targetHeight);
    return await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((blob) => resolve(blob), mimeType, quality);
    });
  }
  return null;
}

/** Shrink oversized JPEG/PNG/WebP uploads off-DOM before transfer; fall back safely on any unsupported runtime. */
export async function optimizeImageForUpload(file: File): Promise<File> {
  const mimeType = file.type.toLowerCase();
  if (
    !OPTIMIZABLE_MIMES.has(mimeType)
    || file.size <= PHOTO_OPTIMIZE_THRESHOLD_BYTES
    || typeof createImageBitmap !== 'function'
  ) {
    return file;
  }

  let bitmap: ImageBitmap | null = null;
  try {
    bitmap = await createImageBitmap(file);
    const maxDim = Math.max(bitmap.width, bitmap.height);
    if (maxDim <= 0) return file;

    const scale = maxDim > MAX_PHOTO_LONG_EDGE ? MAX_PHOTO_LONG_EDGE / maxDim : 1;
    const targetWidth = Math.max(1, Math.round(bitmap.width * scale));
    const targetHeight = Math.max(1, Math.round(bitmap.height * scale));
    if (mimeType === 'image/png' && scale === 1) {
      return file;
    }

    const blob = await renderScaledBlob(bitmap, targetWidth, targetHeight, mimeType);
    if (!blob || blob.size <= 0 || blob.size >= file.size) {
      return file;
    }
    return new File([blob], file.name, {
      type: blob.type || mimeType,
      lastModified: file.lastModified,
    });
  } catch {
    return file;
  } finally {
    bitmap?.close?.();
  }
}

/** Run async tasks with a fixed worker bound while preserving deterministic result order. */
export async function mapWithConcurrency<T, R>(
  items: readonly T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  if (items.length === 0) return [];
  const results = new Array<R>(items.length);
  const limit = Math.max(1, Math.min(Math.floor(concurrency) || 1, items.length));
  let nextIndex = 0;
  let hasError = false;
  let firstError: unknown;

  async function runWorker(): Promise<void> {
    while (!hasError) {
      const current = nextIndex;
      nextIndex += 1;
      if (current >= items.length) return;
      try {
        results[current] = await worker(items[current]!, current);
      } catch (error) {
        if (!hasError) {
          hasError = true;
          firstError = error;
        }
        return;
      }
    }
  }

  await Promise.allSettled(Array.from({ length: limit }, () => runWorker()));
  if (hasError) throw firstError;
  return results;
}
