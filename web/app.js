/* 汇诊 MedConsult 前端逻辑（无框架，原生 JS） */
"use strict";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const state = {
  datasets: [],
  dataset: null,
  caseId: null,
  mode: "mdt",           // auto | human | mdt（默认进入患者 MDT 入口）
  history: [],           // 观摩/问诊模式的对话历史
  running: false,
  finished: false,
  mdtStage: "input",     // input -> clarify -> 会诊
  mdtRole: "patient",    // patient | doctor
  mdtText: "",
  docIds: new Set(),     // 会诊引用的文档
  savedApplied: false,
  transcript: [],        // 当前会话完整留痕（用于记忆存档与回放）
};

const ROLE_LABEL = {
  doctor: "AI 医生 · Dr. Agent",
  patient: "AI 患者",
  measurement: "检查科室 Agent",
};
const ROLE_AVATAR = { doctor: "🧑‍⚕️", patient: "🧑", measurement: "🧪", human: "🩺",
  summary: "📋", specialist: "⚕️", report: "⚖️" };

const BIASES = ["recency", "frequency", "false_consensus", "confirmation", "status_quo",
  "self_diagnosis", "gender", "race", "sexual_orientation", "cultural", "education",
  "religion", "socioeconomic"];
const BIAS_ZH = {
  recency: "近因效应", frequency: "频率误判", false_consensus: "错误共识", confirmation: "确认偏误",
  status_quo: "路径依赖", self_diagnosis: "自我诊断", gender: "性别偏见", race: "种族偏见",
  sexual_orientation: "性向偏见", cultural: "文化偏见", education: "学历偏见",
  religion: "宗教偏见", socioeconomic: "阶层偏见",
};

const SPEC_META = {
  internal:   { name: "内科专家", emoji: "🫀" },
  surgery:    { name: "外科专家", emoji: "🦴" },
  pharmacy:   { name: "药学专家", emoji: "💊" },
  labimaging: { name: "影像与检验专家", emoji: "🩻" },
  neurology:  { name: "神经内科专家", emoji: "🧠" },
  cardio:     { name: "心内科专家", emoji: "❤️" },
  pediatrics: { name: "儿科专家", emoji: "🧒" },
  obgyn:      { name: "妇产科专家", emoji: "🤰" },
};
const DEFAULT_SPECS = ["internal", "surgery", "pharmacy", "labimaging"];

const TEAM_PRESETS = {
  general: ["internal", "surgery", "pharmacy", "labimaging"],
  cardio:  ["cardio", "internal", "pharmacy", "labimaging"],
  neuro:   ["neurology", "labimaging", "pharmacy", "internal"],
  resp:    ["internal", "labimaging", "pharmacy", "surgery"],
  peds:    ["pediatrics", "internal", "pharmacy", "labimaging"],
  obgyn:   ["obgyn", "internal", "pharmacy", "labimaging"],
};

/* 角色默认系统提示词（与平台后端默认一致；可在设置中覆盖） */
const ROLE_PROMPTS = {
  doctor: {
    label: "🧑‍⚕️ 医生 Agent（观摩/训练模式）",
    text: 'You are a doctor named Dr. Agent who only responds in the form of dialogue. You are inspecting a patient who you will ask questions in order to understand their disease. You are only allowed to ask {N} questions total before you must make a decision. You can request test results using the format "REQUEST TEST: [test]". Once you have decided to make a diagnosis please type "DIAGNOSIS READY: [diagnosis here]". Your dialogue will only be 1-3 sentences in length.',
  },
  patient: {
    label: "🧑 患者 Agent（训练模式）",
    text: "You are a patient in a clinic who only responds in the form of dialogue. You are being inspected by a doctor who will ask you questions and will perform exams on you in order to understand your disease. Your answer will only be 1-3 sentences in length. Remember, you must not reveal your disease explicitly but may only convey the symptoms you have in the form of dialogue.",
  },
  measurement: {
    label: "🧪 检查科 Agent",
    text: 'You are a measurement reader who responds with medical test results. Please respond in the format "RESULTS: [results here]". If the requested results are not in your data then you can respond with NORMAL READINGS.',
  },
  moderator: {
    label: "⚖️ 主持人 / 判分 Agent（含 MDT 主持）",
    text: "你是一名严谨的临床医学专家，参与多学科会诊，用中文回答。判分时只回答 Yes 或 No。汇总报告时输出结构化 JSON。",
  },
};

/* 设置本地记忆（localStorage，key 留在本机） */
const SETTINGS_KEY = "medconsult_settings_v1";

function applySavedSettings() {
  let s = null;
  try { s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || "null"); } catch (e) { s = null; }
  if (!s) return;
  state.savedApplied = true;
  const set = (id, v) => { if (v != null && v !== "" && $(id)) $(id).value = v; };
  set("runMode", s.mode);
  set("llmModel", s.model);
  set("doctorModel", s.doctor_model);
  set("patientModel", s.patient_model);
  set("measurementModel", s.measurement_model);
  set("moderatorModel", s.moderator_model);
  set("llmBase", s.base_url);
  set("llmKey", s.api_key);
  set("doctorBias", s.doctor_bias);
  set("patientBias", s.patient_bias);
  set("totalInfs", s.total_inferences);
  set("temperature", s.temperature);
  set("maxTokens", s.max_tokens);
  set("mdtRounds", s.mdt_rounds);
  set("specStyle", s.spec_style);
  set("requestTimeout", s.request_timeout);
  if (typeof s.tool_doc_search === "boolean") $("toolDocSearch").checked = s.tool_doc_search;
  if (typeof s.tool_calculator === "boolean") $("toolCalculator").checked = s.tool_calculator;
  if (typeof s.save_sessions === "boolean") $("saveSessions").checked = s.save_sessions;
  ["doctor", "patient", "measurement", "moderator"].forEach((role) => {
    if (typeof s[role + "_prompt"] === "string") {
      const ta = document.getElementById("prompt_" + role);
      if (ta) ta.value = s[role + "_prompt"];
    }
  });
  if (Array.isArray(s.mdt_specialties) && s.mdt_specialties.length) {
    document.querySelectorAll("#specBoxes input").forEach((cb) => {
      cb.checked = s.mdt_specialties.includes(cb.value);
      cb.closest("label").classList.toggle("on", cb.checked);
    });
  }
}

function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(collectSettings())); } catch (e) { /* 忽略 */ }
}

/* ---------------- 记忆：会诊记录 ---------------- */
async function loadSessions() {
  try {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    const list = $("sessList");
    const sessions = data.sessions || [];
    $("sessCount").textContent = sessions.length ? `(${sessions.length})` : "";
    list.innerHTML = "";
    if (!sessions.length) {
      list.innerHTML = `<div class="doc-empty">暂无会诊记录。每场会诊结束后自动存档于此。</div>`;
      return;
    }
    for (const s of sessions) {
      const item = document.createElement("div");
      item.className = "sess-item";
      item.innerHTML = `<div class="sess-main"><div class="sess-title">${escapeHtml(s.title)}</div>
        <div class="sess-meta">${escapeHtml(s.ts)} · ${{ mdt: "会诊工作台", human: "问诊训练台", auto: "演示观摩台" }[s.mode] || s.mode}</div></div>
        <button class="doc-del" title="删除">✕</button>`;
      item.querySelector(".sess-main").onclick = () => replaySession(s.id);
      item.querySelector(".doc-del").onclick = async (e) => {
        e.stopPropagation();
        await fetch("/api/sessions/delete", { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: s.id }) });
        loadSessions();
      };
      list.appendChild(item);
    }
  } catch (e) { /* 静默 */ }
}

async function replaySession(id) {
  try {
    const res = await fetch("/api/sessions?id=" + encodeURIComponent(id));
    const data = await res.json();
    const s = data.session;
    if (!s) return;
    if (state.finished) resetConsultation();
    $("emptyHint") && $("emptyHint").remove();
    $("chat").innerHTML = "";
    addSystem(`正在回放会诊记录：${s.title}（${s.ts}）· 只读回放，点「重置」返回`);
    for (const it of (s.items || [])) {
      if (it.role === "report" && s.report) { renderReport(s.report); continue; }
      renderMdtEvent(it);
    }
  } catch (e) {
    addSystem("⚠ 回放失败：" + e.message);
  }
}

async function autoSaveSession() {
  if (!$("saveSessions").checked || !state.transcript.length) return;
  try {
    const base = state.caseId != null
      ? (document.getElementById("caseTitle")?.textContent || "病例会诊")
      : ($("humanInput").value.trim().slice(0, 18) || "症状会诊");
    await fetch("/api/sessions/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: state.mode, title: base,
                             items: state.transcript,
                             report: (state.transcript.find(t => t.role === "report") || {}).text || null }),
    });
    loadSessions();
  } catch (e) { /* 存档失败不打扰会诊 */ }
}

/* ---------------- 提示词池 ---------------- */
async function loadPromptPool() {
  try {
    const res = await fetch("/api/prompts");
    const data = await res.json();
    const pool = data.pool || {};
    window.__promptPool = pool;
    for (const role of Object.keys(ROLE_PROMPTS)) {
      const sel = document.getElementById("preset_" + role);
      if (!sel) continue;
      const names = Object.keys(pool[role] || {});
      const cur = sel.value;
      sel.innerHTML = `<option value="">提示词池（${names.length}）</option>` +
        names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
      if (cur) sel.value = cur;
      sel.dataset.role = role;
    }
  } catch (e) { /* 静默 */ }
}

async function savePromptPreset(role) {
  const text = $("prompt_" + role).value.trim();
  if (!text) { alert("提示词为空，无法保存。"); return; }
  const name = window.prompt("预设名称：", role + "_预设");
  if (!name) return;
  await fetch("/api/prompts/save", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, name, text }) });
  loadPromptPool();
}

async function deletePromptPreset(role, name) {
  if (!name) return;
  await fetch("/api/prompts/delete", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, name }) });
  loadPromptPool();
}

/* ---------------- 我的文档库 ---------------- */
async function loadDocs() {
  try {
    const res = await fetch("/api/library");
    const data = await res.json();
    renderDocList(data.docs || []);
  } catch (e) { /* 服务未启动时静默 */ }
}

function renderDocList(docs) {
  const list = $("docList");
  list.innerHTML = "";
  $("docCount").textContent = docs.length ? `(${docs.length})` : "";
  if (!docs.length) {
    list.innerHTML = `<div class="doc-empty">还没有文档。点「＋ 上传文档」导入病历、检查报告、<br>诊疗指南等（支持 txt / md / pdf / docx）。</div>`;
    return;
  }
  for (const d of docs) {
    const row = document.createElement("div");
    row.className = "doc-item" + (state.docIds.has(d.id) ? " selected" : "");
    row.innerHTML = `
      <input type="checkbox" ${state.docIds.has(d.id) ? "checked" : ""} title="勾选后在会诊中引用">
      <span class="dn" title="${escapeHtml(d.preview)}">${escapeHtml(d.name)}</span>
      <span class="ds">${(d.size / 1024).toFixed(1)}K</span>
      <button class="doc-del" title="删除">✕</button>`;
    row.querySelector("input").onchange = (e) => {
      if (e.target.checked) state.docIds.add(d.id); else state.docIds.delete(d.id);
      row.classList.toggle("selected", e.target.checked);
      updateCiteNote();
    };
    row.querySelector(".doc-del").onclick = async (e) => {
      e.stopPropagation();
      await fetch("/api/library/delete", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: d.name }),
      });
      state.docIds.delete(d.id);
      loadDocs();
    };
    list.appendChild(row);
  }
}

function updateCiteNote() {
  if (state.mode === "mdt" && state.docIds.size) {
    addSystemOnce(`已勾选 ${state.docIds.size} 份文档，将在会诊中作为参考资料。`);
  }
}

let _lastCiteNote = "";
function addSystemOnce(text) {
  if (_lastCiteNote === text) return;
  _lastCiteNote = text;
  addSystem(text);
}

async function uploadFiles() {
  const files = [...$("fileInput").files];
  if (!files.length) return;
  for (const f of files) {
    try {
      const res = await fetch("/api/library/upload?name=" + encodeURIComponent(f.name), {
        method: "POST", body: f,
      });
      const d = await res.json();
      if (d.error) addSystem("⚠ " + f.name + "：" + d.error);
    } catch (e) {
      addSystem("⚠ 上传失败：" + f.name);
    }
  }
  $("fileInput").value = "";
  addSystem("文档已入库（保存在本地 library/documents/）。勾选即可在会诊中引用。");
  loadDocs();
}

async function pasteTextDoc() {
  const name = window.prompt("文档名称（如：张三_门诊病历_2026-08-29）：", "粘贴文档.txt");
  if (name === null) return;
  const content = window.prompt("粘贴文档内容：", "");
  if (!content || !content.trim()) return;
  await fetch("/api/library/text", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name || "粘贴文档.txt", content }),
  });
  addSystem("文档已入库。勾选即可在会诊中引用。");
  loadDocs();
}

async function loadServerDefaults() {
  try {
    const d = await (await fetch("/api/defaults")).json();
    if (d.has_key) {
      if (!state.savedApplied) {
        $("runMode").value = "llm";
        // HTML 里的占位默认值（gpt-4o-mini）要让位给服务端配置
        if (d.base_url) $("llmBase").value = d.base_url;
        if (d.model) $("llmModel").value = d.model;
      } else {
        if (!$("llmBase").value && d.base_url) $("llmBase").value = d.base_url;
        if (!$("llmModel").value && d.model) $("llmModel").value = d.model;
      }
      $("llmKey").placeholder = "已配置服务端默认 Key（留空即可）";
      refreshRunBadge();
    }
  } catch (e) { /* ignore */ }
}

/* ---------------- 初始化 ---------------- */
async function init() {
  try {
    fillBiasSelects();
    buildSpecBoxes();
    buildPromptEditors();
    applySavedSettings();
    bindEvents();
    loadDocs();
    loadSessions();
    loadPromptPool();
    loadServerDefaults();
    const res = await fetch("/api/datasets");
    const data = await res.json();
    state.datasets = data.datasets;
    renderDatasetTabs();
    selectDataset(state.datasets[0].name);
    resetConsultation();
  } catch (e) {
    addSystem("⚠ 初始化失败：" + e.message + "（请确认服务已启动）");
  }
  refreshRunBadge();
}

function fillBiasSelects() {
  for (const selId of ["doctorBias", "patientBias"]) {
    const sel = $(selId);
    for (const b of BIASES) {
      const opt = document.createElement("option");
      opt.value = b;
      opt.textContent = `${BIAS_ZH[b] || b} (${b})`;
      sel.appendChild(opt);
    }
  }
}

function buildSpecBoxes() {
  const box = $("specBoxes");
  if (!box) return;
  box.innerHTML = "";
  for (const [key, meta] of Object.entries(SPEC_META)) {
    const label = document.createElement("label");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = key;
    cb.checked = DEFAULT_SPECS.includes(key);
    cb.onchange = () => label.classList.toggle("on", cb.checked);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(meta.emoji + " " + meta.name));
    label.classList.toggle("on", cb.checked);
    box.appendChild(label);
  }
}

function selectedSpecs() {
  return [...document.querySelectorAll("#specBoxes input:checked")].map((cb) => cb.value);
}

function buildPromptEditors() {
  const box = $("promptEditors");
  if (!box) return;
  box.innerHTML = "";
  for (const [role, meta] of Object.entries(ROLE_PROMPTS)) {
    const wrap = document.createElement("div");
    wrap.className = "prompt-editor";
    wrap.innerHTML = `
      <div class="pe-head">
        <span>${meta.label}</span>
        <span class="pe-btns">
          <button type="button" class="pe-btn" data-pe-fill="${role}">填入默认</button>
          <button type="button" class="pe-btn" data-pe-clear="${role}">清空</button>
        </span>
      </div>
      <textarea id="prompt_${role}" class="inp pe-text" rows="3"
        placeholder="留空使用平台默认提示词；可自定义角色设定、输出要求、语气等"></textarea>
      <div class="pe-foot">
        <select id="preset_${role}" class="pe-select"></select>
        <button type="button" class="pe-btn" data-pe-save="${role}">💾 存为预设</button>
      </div>`;
    box.appendChild(wrap);
  }
  box.querySelectorAll("[data-pe-fill]").forEach((b) => {
    b.onclick = () => { $("prompt_" + b.dataset.peFill).value = ROLE_PROMPTS[b.dataset.peFill].text; };
  });
  box.querySelectorAll("[data-pe-clear]").forEach((b) => {
    b.onclick = () => { $("prompt_" + b.dataset.peClear).value = ""; };
  });
  box.querySelectorAll("[data-pe-save]").forEach((b) => {
    b.onclick = () => savePromptPreset(b.dataset.peSave);
  });
  box.querySelectorAll(".pe-select").forEach((sel) => {
    sel.onchange = () => {
      const role = sel.id.replace("preset_", "");
      if (sel.value) {
        const t = window.__promptPool?.[role]?.[sel.value];
        if (t) $("prompt_" + role).value = t;
      }
    };
  });
}

function bindEvents() {
  $("modeAuto").onclick = () => switchMode("auto");
  $("modeHuman").onclick = () => switchMode("human");
  $("modeMdt").onclick = () => switchMode("mdt");
  $("btnStart").onclick = startConsultation;
  $("btnReset").onclick = resetConsultation;
  $("btnStop").onclick = () => { state.running = false; addSystem("已请求停止。"); };
  $("btnSend").onclick = sendHuman;
  $("humanInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!$("btnSend").disabled) sendHuman(); }
  });
  $("humanInput").addEventListener("input", autoGrow);
  $("tipFillCase").onclick = fillFromCase;
  $("tipIntake").onclick = () => $("intakeModal").classList.remove("hidden");
  $("btnCloseIntake").onclick = () => $("intakeModal").classList.add("hidden");
  $("btnGenIntake").onclick = genIntake;
  document.querySelectorAll("#mdtRoleToggle button").forEach((b) => {
    b.onclick = () => {
      state.mdtRole = b.dataset.role;
      document.querySelectorAll("#mdtRoleToggle button").forEach((x) => x.classList.toggle("on", x === b));
      setMode("mdt");
    };
  });
  $("tipSkip").onclick = () => {
    if (state.mdtStage !== "clarify" || state.running) return;
    addSystem("已跳过追问，按现有信息直接会诊。");
    const t = state.mdtText;
    state.mdtStage = "input";
    $("tipSkip").style.display = "none";
    submitMdt(t);
  };
  $("btnUpload").onclick = () => $("fileInput").click();
  $("fileInput").addEventListener("change", uploadFiles);
  $("btnPasteText").onclick = pasteTextDoc;
  $("btnSessClear").onclick = async () => {
    if (!window.confirm("确定清空全部会诊记录？")) return;
    await fetch("/api/sessions/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    loadSessions();
  };
  $("caseSearch").addEventListener("input", filterCases);
  $("teamPreset").onchange = applyTeamPreset;
  document.querySelectorAll(".splash-card").forEach((card) => {
    card.onclick = () => enterWorkspace(card.dataset.mode);
  });
  $("btnSettings").onclick = () => $("settingsModal").classList.remove("hidden");
  $("btnCloseSettings").onclick = closeSettings;
  $("btnSaveSettings").onclick = closeSettings;
  $("settingsModal").addEventListener("click", (e) => {
    if (e.target === $("settingsModal")) closeSettings();
  });
  $("runMode").onchange = refreshRunBadge;
  $("llmModel").oninput = refreshRunBadge;
  $("btnTest").onclick = testConnection;
  document.querySelectorAll(".tip[data-fill]").forEach((btn) => {
    btn.onclick = () => { $("humanInput").value = btn.dataset.fill; $("humanInput").focus(); autoGrow(); };
  });
  $("chat").addEventListener("click", (e) => {
    const st = e.target.closest(".starter");
    if (!st) return;
    const act = st.dataset.act;
    if (act === "auto") {
      if (state.caseId == null) { const first = document.querySelector(".case-item"); if (first) first.click(); }
      setMode("auto");
      startConsultation();
    } else if (act === "mdt") {
      setMode("mdt");
      addSystem("已在输入框放入一份示例病情，可直接「发起 MDT 会诊」，也可以改成你自己的病情描述。");
      fillFromCase();
    } else if (act === "intake") {
      setMode("mdt");
      $("intakeModal").classList.remove("hidden");
    } else if (act === "cfg") {
      $("settingsModal").classList.remove("hidden");
    }
  });
  $("chat").addEventListener("click", (e) => {
    const cp = e.target.closest(".copy-btn");
    if (cp && cp.dataset.text) {
      navigator.clipboard.writeText(cp.dataset.text).then(() => {
        cp.textContent = "已复制 ✓";
        setTimeout(() => { cp.textContent = "复制"; }, 1200);
      });
    }
  });
}

function autoGrow() {
  const t = $("humanInput");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 150) + "px";
}

function closeSettings() {
  saveSettings();
  $("settingsModal").classList.add("hidden");
  refreshRunBadge();
}

function refreshRunBadge() {
  const badge = $("runBadge");
  const llm = $("runMode").value === "llm";
  badge.textContent = llm ? `真实模型 · ${$("llmModel").value.trim() || "gpt-4o-mini"}` : "模拟演示";
  badge.className = "run-badge " + (llm ? "llm" : "mock");
  document.querySelectorAll(".set-group").forEach((g) => {
    if (g.querySelector(".llm-only")) g.classList.toggle("llm-off", !llm);
  });
}

async function testConnection() {
  const out = $("testResult");
  out.textContent = "测试中…";
  out.className = "test-result";
  try {
    const res = await fetch("/api/test_llm", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectSettings()),
    });
    const data = await res.json();
    if (data.ok) { out.textContent = "✅ 连接成功：" + (data.reply || "").slice(0, 40); out.className = "test-result ok"; }
    else { out.textContent = "❌ " + (data.error || "失败").slice(0, 120); out.className = "test-result bad"; }
  } catch (e) {
    out.textContent = "❌ " + e.message; out.className = "test-result bad";
  }
}

/* ---------------- 侧栏 ---------------- */
function renderDatasetTabs() {
  const box = $("datasetTabs");
  box.innerHTML = "";
  for (const ds of state.datasets) {
    const b = document.createElement("button");
    b.textContent = ds.zh_name || ds.name;
    b.title = ds.name + " · " + ds.count + " 个病例";
    b.onclick = () => selectDataset(ds.name);
    box.appendChild(b);
  }
}

function selectDataset(name) {
  state.dataset = name;
  state.caseId = null;
  document.querySelectorAll("#datasetTabs button").forEach((b, i) => {
    b.classList.toggle("active", state.datasets[i].name === name);
  });
  const ds = state.datasets.find((d) => d.name === name);
  $("caseCount").textContent = `(${ds.count})`;
  const list = $("caseList");
  list.innerHTML = "";
  ds.cases.forEach((c) => {
    const item = document.createElement("div");
    item.className = "case-item";
    item.innerHTML = `<div class="demo">${escapeHtml(c.demographics || "患者 #" + (c.id + 1))}</div>
                      <div class="sum">${escapeHtml(c.summary || "")}</div>`;
    item.onclick = () => selectCase(c.id, item);
    list.appendChild(item);
  });
}

function selectCase(id, el) {
  state.caseId = id;
  document.querySelectorAll(".case-item").forEach((n) => n.classList.remove("active"));
  el.classList.add("active");
  const ds = state.datasets.find((d) => d.name === state.dataset);
  const c = ds.cases.find((x) => x.id === id);
  $("caseTitle").textContent = `${c.demographics || "患者 #" + (c.id + 1)} · 病例 #${c.id + 1} · ${ds.zh_name || ds.name}`;
  $("caseObjective").textContent = c.objective || "";
  resetConsultation();
}

/* 启动过渡页 -> 进入工作台 */
function enterWorkspace(mode) {
  const splash = document.getElementById("splash");
  if (splash) {
    splash.classList.add("splash-out");
    setTimeout(() => splash.remove(), 450);
  }
  switchMode(mode);
}

/* 病例库搜索过滤 */
function filterCases() {
  const q = $("caseSearch").value.trim().toLowerCase();
  document.querySelectorAll(".case-item").forEach((item) => {
    item.style.display = !q || item.textContent.toLowerCase().includes(q) ? "" : "none";
  });
}

/* 专科团队预设 */
function applyTeamPreset() {
  const key = $("teamPreset").value;
  if (!key || !TEAM_PRESETS[key]) return;
  const wanted = TEAM_PRESETS[key];
  document.querySelectorAll("#specBoxes input").forEach((cb) => {
    cb.checked = wanted.includes(cb.value);
    cb.closest("label").classList.toggle("on", cb.checked);
  });
}

/* ---------------- 模式 ---------------- */
/* 切换模式：若上一场已结束，自动重置再切换，避免按钮卡在禁用态 */
function switchMode(m) {
  if (state.finished) resetConsultation();
  setMode(m);
}

function setMode(m) {
  state.mode = m;
  $("modeAuto").classList.toggle("active", m === "auto");
  $("modeHuman").classList.toggle("active", m === "human");
  $("modeMdt").classList.toggle("active", m === "mdt");
  const human = m === "human";
  const mdt = m === "mdt";
  const canType = (human || mdt) && !state.finished && !state.running;
  $("humanInput").disabled = !canType;
  $("btnSend").disabled = !canType;
  document.querySelectorAll(".tip[data-fill]").forEach((b) => {
    b.style.display = human ? "inline-block" : "none";
  });
  $("tipFillCase").style.display = mdt ? "inline-block" : "none";
  $("tipIntake").style.display = (mdt && state.mdtRole === "patient") ? "inline-block" : "none";
  $("mdtRoleToggle").style.display = mdt ? "inline-flex" : "none";
  $("tipSkip").style.display = "none";
  $("humanInput").placeholder = mdt
    ? (state.mdtRole === "doctor"
        ? "粘贴脱敏病历 / 检查报告…（会诊团将以医生视角给出会诊参考）"
        : "描述您的症状 / 粘贴检查报告…（可点上方「填写问诊单」更规范）")
    : "以医生身份向患者提问…（Enter 发送）";
  $("composerNote").textContent = mdt
    ? (state.mdtRole === "doctor"
        ? "医生会诊参考：粘贴脱敏病历 → 专科会诊团独立意见与讨论 → 会诊参考报告（可复制入病历）。"
        : "会诊流程：提交病情 → 会诊助理整理摘要与追问 → 各专科独立意见 → 交叉讨论 → 会诊参考报告。")
    : human
      ? "问诊训练：与 AI 患者对话练习问诊；支持 REQUEST TEST 开检查 / DIAGNOSIS READY 提交诊断，结束后自动判分。"
      : "演示观摩台自动完成整场会诊，无需输入。";
  $("btnStart").textContent = mdt ? "👥 发起会诊" : human ? "▶ 开始接诊训练" : "▶ 开始演示";
  const startable = mdt ? true : state.caseId != null;  // caseId 可能为 0，不能用真值判断
  $("btnStart").disabled = !startable || state.running || state.finished;
}

function fillFromCase() {
  if (state.caseId == null) { addSystem("⚠ 请先在左侧选择一位病例库患者作为示例来源。"); return; }
  const ds = state.datasets.find((d) => d.name === state.dataset);
  const c = ds.cases.find((x) => x.id === state.caseId);
  $("humanInput").value = `${c.demographics || ""}，${c.summary || ""}。就诊目的：${c.objective || ""}`;
  autoGrow();
  $("humanInput").focus();
}

/* 结构化问诊单 -> 生成病情描述 */
function genIntake() {
  const g = (id) => $(id).value.trim();
  const symptom = g("inSymptom");
  if (!symptom) { addSystem("⚠ 请至少填写「主要症状」。"); $("inSymptom").focus(); return; }
  const parts = [];
  const who = [g("inAge") && g("inAge") + "岁", g("inSex") && g("inSex") + "性"].filter(Boolean).join("");
  parts.push(who ? `患者${who}，` : "");
  parts.push(`主要症状：${symptom}。`);
  if (g("inDuration")) parts.push(`症状持续${g("inDuration")}。`);
  if (g("inFactor")) parts.push(`加重/缓解因素：${g("inFactor")}。`);
  if (g("inHistory")) parts.push(`既往史：${g("inHistory")}。`);
  if (g("inMeds")) parts.push(`当前用药/过敏史：${g("inMeds")}。`);
  $("humanInput").value = parts.join("");
  $("intakeModal").classList.add("hidden");
  autoGrow();
  $("humanInput").focus();
  addSystem("问诊单已生成，可直接「发起 MDT 会诊」，也可继续补充描述。");
}

/* ---------------- 会话控制 ---------------- */
function resetConsultation() {
  state.history = [];
  state.transcript = [];
  state.running = false;
  state.finished = false;
  state.mdtStage = "input";
  state.mdtText = "";
  $("chat").innerHTML = "";
  $("progress").textContent = "";
  $("btnStop").style.display = "none";
  if (state.caseId == null) {
    $("chat").innerHTML = `
      <div class="empty-hint">
        <div class="empty-icon">🫶</div>
        <h2>AI 专家团，为您会诊</h2>
        <p>描述您的症状，AI 专家团将进行多学科会诊，给出结构化诊疗建议报告。<br>
        <span class="dim">建议先填写问诊单；平台输出仅供健康参考，不构成医疗建议。</span></p>
        <div class="starters">
          <button class="starter" data-act="intake">🫶 填写问诊单开始会诊</button>
          <button class="starter" data-act="auto">🤖 观摩一场 AI 会诊</button>
          <button class="starter" data-act="cfg">⚙️ 配置真实大模型</button>
        </div>
      </div>`;
  }
  setMode(state.mode);
}

async function startConsultation() {
  if (state.running || state.finished) return;
  if (state.mode === "mdt") return submitMdt();
  if (state.caseId == null) return;
  state.history = [];
  state.running = true;
  state.finished = false;
  $("btnStart").disabled = true;
  $("btnStop").style.display = "inline-block";
  addSystem(`会诊开始 · ${state.mode === "auto" ? "观摩模式（AI 医生主诊）" : "问诊模式（由你主诊）"} · ${$("runBadge").textContent}`);
  if (state.mode === "auto") {
    await autoLoop();
    state.running = false;
    $("btnStop").style.display = "none";
  } else {
    state.running = false;
    $("btnStop").style.display = "none";
    setMode("human");
    $("humanInput").focus();
    addSystem("请你以医生身份问诊；可直接输入问题，或使用下方协议按钮开检查 / 提交诊断。");
  }
}

/* ---------------- 自动模式 ---------------- */
async function autoLoop() {
  while (state.running && !state.finished) {
    const typing = addTyping("🧠", "智能体思考中…");
    const ev = await step("step");
    typing.remove();
    if (!ev) break;
    renderEvent(ev);
    if (ev.type === "verdict" || ev.type === "done") {
      state.finished = true;
      if (ev.type === "done") addSystem("已达最大轮数，会诊结束。");
      break;
    }
    await sleep(700);
  }
  $("btnStop").style.display = "none";
}

/* ---------------- 人工模式 ---------------- */
async function sendHuman() {
  if (state.mode === "mdt") {
    const text = $("humanInput").value.trim();
    if (!text) { addSystem("⚠ 请先描述病情。"); $("humanInput").focus(); return; }
    return runMdt(text);
  }
  const input = $("humanInput");
  const q = input.value.trim();
  if (!q || state.finished) return;
  input.value = "";
  autoGrow();
  renderEvent({ type: "doctor", role: "doctor", text: q, human: true });
  const typing = addTyping("🧠", "患者思考中…");
  const ev = await step("ask", q);
  typing.remove();
  if (!ev) return;
  renderEvent(ev);
  if (ev.type === "verdict") { state.finished = true; setMode("human"); }
}

/* ---------------- MDT 会诊（含预问诊追问） ---------------- */
function renderUserMsg(text, label) {
  const chat = $("chat");
  const row = document.createElement("div");
  row.className = "msg human";
  row.innerHTML = `<div class="avatar">🙋</div><div class="msg-body">
    <div class="msg-name">${escapeHtml(label || (state.mdtRole === "doctor" ? "我（医生）" : "我（患者）"))}</div>
    <div class="bubble">${escapeHtml(text)}</div></div>`;
  chat.appendChild(row);
  scrollBottom();
}

function renderAssistantMsg(text) {
  const chat = $("chat");
  const row = document.createElement("div");
  row.className = "msg summary";
  row.innerHTML = `<div class="avatar">📋</div><div class="msg-body">
    <div class="msg-name">会诊助理</div>
    <div class="bubble">${escapeHtml(text)}</div></div>`;
  chat.appendChild(row);
  scrollBottom();
}

async function submitMdt(answerText) {
  const input = $("humanInput");
  const text = (answerText !== undefined ? answerText : input.value).trim();
  if (state.mdtStage === "clarify" && !text) {
    addSystem("⚠ 请先回答上方问题，或点「跳过追问」。"); input.focus(); return;
  }
  if (state.mdtStage === "input" && !text) {
    addSystem("⚠ 请先描述病情（可点上方「填写问诊单」）。"); input.focus(); return;
  }
  if (state.running) return;
  const empty = document.querySelector(".empty-hint");
  if (empty) empty.remove();
  state.history = [];
  state.running = true;
  state.finished = false;
  $("btnStart").disabled = true;
  $("btnSend").disabled = true;
  input.disabled = true;
  $("btnStop").style.display = "inline-block";
  const typing = addTyping("📋", state.mdtStage === "clarify" ? "专家组会诊中（真实模型约 1-2 分钟）…" : "会诊助理分析中…");
  try {
    if (state.mdtStage === "input") {
      renderUserMsg(text);
      state.mdtText = text;
      const res = await fetch("/api/mdt/clarify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, settings: collectSettings() }),
      });
      const data = await res.json();
      typing.remove();
      if (data.error) { addSystem("⚠ " + data.error); }
      else if (data.questions && data.questions.length) {
        renderAssistantMsg("为了给出更准确的会诊意见，请先补充几个关键信息：\n" +
          data.questions.map((q, i) => `${i + 1}. ${q}`).join("\n"));
        state.mdtStage = "clarify";
        $("btnStart").textContent = "回答完毕，继续会诊 →";
        $("composerNote").textContent = "预问诊追问：请回答上方问题（可一并补充其他情况）；不想回答可点「跳过追问」。";
        $("tipSkip").style.display = "inline-block";
        $("humanInput").placeholder = "回答上述问题…（Enter 发送）";
        state.running = false;
        input.disabled = false; $("btnSend").disabled = false; $("btnStart").disabled = false;
        $("btnStop").style.display = "none";
        input.focus();
        scrollBottom();
        return;
      } else {
        await doMdt(text);
      }
    } else {
      renderUserMsg(text);
      typing.remove();
      await doMdt(state.mdtText + "\n\n【补充回答】" + text);
    }
  } catch (e) {
    typing.remove();
    addSystem("⚠ 网络错误：" + e.message);
  }
  state.running = false;
  $("btnStop").style.display = "none";
  state.mdtStage = "input";
  state.mdtText = "";
  setMode("mdt");
  input.disabled = false; $("btnSend").disabled = false; $("btnStart").disabled = false;
}

async function doMdt(text) {
  addSystem(`正式会诊开始 · ${selectedSpecs().length} 个专科 · ${$("runBadge").textContent}`);
  const typing = addTyping("👥", "专家组会诊中（真实模型可能需要 1-2 分钟）…");
  try {
    const res = await fetch("/api/mdt", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        settings: collectSettings(),
        dataset: state.caseId != null ? state.dataset : null,
        case_id: state.caseId,
        doc_ids: [...state.docIds],
      }),
    });
    const data = await res.json();
    typing.remove();
    if (data.error) {
      addSystem("⚠ " + data.error);
    } else {
      for (const ev of data.events) {
        if (!state.running) break;
        renderMdtEvent(ev);
        await sleep(450);
      }
      state.finished = true;
    }
  } catch (e) {
    typing.remove();
    addSystem("⚠ 网络错误：" + e.message);
  }
  state.running = false;
  $("btnStop").style.display = "none";
  setMode("mdt");
}

function renderMdtEvent(ev) {
  if (ev.role === "report") return renderReport(ev.report);
  state.transcript.push({ role: ev.role, name: ev.name, emoji: ev.emoji, round: ev.round, text: ev.text });
  const chat = $("chat");
  const row = document.createElement("div");
  row.className = "msg " + (ev.role === "summary" ? "summary" : ev.role === "tool" ? "tool" : "specialist");
  const av = document.createElement("div");
  av.className = "avatar";
  av.textContent = ev.emoji || ROLE_AVATAR[ev.role] || "•";
  const body = document.createElement("div");
  body.className = "msg-body";
  const name = document.createElement("div");
  name.className = "msg-name";
  name.innerHTML = escapeHtml(ev.name || "") +
    (ev.round > 0 ? ` <span class="round-tag">第 ${ev.round} 轮${ev.round === 1 ? "意见" : "讨论"}</span>` : "");
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = escapeHtml(ev.text || "");
  body.appendChild(name);
  body.appendChild(bubble);
  row.appendChild(av);
  row.appendChild(body);
  chat.appendChild(row);
  scrollBottom();
}

function renderReport(r) {
  state.finished = true;
  state.transcript.push({ role: "report", name: "主持人 Agent", emoji: "⚖️", text: JSON.stringify(r) });
  const chat = $("chat");
  const card = document.createElement("div");
  card.className = "report-card";
  const md = [
    "# 会诊参考报告（MDT）",
    "- 倾向判断（供参考）：" + (r.final_diagnosis || ""),
    "- 置信度：" + (r.confidence || ""),
    "- 建议就诊科室：" + (r.recommended_dept || ""),
    "- 主要依据：" + (r.key_findings || []).join("；"),
    "- 方案建议：" + (r.plan || []).join("；"),
    "- 紧急警示：" + (r.red_flags || []).join("；"),
    "- 工具计算：" + (r.calculations || []).join("；"),
    "- 分歧说明：" + (r.disagreements || "无"),
    "- 注意事项：" + (r.warnings || ""),
  ].join("\n");
  const lis = (arr) => (arr || []).map((x) => `<li>${escapeHtml(String(x))}</li>`).join("");
  card.innerHTML = `
    <div class="report-head">
      <h3>⚖️ 会诊参考报告（多学科）</h3>
      <button class="copy-btn" data-text="${escapeHtml(md)}">复制</button>
    </div>
    <div class="report-grid">
      <div class="report-item"><span>倾向判断（供参考）</span><b>${escapeHtml(r.final_diagnosis || "")}</b></div>
      <div class="report-item"><span>置信度</span><b>${escapeHtml(r.confidence || "")}</b></div>
      <div class="report-item"><span>建议就诊科室</span><b>${escapeHtml(r.recommended_dept || "内科门诊")}</b></div>
    </div>
    ${r.key_findings && r.key_findings.length ? `<h4>主要依据</h4><ul>${lis(r.key_findings)}</ul>` : ""}
    ${r.plan && r.plan.length ? `<h4>方案建议</h4><ul>${lis(r.plan)}</ul>` : ""}
    ${r.calculations && r.calculations.length ? `<h4>🧮 工具计算</h4><ul>${lis(r.calculations)}</ul>` : ""}
    <div class="report-item"><span>分歧说明</span>${escapeHtml(r.disagreements || "无")}</div>
    ${r.red_flags && r.red_flags.length ? `<div class="report-danger">🚨 <b>紧急警示</b>：${escapeHtml(r.red_flags.join("；"))}</div>` : ""}
    <div class="report-warn">⚠ ${escapeHtml(r.warnings || "本报告仅供研究演示，不构成医疗建议。")}</div>`;
  chat.appendChild(card);
  addSystem("MDT 会诊结束 · 会诊参考报告已生成");
  $("progress").textContent = "MDT 会诊已结束";
  scrollBottom();
  autoSaveSession();
}

/* ---------------- API ---------------- */
async function step(endpoint, question) {
  try {
    const body = {
      dataset: state.dataset,
      case_id: state.caseId,
      history: state.history,
      settings: collectSettings(),
    };
    if (endpoint === "ask") body.question = question;
    const res = await fetch("/api/" + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (data.error) { addSystem("⚠ " + data.error); return null; }
    return data.event;
  } catch (e) {
    addSystem("⚠ 网络错误：" + e.message);
    return null;
  }
}

function collectSettings() {
  return {
    mode: $("runMode").value,
    model: $("llmModel").value.trim(),
    doctor_model: $("doctorModel").value.trim(),
    patient_model: $("patientModel").value.trim(),
    measurement_model: $("measurementModel").value.trim(),
    moderator_model: $("moderatorModel").value.trim(),
    base_url: $("llmBase").value.trim(),
    api_key: $("llmKey").value.trim(),
    doctor_bias: $("doctorBias").value || null,
    patient_bias: $("patientBias").value || null,
    total_inferences: parseInt($("totalInfs").value, 10) || 10,
    temperature: parseFloat($("temperature").value) || 0.05,
    max_tokens: parseInt($("maxTokens").value, 10) || 400,
    mdt_specialties: selectedSpecs(),
    mdt_rounds: parseInt($("mdtRounds").value, 10) || 2,
    spec_style: $("specStyle").value || "brief",
    doctor_prompt: $("prompt_doctor").value.trim(),
    patient_prompt: $("prompt_patient").value.trim(),
    measurement_prompt: $("prompt_measurement").value.trim(),
    moderator_prompt: $("prompt_moderator").value.trim(),
    tool_doc_search: $("toolDocSearch").checked,
    tool_calculator: $("toolCalculator").checked,
    save_sessions: $("saveSessions").checked,
    request_timeout: parseFloat($("requestTimeout").value) || 120,
  };
}

/* ---------------- 渲染 ---------------- */
function renderEvent(ev) {
  if (ev.type === "verdict") return renderVerdict(ev);
  if (!ev.text) return;
  state.history.push({ role: ev.role, text: ev.text });
  state.transcript.push({ role: ev.role, name: ev.human ? "我（医生）" : (ROLE_LABEL[ev.role] || ev.role),
                          emoji: ROLE_AVATAR[ev.role] || "•", text: ev.text });
  renderBubble(ev);
  if (ev.turn) $("progress").textContent = `第 ${ev.turn} / ${ev.total} 轮`;
  scrollBottom();
}

function renderBubble(ev) {
  const chat = $("chat");
  const row = document.createElement("div");
  row.className = "msg " + (ev.human ? "human doctor" : ev.role);

  const av = document.createElement("div");
  av.className = "avatar";
  av.textContent = ev.human ? ROLE_AVATAR.human : (ROLE_AVATAR[ev.role] || "•");

  const body = document.createElement("div");
  body.className = "msg-body";
  const label = ev.human ? "你（医生）" : ROLE_LABEL[ev.role] || ev.role;
  const name = document.createElement("div");
  name.className = "msg-name";
  name.textContent = label;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  let text = escapeHtml(ev.text);
  text = text.replace(/REQUEST TEST\s*:\s*([^\n<]+)/gi,
    (m, t) => `${m.slice(0, m.indexOf(":"))}:<br><span class="chip test">🧪 开具检查：${t.trim()}</span>`);
  text = text.replace(/DIAGNOSIS READY\s*:\s*([^\n<]+)/gi,
    (m, t) => `${m.slice(0, m.indexOf(":"))}:<br><span class="chip dx">🩺 最终诊断：${t.trim()}</span>`);
  bubble.innerHTML = text;

  const copy = document.createElement("button");
  copy.className = "copy-btn";
  copy.textContent = "复制";
  copy.dataset.text = ev.text;
  copy.title = "复制本条内容";

  body.appendChild(name);
  body.appendChild(bubble);
  body.appendChild(copy);
  row.appendChild(av);
  row.appendChild(body);
  chat.appendChild(row);
  scrollBottom();
}

function renderVerdict(ev) {
  state.history.push({ role: "moderator", text: JSON.stringify(ev) });
  state.transcript.push({ role: "moderator", name: "主持人 Agent", emoji: "⚖️",
                          text: `判分：${ev.correct === true ? "正确" : "不符"}（标准答案：${ev.correct_answer}）` });
  const ok = ev.correct === true;
  const chat = $("chat");
  const card = document.createElement("div");
  card.className = "verdict-card " + (ok ? "ok" : "bad");
  card.innerHTML = `
    <h3>${ok ? "✅ 会诊结论与标准答案一致" : "❌ 会诊结论与标准答案不符"}</h3>
    <div class="detail">医生最终诊断：<b>${escapeHtml(ev.doctor_diagnosis || "（未给出）")}</b><br>
    标准答案：<b>${escapeHtml(ev.correct_answer)}</b></div>
    <div class="summary">会诊小结：共 ${countTurns()} 轮医患交流、${countTests()} 项检查；主持人 Agent 已依据标准答案完成判分。本平台输出仅供研究演示，不构成医疗建议。</div>`;
  chat.appendChild(card);
  addSystem(ok ? "主持人 Agent 判分：CORRECT ✅" : "主持人 Agent 判分：INCORRECT ❌");
  $("progress").textContent = "会诊已结束";
  scrollBottom();
  autoSaveSession();
}

function countTurns() { return state.history.filter((h) => h.role === "doctor").length; }
function countTests() { return state.history.filter((h) => /REQUEST TEST/i.test(h.text || "")).length; }

function addSystem(text) {
  const chat = $("chat");
  const div = document.createElement("div");
  div.className = "system-note";
  div.textContent = text;
  chat.appendChild(div);
  scrollBottom();
}

function addTyping(emoji, text) {
  const chat = $("chat");
  const row = document.createElement("div");
  row.className = "typing";
  row.innerHTML = `<div class="avatar">${emoji || "🧠"}</div><div class="msg-body"><div class="bubble">${text || "思考中…"}</div></div>`;
  chat.appendChild(row);
  scrollBottom();
  return row;
}

function scrollBottom() {
  const sc = document.querySelector(".chat-scroll");
  sc.scrollTop = sc.scrollHeight;
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

init();
