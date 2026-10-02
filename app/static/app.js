const $ = id => document.getElementById(id);
let controller = null, polling = null;
let busy = false;
function headers() { return {"X-API-Key": $("api-key").value.trim()}; }
function toast(message = "") { $("toast").textContent = message; }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...headers(), ...(options.headers || {})}});
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { message = (await response.json()).error?.message || message; } catch {}
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}
async function refresh() {
  const selected = new Set([...document.querySelectorAll(".document input:checked")].map(x => x.value));
  try {
    const result = await api("/api/v1/documents");
    $("documents").replaceChildren();
    let pending = false;
    const statuses = {queued:"Đang chờ", processing:"Đang trích xuất", ready:"Sẵn sàng", failed:"Lỗi xử lý"};
    for (const item of result.items) {
      const box = document.createElement("div"); box.className = "document";
      const label = document.createElement("label"); label.className = "name";
      const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.value = item.id;
      checkbox.disabled = item.status !== "ready"; checkbox.checked = selected.has(item.id) && !checkbox.disabled;
      label.append(checkbox, document.createTextNode(item.name)); box.append(label);
      const state = document.createElement("small"); state.textContent = `${statuses[item.status]} · ${item.units} trang/slide`; box.append(state);
      if (item.error) { const error = document.createElement("small"); error.textContent = item.error; box.append(error); }
      if (["queued", "processing"].includes(item.status)) pending = true;
      else {
        const remove = document.createElement("button"); remove.textContent = "Xóa";
        remove.onclick = async () => { try { await api(`/api/v1/documents/${item.id}`, {method:"DELETE"}); await refresh(); } catch(e) {toast(e.message);} };
        box.append(remove);
        if (item.status === "failed") {
          const retry = document.createElement("button"); retry.textContent = "Thử lại";
          retry.onclick = async () => { try { await api(`/api/v1/documents/${item.id}/retry`, {method:"POST"}); await refresh(); } catch(e) {toast(e.message);} };
          box.append(retry);
        }
      }
      $("documents").append(box);
    }
    $("connection").textContent = `Đã kết nối · ${result.items.length} tài liệu`;
    clearTimeout(polling); if (pending) polling = setTimeout(refresh, 1000);
  } catch(e) { clearTimeout(polling); $("connection").textContent = e.message; toast(e.message); }
}
function addMessage(role, text) {
  $("intro").hidden = true;
  const box = document.createElement("section"); box.className = `message ${role}`;
  const label = document.createElement("span"); label.className = "label"; label.textContent = role === "user" ? "BẠN" : "STUDYGATEWAY";
  const content = document.createElement("div"); content.textContent = text;
  box.append(label, content); $("messages").append(box); return {box, content};
}
function displaySources(box, sources) {
  if (!sources.length) return;
  const details = document.createElement("details"); details.className = "sources";
  const summary = document.createElement("summary"); summary.textContent = `${sources.length} trích đoạn gửi đến mô hình`;
  details.append(summary);
  sources.forEach((source, i) => { const p = document.createElement("p"); p.textContent = `[${i + 1}] ${source.name} · trang/slide ${source.unit}\n${source.excerpt}`; details.append(p); });
  box.append(details);
}
function parseEvent(block) {
  let event = "message", data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? {event, data: JSON.parse(data.join("\n"))} : null;
}
$("connect").onclick = () => {toast(); refresh();};
$("refresh").onclick = refresh;
$("file").onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  toast(); const form = new FormData(); form.append("file", file);
  try {await api("/api/v1/documents", {method:"POST", body:form}); await refresh();} catch(e) {toast(e.message);}
  event.target.value = "";
};
document.querySelectorAll("[data-prompt]").forEach(button => button.onclick = () => {$("question").value = button.dataset.prompt; $("question").focus();});
$("stop").onclick = () => controller?.abort();
$("chat-form").onsubmit = async event => {
  event.preventDefault(); if (busy) return;
  const question = $("question").value.trim(); if (!question) return;
  const ids = [...document.querySelectorAll(".document input:checked")].map(x => x.value);
  if (ids.length > 5) return toast("Chọn tối đa 5 tài liệu.");
  busy = true; toast(); $("send").disabled = true; $("stop").hidden = false;
  addMessage("user", question); const message = addMessage("assistant", "");
  controller = new AbortController(); let done = false;
  try {
    const response = await fetch("/api/v1/chat/stream", {method:"POST", signal:controller.signal,
      headers:{...headers(), "Content-Type":"application/json"}, body:JSON.stringify({question, document_ids:ids, task:$("task").value})});
    if (!response.ok) throw new Error((await response.json()).error?.message || `HTTP ${response.status}`);
    const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = "";
    const consume = block => {
      const item = parseEvent(block); if (!item) return;
      if (item.event === "token") message.content.textContent += item.data.text;
      if (item.event === "meta") displaySources(message.box, item.data.sources);
      if (item.event === "done") done = true;
      if (item.event === "error") throw new Error(item.data.message);
    };
    try {
      while (true) {
        const chunk = await reader.read();
        buffer += decoder.decode(chunk.value || new Uint8Array(), {stream:!chunk.done});
        buffer = buffer.replace(/\r\n/g, "\n");
        let boundary; while ((boundary = buffer.indexOf("\n\n")) !== -1) {consume(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2);}
        if (chunk.done) break;
      }
      if (!done) throw new Error("Kết nối đóng trước khi câu trả lời hoàn tất");
    } finally { await reader.cancel(); reader.releaseLock(); }
    $("question").value = "";
  } catch(e) {
    message.content.textContent += e.name === "AbortError" ? "\n[Đã dừng]" : `\n[Lỗi] ${e.message}`;
    if (e.name !== "AbortError") toast(e.message);
  } finally {busy = false; controller = null; $("send").disabled = false; $("stop").hidden = true;}
};
fetch("/health").then(r => r.json()).then(x => {$("mode").textContent = x.provider === "demo" ? "DEMO · mô phỏng" : "LLM · tích hợp API";}).catch(() => {$("mode").textContent = "Mất kết nối";});
