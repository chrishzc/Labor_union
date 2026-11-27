const statusMessage = document.getElementById("status");
const nameHeading = document.getElementById("staff-name");
const groupsRoot = document.getElementById("groups");
const categories = [["photo", "照片"], ["certificate", "證照"], ["other", "其他"], ["feedback", "客戶反饋"]];
let activeRequest;
let liffScript;
const imageUrls = new Set();

function clearProfile() {
  activeRequest?.abort();
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
  try {
    const response = await readProfile(`${path}/images/${item.image_entry}/${item.image_version}`, request, signal);
    const blob = await response.blob();
    if (signal.aborted) return;
    const image = document.createElement("img");
    const url = URL.createObjectURL(blob);
    imageUrls.add(url);
    image.src = url;
    image.alt = item.item_name;
    figure.prepend(image);
  } catch {
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
