import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  mapWithConcurrency,
  MAX_PHOTO_LONG_EDGE,
  optimizeImageForUpload,
  PHOTO_OPTIMIZE_THRESHOLD_BYTES,
} from '../api/shared/image_upload_optimizer';

describe('optimizeImageForUpload', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('passes through small images and non-image files without decoding', async () => {
    const decodeSpy = vi.fn();
    vi.stubGlobal('createImageBitmap', decodeSpy);
    const small = new File([new Uint8Array(100)], 'small.jpg', { type: 'image/jpeg' });
    const pdf = new File([new Uint8Array(PHOTO_OPTIMIZE_THRESHOLD_BYTES + 10)], 'doc.pdf', { type: 'application/pdf' });

    expect(await optimizeImageForUpload(small)).toBe(small);
    expect(await optimizeImageForUpload(pdf)).toBe(pdf);
    expect(decodeSpy).not.toHaveBeenCalled();
  });

  it('downscales oversized photos and returns the smaller file', async () => {
    const closeSpy = vi.fn();
    const drawImageSpy = vi.fn();
    const canvasDims: { width: number; height: number }[] = [];
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 4096, height: 2048, close: closeSpy }));
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(width: number, height: number) { canvasDims.push({ width, height }); }
      getContext() { return { drawImage: drawImageSpy }; }
      async convertToBlob() { return new Blob([new Uint8Array(512)], { type: 'image/jpeg' }); }
    });

    const large = new File([new Uint8Array(PHOTO_OPTIMIZE_THRESHOLD_BYTES + 5000)], 'photo.jpg', { type: 'image/jpeg', lastModified: 1234 });
    const optimized = await optimizeImageForUpload(large);

    expect(canvasDims).toEqual([{ width: MAX_PHOTO_LONG_EDGE, height: 1024 }]);
    expect(drawImageSpy).toHaveBeenCalledOnce();
    expect(closeSpy).toHaveBeenCalledOnce();
    expect(optimized).not.toBe(large);
    expect(optimized.name).toBe('photo.jpg');
    expect(optimized.type).toBe('image/jpeg');
    expect(optimized.size).toBe(512);
  });

  it('falls back to original file when re-encoded blob is larger or decoding throws', async () => {
    const closeSpy = vi.fn();
    const large = new File([new Uint8Array(PHOTO_OPTIMIZE_THRESHOLD_BYTES + 100)], 'photo.jpg', { type: 'image/jpeg' });
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 3000, height: 3000, close: closeSpy }));
    vi.stubGlobal('OffscreenCanvas', class {
      getContext() { return { drawImage: vi.fn() }; }
      async convertToBlob() { return new Blob([new Uint8Array(large.size + 10)], { type: 'image/jpeg' }); }
    });

    expect(await optimizeImageForUpload(large)).toBe(large);
    expect(closeSpy).toHaveBeenCalledOnce();

    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('decode failed')));
    expect(await optimizeImageForUpload(large)).toBe(large);
  });
});

describe('mapWithConcurrency', () => {
  it('enforces concurrency limits and preserves output ordering', async () => {
    let active = 0;
    let maxActive = 0;
    const result = await mapWithConcurrency([40, 10, 30, 5], 2, async (delay, index) => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setTimeout(resolve, delay));
      active -= 1;
      return `${index}:${delay}`;
    });

    expect(maxActive).toBe(2);
    expect(result).toEqual(['0:40', '1:10', '2:30', '3:5']);
  });

  it('stops scheduling new items after a worker fails and drains in-flight siblings', async () => {
    const visited: number[] = [];
    let siblingSettled = false;
    let releaseSibling!: () => void;
    const siblingGate = new Promise<void>((resolve) => { releaseSibling = resolve; });

    const promise = mapWithConcurrency([1, 2, 3, 4], 2, async (item) => {
      visited.push(item);
      if (item === 1) {
        await siblingGate;
        siblingSettled = true;
        return item;
      }
      if (item === 2) throw new Error('boom');
      return item;
    });

    let settledBeforeSibling = false;
    void promise.catch(() => { settledBeforeSibling = !siblingSettled; });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(settledBeforeSibling).toBe(false);

    releaseSibling();
    await expect(promise).rejects.toThrow('boom');
    expect(siblingSettled).toBe(true);
    expect(visited).toEqual([1, 2]);
  });
});
