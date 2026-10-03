"use strict";

const $ = id => document.getElementById(id);
let engines = [], selectedFile = null, running = false, ready = false, polling = false;
let lastText = "", noticeTimer;

window.showNotice = function (message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { $("notice").hidden = true; }, 5500);
};

function updateControls() {
  $("settings").disabled = !ready || running;
  $("choose-file").disabled = !ready || running;
  $("start").disabled = !ready || running || !selectedFile;
  $("start").textContent = running ? "Dönüştürülüyor…" : "Metne dönüştür →";
}

function updateEngine() {
  const spec = engines.find(engine => engine.id === $("engine").value);
  const localWhisper = ["faster_whisper", "whisper"].includes(spec.id);
  $("engine-description").textContent = spec.description;
  $("model").replaceChildren(...spec.models.map(value => new Option(value, value)));
  $("model-row").hidden = !spec.models.length;
  $("device-row").hidden = !localWhisper;
  $("key-row").hidden = !spec.key_env;
  $("region-row").hidden = spec.id !== "azure";
  $("path-row").hidden = spec.id !== "vosk";
  $("api-key").value = "";
  $("api-key").placeholder = "Anahtarınızı girin";
  $("key-hint").textContent = spec.key_env ? `Veya ${spec.key_env} ortam değişkeni. Anahtar diske kaydedilmez.` : "";
}

function renderState(state) {
  running = state.status === "running";
  const labels = {idle:"HAZIR",running:"İŞLENİYOR",success:"TAMAMLANDI",partial:"KISMİ SONUÇ",failed:"SONUÇ YOK",error:"HATA"};
  $("status-badge").textContent = labels[state.status] || "HAZIR";
  $("status-badge").className = `status-badge ${state.status}`;
  $("stage").textContent = state.stage;
  $("progress").value = state.progress;
  $("percentage").textContent = `${state.progress}%`;
  const elapsed = state.elapsed_seconds || 0;
  $("elapsed").textContent = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
  if (state.text !== lastText) {
    $("transcript").value = state.text;
    lastText = state.text;
  }
  $("transcript").hidden = !state.text;
  $("empty-state").hidden = !!state.text;
  $("word-count").textContent = `${state.text.trim() ? state.text.trim().split(/\s+/u).length : 0} kelime`;
  $("copy").disabled = !state.text || running;
  $("open-folder").disabled = !state.output_path || running;
  $("output-path").textContent = state.output_path || "TXT çıktısı";
  $("output-path").title = state.output_path || "";
  $("errors").textContent = state.errors.join("\n");
  $("errors").hidden = !state.errors.length;
  updateControls();
}

async function poll() {
  if (!ready || polling) return;
  polling = true;
  try { renderState(await window.pywebview.api.get_state()); }
  catch (error) { window.showNotice(`İşlem durumu alınamadı: ${error.message}`); }
  finally { polling = false; }
  if (running) setTimeout(poll, 500);
}

$("engine").addEventListener("change", updateEngine);
$("choose-file").addEventListener("click", async () => {
  $("choose-file").disabled = true;
  try {
    const result = await window.pywebview.api.choose_file();
    if (!result.ok) throw new Error(result.error);
    if (result.file) {
      selectedFile = result.file;
      $("file-name").textContent = selectedFile.name;
      $("file-meta").textContent = `${(selectedFile.size / 1024 / 1024).toFixed(1)} MB · Değiştirmek için tıkla`;
      $("file-path").textContent = selectedFile.path;
      $("file-path").title = selectedFile.path;
      $("file-path").hidden = false;
      $("choose-file").classList.add("has-file");
    }
  } catch (error) { window.showNotice(error.message); }
  finally { updateControls(); }
});

$("choose-model").addEventListener("click", async () => {
  try { const path = await window.pywebview.api.choose_model_folder(); if (path) $("model-path").value = path; }
  catch (error) { window.showNotice(error.message); }
});

$("start").addEventListener("click", async () => {
  const spec = engines.find(engine => engine.id === $("engine").value);
  const settings = {engine:spec.id, model:$("model").value, device:$("device-row").hidden ? "cpu" : $("device").value,
    api_key:spec.key_env ? $("api-key").value : "", region:spec.id === "azure" ? $("region").value : "",
    model_path:spec.id === "vosk" ? $("model-path").value : ""};
  running = true;
  updateControls();
  try {
    const result = await window.pywebview.api.start_conversion(settings);
    if (!result.ok) throw new Error(result.error);
    renderState(result.state);
    if (running) poll();
  } catch (error) { running = false; updateControls(); window.showNotice(error.message); }
});

$("copy").addEventListener("click", async () => {
  try {
    try { await navigator.clipboard.writeText($("transcript").value); }
    catch (_) { $("transcript").select(); if (!document.execCommand("copy")) throw new Error("Kopyalama kullanılamıyor; metni seçip Ctrl+C kullanın."); }
    window.showNotice("Metin panoya kopyalandı.");
  } catch (error) { window.showNotice(error.message); }
});

$("open-folder").addEventListener("click", async () => {
  try { const result = await window.pywebview.api.open_output_folder(); if (!result.ok) throw new Error(result.error); }
  catch (error) { window.showNotice(error.message); }
});

window.addEventListener("pywebviewready", async () => {
  try {
    const config = await window.pywebview.api.get_config();
    engines = config.engines;
    $("engine").replaceChildren(...engines.map(spec => new Option(spec.name, spec.id)));
    updateEngine();
    ready = true;
    await poll();
  } catch (error) { window.showNotice(`Arayüz başlatılamadı: ${error.message}`); }
});
