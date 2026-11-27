const statusMessage = document.getElementById("status");
const nameHeading = document.getElementById("staff-name");
const groupsRoot = document.getElementById("groups");
const categories = [["photo", "照片"], ["certificate", "證照"], ["other", "其他"], ["feedback", "客戶反饋"]];
let activeRequest;
let liffScript;
const imageUrls = new Set();

const photoViewer = document.getElementById("photo-viewer");
const photoPlane = document.getElementById("photo-plane");
const largePhoto = document.getElementById("photo-large");
const largerButton = document.getElementById("photo-larger");
const smallerButton = document.getElementById("photo-smaller");
const photoPointers = new Map();
const maximumPhotoScale = 4;
let photoScale = 1;
let photoX = 0;
let photoY = 0;

function paintPhoto() {
  const limitX = Math.max(0, (largePhoto.clientWidth * photoScale - photoPlane.clientWidth) / 2);
  const limitY = Math.max(0, (largePhoto.clientHeight * photoScale - photoPlane.clientHeight) / 2);
  photoX = Math.min(limitX, Math.max(-limitX, photoX));
  photoY = Math.min(limitY, Math.max(-limitY, photoY));
  largePhoto.style.transform = `translate(${photoX}px, ${photoY}px) scale(${photoScale})`;
  smallerButton.disabled = photoScale <= 1;
  largerButton.disabled = photoScale >= maximumPhotoScale;
}

function scalePhoto(nextScale, before, after) {
  const scale = Math.min(maximumPhotoScale, Math.max(1, nextScale));
  const ratio = scale / photoScale;
  photoX = after.x - (before.x - photoX) * ratio;
  photoY = after.y - (before.y - photoY) * ratio;
  photoScale = scale;
  paintPhoto();
}

function pointInPhoto(event) {
  const bounds = photoPlane.getBoundingClientRect();
  return {x: event.clientX - bounds.left - bounds.width / 2,
    y: event.clientY - bounds.top - bounds.height / 2};
}

function midpoint(first, second) {
  return {x: (first.x + second.x) / 2, y: (first.y + second.y) / 2};
}

function openLargePhoto(image) {
  if (photoViewer.open) return;
  photoPointers.clear();
  photoScale = 1;
  photoX = photoY = 0;
  largePhoto.alt = image.alt;
  largePhoto.src = image.src;
  photoViewer.showModal();
  paintPhoto();
}

document.getElementById("photo-close").addEventListener("click", () => photoViewer.close());
photoViewer.addEventListener("close", () => {
  if (photoViewer.open) return;
  largePhoto.removeAttribute("src");
  photoPointers.clear();
});
largePhoto.addEventListener("load", paintPhoto);
window.addEventListener("resize", () => { if (photoViewer.open) paintPhoto(); });
for (const [button, factor] of [[largerButton, 1.5], [smallerButton, 1 / 1.5]]) {
  button.addEventListener("click", () => {
    const center = {x: 0, y: 0};
    scalePhoto(photoScale * factor, center, center);
  });
}

photoPlane.addEventListener("pointerdown", event => {
  if (event.button !== 0 || photoPointers.size >= 2) return;
  photoPointers.set(event.pointerId, pointInPhoto(event));
  if (event.pointerType === "mouse") photoPlane.setPointerCapture(event.pointerId);
});
photoPlane.addEventListener("pointermove", event => {
  const previous = photoPointers.get(event.pointerId);
  if (!previous) return;
  const point = pointInPhoto(event);
  photoPointers.set(event.pointerId, point);
  if (photoPointers.size === 2) {
    const other = [...photoPointers.entries()].find(([id]) => id !== event.pointerId)[1];
    const before = Math.hypot(previous.x - other.x, previous.y - other.y);
    const after = Math.hypot(point.x - other.x, point.y - other.y);
    if (before > 0 && after > 0) scalePhoto(photoScale * after / before,
      midpoint(previous, other), midpoint(point, other));
  } else if (photoScale > 1) {
    photoX += point.x - previous.x;
    photoY += point.y - previous.y;
    paintPhoto();
  }
});
for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"]) {
  photoPlane.addEventListener(eventName, event => photoPointers.delete(event.pointerId));
}

function clearProfile() {
  activeRequest?.abort();
  if (photoViewer.open) photoViewer.close();
  largePhoto.removeAttribute("src");
  for (const url of imageUrls) URL.revokeObjectURL(url);
  imageUrls.clear();
  nameHeading.hidden = true;
  nameHeading.textContent = "";
  groupsRoot.replaceChildren();
}

async function readProfile(path, request, signal) {
  const response = await fetch(path, { ...request, cache: "no-store", signal });
  if (!response.ok) throw new Error(request.method === "GET"
    ? "無法開啟月嫂個人網頁，請確認後台登入及名冊權限。"
    : "無法開啟個人網頁，請從 LINE 推薦訊息重新開啟。");
  return response;
}

async function addImage(slider, item, path, request, signal) {
  const figure = document.createElement("figure");
  slider.append(figure);
  let url;
  try {
    const response = await readProfile(`${path}/images/${item.image_entry}/${item.image_version}`, request, signal);
    const blob = await response.blob();
    if (signal.aborted) return;
    const image = document.createElement("img");
    url = URL.createObjectURL(blob);
    imageUrls.add(url);
    image.src = url;
    image.alt = item.item_name;
    await image.decode();
    if (signal.aborted) return;
    const open = document.createElement("button");
    open.type = "button";
    open.className = "photo-open";
    open.setAttribute("aria-label", "放大履歷圖片");
    open.append(image);
    open.addEventListener("click", () => openLargePhoto(image));
    figure.prepend(open);
  } catch {
    if (url && imageUrls.delete(url)) URL.revokeObjectURL(url);
    if (signal.aborted) return;
    const message = document.createElement("p");
    message.className = "unavailable";
    message.textContent = "無法載入圖片";
    figure.prepend(message);
  }
}

function loadLiff() {
  if (window.liff) return Promise.resolve(window.liff);
  if (!liffScript) {
    liffScript = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://static.line-scdn.net/liff/edge/2/sdk.js";
      script.onload = () => window.liff ? resolve(window.liff) : reject(new Error("LINE 登入暫時無法使用。"));
      script.onerror = () => reject(new Error("LINE 登入暫時無法使用。"));
      document.head.append(script);
    });
  }
  return liffScript;
}

async function customerRequest(interaction, signal) {
  const config = await fetch("./api/v1/line/identity/runtime-config", { cache: "no-store", signal });
  const { data } = await config.json();
  if (!config.ok || !data?.liff_id) throw new Error("LINE 登入暫時無法使用。");
  const liff = await loadLiff();
  if (signal.aborted) return null;
  await liff.init({ liffId: data.liff_id });
  if (signal.aborted) return null;
  if (!liff.isLoggedIn()) {
    liff.login({ redirectUri: location.href });
    return null;
  }
  const token = liff.getIDToken();
  if (!token) throw new Error("無法驗證 LINE 身分，請重新開啟連結。");
  return {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ interaction_token: interaction, line_id_token: token }),
  };
}

async function openProfile() {
  clearProfile();
  const params = new URLSearchParams(location.search);
  const admin = params.get("mode") === "admin";
  statusMessage.hidden = false;
  statusMessage.textContent = admin ? "正在載入月嫂個人網頁…" : "正在確認 LINE 身分…";
  activeRequest = new AbortController();
  const { signal } = activeRequest;
  try {
    const staffId = params.get("staff_id");
    const interaction = params.get("interaction");
    if (!staffId || !/^[1-9]\d*$/.test(staffId) || (!admin && !interaction)) {
      throw new Error(admin ? "連結不完整，請從月嫂名冊重新開啟。" : "這個連結打不開。請回到工會傳給你的 LINE 訊息，再點一次月嫂連結。");
    }
    let request;
    let path;
    if (admin) {
      const token = window.sessionStorage.getItem("union_admin_session_token");
      if (!token) throw new Error("請先登入後台，再從月嫂名冊重新開啟。");
      request = { method: "GET", headers: { Authorization: `Bearer ${token}` } };
      path = `./api/v1/admin/staff-web-profile/${staffId}/website`;
    } else {
      request = await customerRequest(interaction, signal);
      path = `./api/v1/line/staff-web-profiles/${staffId}`;
    }
    if (!request || signal.aborted) return;
    const response = await readProfile(admin ? path : `${path}/query`, request, signal);
    const { data: profile } = await response.json();
    if (signal.aborted) return;
    if (!profile || typeof profile.name !== "string" || !Array.isArray(profile.groups)) {
      throw new Error("無法讀取月嫂資料。");
    }
    nameHeading.textContent = profile.name;
    nameHeading.hidden = false;
    statusMessage.hidden = true;
    for (const [category, label] of categories) {
      const group = profile.groups.find(item => item.category === category);
      if (!group?.images?.length) continue;
      const section = document.createElement("section");
      const heading = document.createElement("h2");
      heading.textContent = label;
      const slider = document.createElement("div");
      slider.className = "photos";
      slider.tabIndex = 0;
      slider.setAttribute("aria-label", label);
      section.append(heading, slider);
      groupsRoot.append(section);
      for (const item of group.images) void addImage(slider, item, path, request, signal);
    }
  } catch (error) {
    if (!signal.aborted) statusMessage.textContent = error instanceof Error && error.message !== "Failed to fetch"
      ? error.message : "無法載入個人網頁，請重新開啟。";
  }
}

window.addEventListener("pagehide", clearProfile);
window.addEventListener("pageshow", event => {
  if (event.persisted) void openProfile();
});
void openProfile();
