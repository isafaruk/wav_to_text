"use strict";

const $ = id => document.getElementById(id);
let engines = [], selectedFile = null, running = false, ready = false, polling = false;
let lastText = "", noticeTimer;

function formatTime(value) {
  const seconds = Math.max(0, Math.floor(value || 0));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function updatePerformance() {
  const local = ["faster_whisper", "whisper"].includes($("engine").value);
  $("performance-settings").hidden = !local;
  $("threads-row").hidden = !local || $("device").value !== "cpu";
  $("gpu-compute-row").hidden = $("engine").value !== "faster_whisper" || $("device").value !== "cuda";
}

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
  updatePerformance();
}

function renderState(state) {
  running = ["running", "cancelling"].includes(state.status);
  const labels = {idle:"HAZIR",running:"İŞLENİYOR",cancelling:"DURDURULUYOR",cancelled:"İPTAL EDİLDİ",success:"TAMAMLANDI",partial:"KISMİ SONUÇ",failed:"SONUÇ YOK",error:"HATA"};
  $("status-badge").textContent = labels[state.status] || "HAZIR";
  $("status-badge").className = `status-badge ${state.status}`;
  $("stage").textContent = state.stage;
  const unknown = (!state.progress_available && state.progress < 100) ||
    (running && ["preparing", "loading"].includes(state.phase));
  if (unknown) $("progress").removeAttribute("value");
  else $("progress").value = state.progress;
  $("percentage").textContent = unknown ? "—" : `${state.progress}%`;
  $("elapsed").textContent = `Geçen ${formatTime(state.elapsed_seconds)}`;
  $("cancel").hidden = !running;
  $("cancel").disabled = !state.can_cancel;
  $("cancel").textContent = state.status === "cancelling" ? "İptal ediliyor…" : "İptal et";
  $("job-metrics").hidden = !state.duration_seconds;
  const audioProgress = state.progress_available || state.progress === 100 ? formatTime(state.processed_seconds) : "—";
  $("audio-time").textContent = `İşlenen ses ${audioProgress} / ${formatTime(state.duration_seconds)}`;
  $("remaining").textContent = running ? `Tahmini kalan ${state.remaining_seconds == null ? "hesaplanıyor…" : "≈ " + formatTime(state.remaining_seconds)}` : "";
  $("speed").textContent = state.speed ? `Hız ${state.speed.toFixed(2)}×` : "";
  $("speed").title = "Bir saniyede işlenen ses süresi. Kalan süre tahmini değişebilir.";
  $("last-update").textContent = running && state.last_update_seconds != null ? `Son ilerleme ${state.last_update_seconds} sn önce` : "";
  const limited = running && !state.progress_available;
  $("progress-note").hidden = !limited;
  $("progress-note").textContent = limited ? "Standart Whisper ara ilerleme ve canlı metin sağlamaz; metin döndüğünde kaydedilir. Canlı takip için Faster Whisper seçebilirsiniz. İptal kullanılabilir." : "";
  if (limited) $("remaining").textContent = "Kalan süre bu motorda hesaplanamıyor";
  if (state.text !== lastText) {
    $("transcript").value = state.text;
    lastText = state.text;
  }
  $("transcript").hidden = !state.text;
  $("empty-state").hidden = !!state.text;
  $("word-count").textContent = `${state.text.trim() ? state.text.trim().split(/\s+/u).length : 0} kelime`;
  $("copy").disabled = !state.text;
  const output = state.output_path || state.checkpoint_path;
  $("open-folder").disabled = !output;
  $("output-path").textContent = output ? `${state.output_path ? "" : "Ara kayıt: "}${output}` : "TXT çıktısı";
  $("output-path").title = output || "";
  const messages = [...state.errors, ...(state.warnings || [])];
  $("errors").textContent = messages.join("\n");
  $("errors").hidden = !messages.length;
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
$("device").addEventListener("change", updatePerformance);
$("cancel").addEventListener("click", async () => {
  $("cancel").disabled = true;
  try {
    const result = await window.pywebview.api.cancel_conversion();
    if (!result.ok) throw new Error(result.error);
    renderState(result.state);
  } catch (error) { window.showNotice(error.message); await poll(); }
});
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
  clearTimeout(noticeTimer);
  $("notice").hidden = true;
  const spec = engines.find(engine => engine.id === $("engine").value);
  const settings = {engine:spec.id, model:$("model").value, device:$("device-row").hidden ? "cpu" : $("device").value,
    api_key:spec.key_env ? $("api-key").value : "", region:spec.id === "azure" ? $("region").value : "",
    model_path:spec.id === "vosk" ? $("model-path").value : "",
    cpu_threads:$("threads-row").hidden ? "auto" : $("cpu-threads").value,
    gpu_compute_type:$("gpu-compute-row").hidden ? "int8_float16" : $("gpu-compute").value};
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
    const automatic = new Option(`Otomatik · Faster Whisper için ${config.auto_cpu_threads}, Whisper için motor varsayılanı`, "auto");
    const threads = Array.from({length:config.cpu_count}, (_, i) => new Option(String(i + 1), String(i + 1)));
    $("cpu-threads").replaceChildren(automatic, ...threads);
    $("engine").replaceChildren(...engines.map(spec => new Option(spec.name, spec.id)));
    updateEngine();
    ready = true;
    await poll();
  } catch (error) { window.showNotice(`Arayüz başlatılamadı: ${error.message}`); }
});
