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
      const contents = [];
      for (const draft of drafts) {
        if (!draft.fileId) {
          const body = new FormData();
          body.set("upload_id", draft.uploadId);
          body.set("photograph", draft.file);
          for (const [key, value] of Object.entries(identity)) body.set(key, value);
          draft.fileId = await uploadProfilePhoto(body, draft.template.name);
        }
        contents.push({
          template_item_id: draft.template.item_id,
          template_version: draft.template.version,
          original_file_id: draft.fileId,
          expiry_date: draft.expiry || null,
          ...(draft.replaces ? { entry_id: draft.replaces.entry_id, entry_version: draft.replaces.version } : {}),
        });
      }
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
  try {
    response = await fetch("/api/v1/line/staff-self-service/profile-change/photos", {
      method: "POST", cache: "no-store", body,
    });
  } catch {
    throw new Error(itemName + "的照片上傳連線中斷。草稿已保留，請檢查網路後再送出。");
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
