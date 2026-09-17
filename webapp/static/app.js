(() => {
  const $ = (id) => document.getElementById(id);

  const dropzone = $("dropzone");
  const fileInput = $("file-input");
  const parsingStatus = $("parsing-status");
  const bookPreview = $("book-preview");
  const bookCoverImg = $("book-cover-img");
  const bookCoverPlaceholder = $("book-cover-placeholder");
  const titleInput = $("title-input");
  const authorInput = $("author-input");
  const chapterCountEl = $("chapter-count");
  const estMinutesEl = $("est-minutes");
  const estSizeEl = $("est-size");
  const changeFileBtn = $("change-file-btn");

  const voiceCard = $("voice-card");
  const voiceGrid = $("voice-grid");
  const voiceFilters = $("voice-filters");
  const rateSlider = $("rate-slider");
  const rateValue = $("rate-value");
  const combinedToggle = $("combined-toggle");

  const generateCard = $("generate-card");
  const generateBtn = $("generate-btn");
  const estimateText = $("estimate-text");

  const progressCard = $("progress-card");
  const progressFill = $("progress-fill");
  const progressStatus = $("progress-status");

  const doneCard = $("done-card");
  const doneTitle = $("done-title");
  const doneMeta = $("done-meta");
  const downloadBtn = $("download-btn");
  const restartBtn = $("restart-btn");

  const errorCard = $("error-card");
  const errorMessage = $("error-message");
  const errorRestartBtn = $("error-restart-btn");

  const previewPlayer = $("preview-player");

  const stepEls = Array.from(document.querySelectorAll(".step"));
  const lines = [$("line-1-2"), $("line-2-3")];

  const ICON_PLAY = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg><span>Preview</span>';
  const ICON_PAUSE = '<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg><span>Playing</span>';
  const ICON_CHECK = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  const ICON_STAR_OUTLINE = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
  const ICON_STAR_FILLED = '<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';

  // ---------- Favorite voices (persisted locally) ----------

  const FAVORITES_KEY = "narratix_favorite_voices";

  function getFavorites() {
    try {
      const raw = localStorage.getItem(FAVORITES_KEY);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch (err) {
      return new Set();
    }
  }

  function saveFavorites(set) {
    try {
      localStorage.setItem(FAVORITES_KEY, JSON.stringify([...set]));
    } catch (err) {
      // Storage unavailable (private browsing, etc.) -- favorites just won't persist.
    }
  }

  function toggleFavorite(voiceId) {
    const favorites = getFavorites();
    if (favorites.has(voiceId)) favorites.delete(voiceId);
    else favorites.add(voiceId);
    saveFavorites(favorites);
    return favorites.has(voiceId);
  }

  const state = {
    uploadId: null,
    selectedVoiceId: null,
    downloadUrl: null,
    etaLow: null,
    etaHigh: null,
  };

  function show(el) { el.classList.remove("hidden"); }
  function hide(el) { el.classList.add("hidden"); }

  function setStep(n) {
    stepEls.forEach((el) => {
      const step = parseInt(el.dataset.step, 10);
      el.classList.remove("active", "complete");
      if (step < n) el.classList.add("complete");
      else if (step === n) el.classList.add("active");
    });
    lines.forEach((line, i) => {
      line.classList.toggle("filled", n > i + 1);
    });
  }

  function resetAll() {
    state.uploadId = null;
    state.selectedVoiceId = null;
    state.downloadUrl = null;
    state.etaLow = null;
    state.etaHigh = null;
    fileInput.value = "";
    hide(bookPreview);
    hide(voiceCard);
    hide(generateCard);
    hide(progressCard);
    hide(doneCard);
    hide(errorCard);
    hide(parsingStatus);
    show(dropzone);
    document.querySelectorAll(".voice-card").forEach((c) => c.classList.remove("selected"));
    setStep(1);
    checkReady();
  }

  // ---------- Step 1: upload & parse ----------

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });
  changeFileBtn.addEventListener("click", resetAll);

  async function handleFile(file) {
    if (!file.name.toLowerCase().endsWith(".epub")) {
      alert("Please choose a .epub file.");
      return;
    }
    hide(dropzone);
    show(parsingStatus);
    hide(bookPreview);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/parse", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not parse this EPUB.");

      state.uploadId = data.upload_id;
      state.etaLow = data.estimated_conversion_seconds_low;
      state.etaHigh = data.estimated_conversion_seconds_high;

      titleInput.value = data.title;
      authorInput.value = data.author;
      chapterCountEl.textContent = data.chapter_count;
      estMinutesEl.textContent = Math.round(data.estimated_minutes);
      estSizeEl.textContent = data.estimated_size_mb;
      estimateText.textContent = `Estimated generation time: ${formatRange(state.etaLow, state.etaHigh)}`;

      if (data.cover_data_url) {
        bookCoverImg.src = data.cover_data_url;
        show(bookCoverImg);
        hide(bookCoverPlaceholder);
      } else {
        hide(bookCoverImg);
        show(bookCoverPlaceholder);
      }

      hide(parsingStatus);
      show(bookPreview);
      show(voiceCard);
      show(generateCard);
      setStep(2);
      checkReady();
    } catch (err) {
      hide(parsingStatus);
      show(dropzone);
      alert(err.message || "Something went wrong reading that file.");
    }
  }

  // ---------- Step 2: voice gallery ----------

  let currentAudio = null;
  let currentPlayBtn = null;

  function stopPreview() {
    previewPlayer.pause();
    if (currentPlayBtn) currentPlayBtn.innerHTML = ICON_PLAY;
    if (currentPlayBtn) currentPlayBtn.classList.remove("playing");
    currentPlayBtn = null;
  }

  previewPlayer.addEventListener("ended", stopPreview);

  let activeFilter = "All";

  async function loadVoices() {
    const res = await fetch("/api/voices");
    const voices = await res.json();
    voiceGrid.innerHTML = "";

    const favorites = getFavorites();
    const sorted = [...voices].sort((a, b) => {
      const favA = favorites.has(a.id) ? 0 : 1;
      const favB = favorites.has(b.id) ? 0 : 1;
      return favA - favB;
    });

    sorted.forEach((voice) => {
      const isFavorite = favorites.has(voice.id);
      const card = document.createElement("div");
      card.className = "voice-card";
      card.dataset.voiceId = voice.id;
      card.dataset.accent = voice.accent;
      card.dataset.favorite = isFavorite ? "true" : "false";
      card.innerHTML = `
        <button type="button" class="favorite-btn${isFavorite ? " favorited" : ""}" title="Favorite this voice" aria-label="Favorite this voice">${isFavorite ? ICON_STAR_FILLED : ICON_STAR_OUTLINE}</button>
        <div class="voice-check">${ICON_CHECK}</div>
        <div class="voice-top">
          <div class="voice-avatar">${voice.name.charAt(0)}</div>
          <div class="voice-name-col">
            <span class="voice-name">${voice.name}</span>
            <span class="voice-tag">${voice.accent} &middot; ${voice.gender}</span>
          </div>
        </div>
        <div class="voice-tagline">${voice.tagline}</div>
        <button type="button" class="play-btn">${ICON_PLAY}</button>
      `;

      card.addEventListener("click", (e) => {
        if (e.target.closest(".play-btn") || e.target.closest(".favorite-btn")) return;
        document.querySelectorAll(".voice-card").forEach((c) => c.classList.remove("selected"));
        card.classList.add("selected");
        state.selectedVoiceId = voice.id;
        checkReady();
      });

      const playBtn = card.querySelector(".play-btn");
      playBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (currentPlayBtn === playBtn) {
          stopPreview();
          return;
        }
        stopPreview();
        previewPlayer.src = voice.sample_url;
        previewPlayer.play();
        playBtn.innerHTML = ICON_PAUSE;
        playBtn.classList.add("playing");
        currentPlayBtn = playBtn;
      });

      const favoriteBtn = card.querySelector(".favorite-btn");
      favoriteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const nowFavorite = toggleFavorite(voice.id);
        card.dataset.favorite = nowFavorite ? "true" : "false";
        favoriteBtn.classList.toggle("favorited", nowFavorite);
        favoriteBtn.innerHTML = nowFavorite ? ICON_STAR_FILLED : ICON_STAR_OUTLINE;
        if (activeFilter === "Favorites") applyVoiceFilter(activeFilter);
      });

      voiceGrid.appendChild(card);
    });

    buildVoiceFilters(voices);
  }

  function applyVoiceFilter(mode) {
    activeFilter = mode;
    document.querySelectorAll(".voice-card").forEach((card) => {
      let visible = true;
      if (mode === "Favorites") visible = card.dataset.favorite === "true";
      else if (mode !== "All") visible = card.dataset.accent === mode;
      card.classList.toggle("hidden", !visible);
    });
  }

  function buildVoiceFilters(voices) {
    const accents = [...new Set(voices.map((v) => v.accent))];
    voiceFilters.innerHTML = "";

    const makeChip = (label, mode) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip" + (mode === activeFilter ? " active" : "");
      chip.textContent = label;
      chip.addEventListener("click", () => {
        document.querySelectorAll(".filter-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        applyVoiceFilter(mode);
      });
      return chip;
    };

    voiceFilters.appendChild(makeChip("All voices", "All"));
    voiceFilters.appendChild(makeChip("★ Favorites", "Favorites"));
    accents.forEach((accent) => voiceFilters.appendChild(makeChip(accent, accent)));
  }

  rateSlider.addEventListener("input", () => {
    const v = parseInt(rateSlider.value, 10);
    rateValue.textContent = (v >= 0 ? "+" : "") + v + "%";
  });

  // ---------- Time formatting ----------

  function formatRange(lowSec, highSec) {
    if (lowSec == null || highSec == null) return "a few minutes";
    if (highSec < 60) {
      return `${Math.max(1, Math.round(lowSec))}–${Math.round(highSec)} sec`;
    }
    const lowMin = Math.max(1, Math.round(lowSec / 60));
    const highMin = Math.max(lowMin, Math.round(highSec / 60));
    return lowMin === highMin ? `~${lowMin} min` : `~${lowMin}–${highMin} min`;
  }

  function formatEta(seconds) {
    if (seconds == null) return "estimating time remaining…";
    const s = Math.round(seconds);
    if (s < 45) return "less than a minute remaining";
    const minutes = Math.round(s / 60);
    return `about ${minutes} min remaining`;
  }

  // ---------- Step 3: generate ----------

  function checkReady() {
    generateBtn.disabled = !(state.uploadId && state.selectedVoiceId);
  }

  titleInput.addEventListener("input", checkReady);
  authorInput.addEventListener("input", checkReady);

  generateBtn.addEventListener("click", startGeneration);

  async function startGeneration() {
    stopPreview();
    hide(voiceCard);
    hide(generateCard);
    hide(bookPreview);
    hide(errorCard);
    show(progressCard);
    setStep(3);
    setProgress(0, "Starting up…");

    const formData = new FormData();
    formData.append("upload_id", state.uploadId);
    formData.append("voice", state.selectedVoiceId);
    formData.append("title", titleInput.value);
    formData.append("author", authorInput.value);
    const rateNum = parseInt(rateSlider.value, 10);
    formData.append("rate", (rateNum >= 0 ? "+" : "") + rateNum + "%");
    formData.append("include_combined", combinedToggle.checked ? "true" : "false");

    try {
      const res = await fetch("/api/jobs", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not start the job.");
      streamProgress(data.job_id);
    } catch (err) {
      showError(err.message || "Something went wrong starting the conversion.");
    }
  }

  function setProgress(pct, text) {
    progressFill.style.width = Math.min(100, Math.max(0, pct)) + "%";
    progressStatus.textContent = text;
  }

  function streamProgress(jobId) {
    const source = new EventSource(`/api/jobs/${jobId}/events`);

    source.onmessage = (event) => {
      const payload = JSON.parse(event.data);

      if (payload.stage === "parsed") {
        setProgress(2, `Preparing ${payload.chapters} chapters…`);
      } else if (payload.stage === "synthesizing") {
        const frac = payload.total ? payload.done / payload.total : 0;
        setProgress(2 + frac * 73, `Narrating (${payload.done}/${payload.total}), ${formatEta(payload.eta_seconds)}`);
      } else if (payload.stage === "merging") {
        const frac = payload.total ? payload.done / payload.total : 0;
        setProgress(75 + frac * 15, `Assembling chapter ${payload.done} of ${payload.total}`);
      } else if (payload.stage === "combining") {
        setProgress(91, "Combining chapters into one file…");
      } else if (payload.stage === "packaging") {
        setProgress(96, "Packaging your download…");
      } else if (payload.stage === "done") {
        setProgress(100, "Done!");
        source.close();
        state.downloadUrl = payload.download_url;
        doneTitle.textContent = "Your audiobook is ready";
        doneMeta.textContent = `${titleInput.value} · ${payload.size_mb} MB`;
        hide(progressCard);
        show(doneCard);
      } else if (payload.stage === "error") {
        source.close();
        showError(payload.message || "Something went wrong during conversion.");
      }
    };

    source.onerror = () => {
      source.close();
    };
  }

  function showError(message) {
    hide(progressCard);
    errorMessage.textContent = message;
    show(errorCard);
  }

  downloadBtn.addEventListener("click", () => {
    if (state.downloadUrl) window.location.href = state.downloadUrl;
  });

  restartBtn.addEventListener("click", () => {
    hide(doneCard);
    resetAll();
  });

  errorRestartBtn.addEventListener("click", () => {
    hide(errorCard);
    resetAll();
  });

  // ---------- Storage location settings ----------

  const settingsBtn = $("settings-btn");
  const settingsDialog = $("settings-dialog");
  const closeSettingsBtn = $("close-settings-btn");
  const folderDisplay = $("folder-display");
  const folderMeta = $("folder-meta");
  const browseBtn = $("browse-btn");
  const saveSettingsBtn = $("save-settings-btn");
  const settingsNote = $("settings-note");

  let pendingDataDir = null;

  async function openSettings() {
    settingsNote.textContent = "";
    settingsNote.className = "settings-note";
    saveSettingsBtn.disabled = true;
    pendingDataDir = null;
    folderDisplay.textContent = "Loading…";
    settingsDialog.showModal();

    try {
      const res = await fetch("/api/settings");
      const data = await res.json();
      folderDisplay.textContent = data.data_dir;
      folderMeta.textContent = `${data.size_mb} MB used${data.is_default ? " · default location" : ""}`;
    } catch (err) {
      folderDisplay.textContent = "Could not load current settings.";
    }
  }

  settingsBtn.addEventListener("click", openSettings);
  closeSettingsBtn.addEventListener("click", () => settingsDialog.close());
  settingsDialog.addEventListener("click", (e) => {
    if (e.target === settingsDialog) settingsDialog.close();
  });

  browseBtn.addEventListener("click", async () => {
    browseBtn.disabled = true;
    settingsNote.textContent = "Opening folder picker…";
    settingsNote.className = "settings-note";
    try {
      const res = await fetch("/api/settings/browse", { method: "POST" });
      const data = await res.json();
      if (data.path) {
        pendingDataDir = data.path;
        folderDisplay.textContent = data.path;
        saveSettingsBtn.disabled = false;
        settingsNote.textContent = "Click Save to switch to this folder.";
      } else {
        settingsNote.textContent = "";
      }
    } catch (err) {
      settingsNote.textContent = "Could not open the folder picker.";
      settingsNote.className = "settings-note error";
    } finally {
      browseBtn.disabled = false;
    }
  });

  saveSettingsBtn.addEventListener("click", async () => {
    if (!pendingDataDir) return;
    saveSettingsBtn.disabled = true;
    settingsNote.textContent = "Saving…";
    settingsNote.className = "settings-note";
    try {
      const formData = new FormData();
      formData.append("data_dir", pendingDataDir);
      const res = await fetch("/api/settings", { method: "POST", body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not use that folder.");
      settingsNote.textContent = "Saved. New uploads and audiobooks will be stored here.";
      settingsNote.className = "settings-note success";
      pendingDataDir = null;
    } catch (err) {
      settingsNote.textContent = err.message || "Could not save that folder.";
      settingsNote.className = "settings-note error";
      saveSettingsBtn.disabled = false;
    }
  });

  loadVoices();
})();
