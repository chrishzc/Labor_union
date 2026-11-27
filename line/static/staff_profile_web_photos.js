const PHOTO_UPLOAD_TIMEOUT_MS = 120000;
const MAX_CONCURRENT_PHOTO_UPLOADS = 3;
const MAX_PHOTO_LONG_EDGE = 2048;
const PHOTO_OPTIMIZE_THRESHOLD_BYTES = 1024 * 1024;
const PHOTO_ENCODE_QUALITY = 0.85;
const SUPPORTED_PHOTO_MIMES = new Set(["image/jpeg", "image/png", "image/webp"]);

async function optimizePhotoForUpload(file) {
  const mimeType = (file.type || "").toLowerCase();
  if (
    !SUPPORTED_PHOTO_MIMES.has(mimeType)
    || file.size <= PHOTO_OPTIMIZE_THRESHOLD_BYTES
    || typeof createImageBitmap !== "function"
  ) {
    return file;
  }
  let bitmap = null;
  try {
    bitmap = await createImageBitmap(file);
    const maxDim = Math.max(bitmap.width, bitmap.height);
    if (maxDim <= 0) return file;
    const scale = maxDim > MAX_PHOTO_LONG_EDGE ? MAX_PHOTO_LONG_EDGE / maxDim : 1;
    if (mimeType === "image/png" && scale === 1) return file;
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));
    const quality = mimeType === "image/jpeg" || mimeType === "image/webp" ? PHOTO_ENCODE_QUALITY : undefined;
    let blob = null;
    if (typeof OffscreenCanvas !== "undefined") {
      const canvas = new OffscreenCanvas(width, height);
      const context = canvas.getContext("2d");
      if (context && typeof canvas.convertToBlob === "function") {
        context.drawImage(bitmap, 0, 0, width, height);
        blob = await canvas.convertToBlob({ type: mimeType, quality });
      }
    } else if (typeof document !== "undefined") {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext("2d");
      if (context) {
        context.drawImage(bitmap, 0, 0, width, height);
        blob = await new Promise(resolve => canvas.toBlob(resolve, mimeType, quality));
      }
    }
    if (!blob || blob.size <= 0 || blob.size >= file.size) return file;
    return new File([blob], file.name, { type: blob.type || mimeType, lastModified: file.lastModified });
  } catch {
    return file;
  } finally {
    bitmap?.close?.();
  }
}

function createProfilePhotoForm() {
  const templateSelect = document.getElementById("photo-template");
  const files = document.getElementById("photo-files");
  const root = document.getElementById("photo-drafts");
  const status = document.getElementById("photo-status");
  const categories = { photo: "照片", certificate: "證照", other: "其他", feedback: "客戶反饋" };
  const drafts = [];
  let templates = [];
  let published = [];

  function labelControl(labelText, control) {
    const label = document.createElement("label");
    label.append(labelText, control);
    return label;
  }

  function releasePreview(draft) {
    if (draft.previewUrl) URL.revokeObjectURL(draft.previewUrl);
    draft.previewUrl = "";
  }

  function render() {
    root.replaceChildren();
    for (const template of templates) {
      const groupDrafts = drafts.filter(draft => draft.template.item_id === template.item_id);
      if (!groupDrafts.length) continue;
      const group = document.createElement("section");
      const heading = document.createElement("h3");
      heading.textContent = template.name + "（" + categories[template.category] + "）";
      group.append(heading);
      groupDrafts.forEach((draft, index) => {
        const row = document.createElement("div");
        row.className = "photo-draft";
        const preview = document.createElement("img");
        draft.previewUrl ||= URL.createObjectURL(draft.file);
        preview.src = draft.previewUrl;
        preview.alt = template.name + " 照片 " + (index + 1);
        const controls = document.createElement("div");
        if (template.category === "other") {
          const date = document.createElement("input");
          date.type = "date";
          date.className = "photo-expiry";
          date.required = true;
          date.value = draft.expiry;
          date.addEventListener("input", () => { draft.expiry = date.value; });
          controls.append(labelControl("到期日", date));
        }
        const replaceable = published.filter(entry => entry.item.item_id === template.item_id);
        if (template.category === "other" && draft.replaces) {
          const replacement = document.createElement("p");
          replacement.textContent = "核准發布後會替換目前照片。";
          controls.append(replacement);
        } else if (replaceable.length) {
          const select = document.createElement("select");
          select.append(new Option("新增照片", ""));
          for (const [index, entry] of replaceable.entries()) {
            const date = entry.expiry_date ? " · 到期日 " + entry.expiry_date : "";
            select.append(new Option("替換「" + template.name + "」第 " + (index + 1) + " 張" + date, entry.entry_id));
          }
          select.value = draft.replaces ? String(draft.replaces.entry_id) : "";
          select.addEventListener("change", () => {
            draft.replaces = replaceable.find(entry => String(entry.entry_id) === select.value);
          });
          controls.append(labelControl("發布方式", select));
        }
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "photo-draft-action";
        remove.textContent = "移除這張";
        remove.setAttribute("aria-label", "移除" + preview.alt);
        remove.addEventListener("click", () => {
          drafts.splice(drafts.indexOf(draft), 1);
          releasePreview(draft);
          status.textContent = "";
          render();
        });
        controls.append(remove);
        row.append(preview, controls);
        group.append(row);
      });
      root.append(group);
    }
  }

  templateSelect.addEventListener("change", () => {
    const template = templates.find(item => String(item.item_id) === templateSelect.value);
    files.disabled = !template;
    files.multiple = template?.category !== "other";
  });
  files.addEventListener("change", () => {
    const template = templates.find(item => String(item.item_id) === templateSelect.value);
    const selected = Array.from(files.files);
    files.value = "";
    if (!template || !selected.length) return;
    if (template.category === "other" && (
      selected.length !== 1 || drafts.some(draft => draft.template.item_id === template.item_id)
    )) {
      status.textContent = "每個「其他」項目只能上傳一張照片。請先移除草稿中同項目的照片。";
      return;
    }
    if (drafts.length + selected.length > 50) {
      status.textContent = "每張申請最多 50 張照片，請減少檔案後再加入。";
      return;
    }
    if (selected.some(file => file.size <= 0 || (file.type && !SUPPORTED_PHOTO_MIMES.has(file.type.toLowerCase())))) {
      status.textContent = "只接受非空的 JPG、PNG 或 WebP 照片檔案。";
      return;
    }
    const replaces = template.category === "other"
      ? published.find(entry => entry.item.item_id === template.item_id)
      : undefined;
    for (const file of selected) {
      drafts.push({ template, file, uploadId: crypto.randomUUID(), expiry: "", previewUrl: "", replaces });
    }
    status.textContent = "";
    render();
  });

  window.addEventListener("pagehide", () => drafts.forEach(releasePreview));
  window.addEventListener("pageshow", event => { if (event.persisted) render(); });

  return {
    load(webProfile) {
      templates = webProfile?.templates ?? [];
      published = webProfile?.published ?? [];
      templateSelect.disabled = !templates.length;
      for (const item of templates) {
        templateSelect.append(new Option(item.name + "（" + categories[item.category] + "）", item.item_id));
      }
      if (!templates.length) status.textContent = "目前沒有可送審的照片項目。";
    },
    async upload(identity) {
      const replacements = drafts.flatMap(draft => draft.replaces ? [draft.replaces.entry_id] : []);
      if (new Set(replacements).size !== replacements.length) {
        throw new Error("同一張已發布照片在本次申請只能替換一次。");
      }
      const total = drafts.length;
      if (total === 0) return [];
      const contents = new Array(total);
      const workers = Math.min(MAX_CONCURRENT_PHOTO_UPLOADS, total);
      let nextIndex = 0;
      let done = 0;
      let hasError = false;
      let firstError;
      status.textContent = "正在上傳照片（0／" + total + "）…";

      async function runWorker() {
        while (!hasError) {
          const index = nextIndex;
          nextIndex += 1;
          if (index >= total) return;
          const draft = drafts[index];
          try {
            if (!draft.fileId) {
              const prepared = await optimizePhotoForUpload(draft.file);
              const body = new FormData();
              body.set("upload_id", draft.uploadId);
              body.set("photograph", prepared);
              for (const [key, value] of Object.entries(identity)) body.set(key, value);
              draft.fileId = await uploadProfilePhoto(body, draft.template.name);
            }
            contents[index] = {
              template_item_id: draft.template.item_id,
              template_version: draft.template.version,
              original_file_id: draft.fileId,
              expiry_date: draft.expiry || null,
              ...(draft.replaces ? { entry_id: draft.replaces.entry_id, entry_version: draft.replaces.version } : {}),
            };
            done += 1;
            if (!hasError) {
              status.textContent = "正在上傳照片（" + done + "／" + total + "）…";
            }
          } catch (error) {
            if (!hasError) {
              hasError = true;
              firstError = error;
            }
            return;
          }
        }
      }

      await Promise.allSettled(Array.from({ length: workers }, () => runWorker()));
      status.textContent = "";
      if (hasError) throw firstError;
      return contents;
    },
    clear() {
      drafts.forEach(releasePreview);
      drafts.length = 0;
      root.replaceChildren();
    },
  };
}

async function uploadProfilePhoto(body, itemName) {
  let response;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PHOTO_UPLOAD_TIMEOUT_MS);
  try {
    response = await fetch("/api/v1/line/staff-self-service/profile-change/photos", {
      method: "POST", cache: "no-store", body, signal: controller.signal,
    });
  } catch (error) {
    if (error && error.name === "AbortError") {
      throw new Error(itemName + "的照片上傳逾時。草稿已保留，請稍後再送出。");
    }
    throw new Error(itemName + "的照片上傳連線中斷。草稿已保留，請檢查網路後再送出。");
  } finally {
    clearTimeout(timer);
  }
  const result = await response.json().catch(() => null);
  const message = result?.detail?.error?.message;
  if (!response.ok) {
    if ([401, 403, 410].includes(response.status)) {
      throw new Error("身分驗證失效或權限已變更。請從 LINE「我的資料」重新開啟。");
    }
    if (response.status === 413) {
      throw new Error(itemName + "的照片超過上傳大小上限，請縮小後重新選擇。");
    }
    if (typeof message === "string") throw new Error(itemName + "：" + message);
    throw new Error(itemName + "的照片暫時無法上傳。草稿已保留，請稍後再送出。");
  }
  const id = result?.data?.file_id;
  if (typeof id !== "string" || !/^cf_[a-f0-9]{32}$/.test(id)) {
    throw new Error(itemName + "的照片上傳結果未確認。草稿已保留，請再送出一次。");
  }
  return id;
}
