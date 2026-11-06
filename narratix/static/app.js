(() => {
  const $ = (id) => document.getElementById(id);

  const uploadCard = $("upload-card");
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
  const folderFormat = $("folder-format");
  const folderPreview = $("folder-preview");

  const generateCard = $("generate-card");
  const generateBtn = $("generate-btn");
  const estimateText = $("estimate-text");

  const progressCard = $("progress-card");
  const progressFill = $("progress-fill");
  const progressStatus = $("progress-status");

  const doneCard = $("done-card");
  const doneTitle = $("done-title");
  const doneMeta = $("done-meta");
  const restartBtn = $("restart-btn");

  const errorCard = $("error-card");
  const errorMessage = $("error-message");
  const errorRestartBtn = $("error-restart-btn");

  const previewPlayer = $("preview-player");

  const stepEls = Array.from(document.querySelectorAll(".step"));
  const lines = [$("line-1-2"), $("line-2-3")];

  const ICON_PLAY = '<svg width="11" height="11" viewBox="0 0 256 256" fill="currentColor"><path d="M232 128a15.9 15.9 0 0 1-7.6 13.6l-144 88A16 16 0 0 1 56 216V40a16 16 0 0 1 24.4-13.6l144 88A15.9 15.9 0 0 1 232 128Z"/></svg><span>Preview</span>';
  const ICON_PAUSE = '<svg width="11" height="11" viewBox="0 0 256 256" fill="currentColor"><path d="M216 48v160a16 16 0 0 1-16 16h-40a16 16 0 0 1-16-16V48a16 16 0 0 1 16-16h40a16 16 0 0 1 16 16ZM96 32H56a16 16 0 0 0-16 16v160a16 16 0 0 0 16 16h40a16 16 0 0 0 16-16V48a16 16 0 0 0-16-16Z"/></svg><span>Playing</span>';
  const ICON_CHECK = '<svg width="11" height="11" viewBox="0 0 256 256" fill="currentColor"><path d="m229.7 77.7-120 120a8 8 0 0 1-11.4 0l-56-56a8 8 0 0 1 11.4-11.4L104 180.7 218.3 66.3a8 8 0 0 1 11.4 11.4Z"/></svg>';
  const STAR_OUTLINE = "M239.2 97.3a16.5 16.5 0 0 0-14-11.3l-56.6-4.9-22-52.8a16.3 16.3 0 0 0-30.4 0l-22 52.8-56.6 4.9A16.5 16.5 0 0 0 28 114l43 37.6-13 55.5A16.4 16.4 0 0 0 82 224.8l46-27.5 46 27.5a16.4 16.4 0 0 0 23.9-17.7l-13-55.5 43-37.6a16.4 16.4 0 0 0 5.3-16.7ZM128 184.6l-48.5 29 13.7-58.4L48 115.8l59.7-5.2L128 54.9l20.3 55.7 59.7 5.2-45.2 39.4 13.7 58.4Z";
  const STAR_FILLED = "M234.3 108.3 191 146l13 55.5a8.4 8.4 0 0 1-12.6 9.1L128 173.4l-63.4 37.2a8.4 8.4 0 0 1-12.6-9.1L65 146l-43.3-37.7a8.4 8.4 0 0 1 4.8-14.7l57-4.9 22-52.8a8.3 8.3 0 0 1 15.4 0l22 52.8 57 4.9a8.4 8.4 0 0 1 4.8 14.7Z";
  const star = (d) => `<svg width="14" height="14" viewBox="0 0 256 256" fill="currentColor"><path d="${d}"/></svg>`;
  const ICON_STAR_OUTLINE = star(STAR_OUTLINE);
  const ICON_STAR_FILLED = star(STAR_FILLED);

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
    state.etaLow = null;
    state.etaHigh = null;
    fileInput.value = "";
    show(uploadCard);
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
      updateFolderPreview();
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

    sorted.forEach((voice, index) => {
      const isFavorite = favorites.has(voice.id);
      const card = document.createElement("div");
      card.className = "voice-card";
      card.style.setProperty("--i", index);
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
            <span class="voice-tag">${voice.accent} / ${voice.gender}</span>
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

    voiceFilters.appendChild(makeChip("All", "All"));
    voiceFilters.appendChild(makeChip("Favorites", "Favorites"));
    accents.forEach((accent) => voiceFilters.appendChild(makeChip(accent, accent)));
  }

  rateSlider.addEventListener("input", () => {
    const v = parseInt(rateSlider.value, 10);
    rateValue.textContent = (v >= 0 ? "+" : "") + v + "%";
  });

  // ---------- Folder name format (remembered between visits) ----------

  const FORMAT_KEY = "narratix_folder_format";
  const FORMATS = {
    title_author: (t, a) => `${t} - ${a}`,
    author_title: (t, a) => `${a} - ${t}`,
    title: (t) => t,
    author_nested: (t, a) => `${a}/${t}`,
  };

  function updateFolderPreview() {
    const t = titleInput.value.trim() || "Title";
    const a = authorInput.value.trim() || "Author";
    folderPreview.textContent = FORMATS[folderFormat.value](t, a) + "/";
  }

  try { folderFormat.value = localStorage.getItem(FORMAT_KEY) || "title_author"; } catch (err) { /* default */ }
  folderFormat.addEventListener("change", () => {
    try { localStorage.setItem(FORMAT_KEY, folderFormat.value); } catch (err) { /* won't persist */ }
    updateFolderPreview();
  });
  titleInput.addEventListener("input", updateFolderPreview);
  authorInput.addEventListener("input", updateFolderPreview);

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
    hide(uploadCard);
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
    formData.append("folder_format", folderFormat.value);

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
      } else if (payload.stage === "done") {
        setProgress(100, "Done!");
        source.close();
        doneTitle.textContent = "Your audiobook is ready";
        doneMeta.textContent = `${payload.size_mb} MB · saved to ${payload.saved_path}`;
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
      folderMeta.textContent = data.is_default ? "Default location" : "";
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
      settingsNote.textContent = "Saved. New audiobooks will be saved here.";
      settingsNote.className = "settings-note success";
      pendingDataDir = null;
    } catch (err) {
      settingsNote.textContent = err.message || "Could not save that folder.";
      settingsNote.className = "settings-note error";
      saveSettingsBtn.disabled = false;
    }
  });

  // ---------- Library (books found in the save folder) ----------

  const createView = $("create-view");
  const libraryView = $("library-view");
  const tabCreate = $("tab-create");
  const tabLibrary = $("tab-library");
  const libShelf = $("lib-shelf");
  const libGrid = $("lib-grid");
  const libEmpty = $("lib-empty");
  const libSearch = $("lib-search");
  const libSort = $("lib-sort");
  const libDetail = $("lib-detail");
  const libPlayer = $("lib-player");
  const libChapters = $("lib-chapters");

  const ICON_PLAY_ONLY = '<svg width="11" height="11" viewBox="0 0 256 256" fill="currentColor"><path d="M232 128a15.9 15.9 0 0 1-7.6 13.6l-144 88A16 16 0 0 1 56 216V40a16 16 0 0 1 24.4-13.6l144 88A15.9 15.9 0 0 1 232 128Z"/></svg>';
  const ICON_PAUSE_ONLY = '<svg width="11" height="11" viewBox="0 0 256 256" fill="currentColor"><path d="M216 48v160a16 16 0 0 1-16 16h-40a16 16 0 0 1-16-16V48a16 16 0 0 1 16-16h40a16 16 0 0 1 16 16ZM96 32H56a16 16 0 0 0-16 16v160a16 16 0 0 0 16 16h40a16 16 0 0 0 16-16V48a16 16 0 0 0-16-16Z"/></svg>';

  let libBooks = [];
  let libCurrent = null;
  let libTracks = [];
  let libIndex = -1;

  // textContent only: titles and authors come from user EPUB metadata, so never inject them as HTML.
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };

  function formatDuration(sec) {
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(s).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  }

  function showView(name) {
    const lib = name === "library";
    createView.classList.toggle("hidden", lib);
    libraryView.classList.toggle("hidden", !lib);
    document.body.classList.toggle("is-library", lib);
    tabCreate.classList.toggle("active", !lib);
    tabLibrary.classList.toggle("active", lib);
    if (lib) { stopPreview(); showShelf(); loadLibrary(); }
    else libPlayer.pause();
  }
  tabCreate.addEventListener("click", () => showView("create"));
  tabLibrary.addEventListener("click", () => showView("library"));

  async function loadLibrary() {
    try {
      const [books, settings] = await Promise.all([
        fetch("/api/library").then((r) => r.json()),
        fetch("/api/settings").then((r) => r.json()),
      ]);
      libBooks = books;
      $("lib-folder").textContent = settings.data_dir;
      libEmpty.dataset.folder = settings.data_dir;
    } catch (err) {
      libBooks = [];
    }
    renderShelf();
  }

  function renderShelf() {
    const q = libSearch.value.trim().toLowerCase();
    const books = libBooks.filter((b) => !q || `${b.title} ${b.author}`.toLowerCase().includes(q));
    const by = libSort.value;
    books.sort((a, b) =>
      by === "recent" ? b.modified - a.modified : (a[by] || "").localeCompare(b[by] || ""));

    libGrid.replaceChildren();
    books.forEach((book, i) => {
      const card = el("button", "lib-card");
      card.type = "button";
      card.style.setProperty("--i", i);
      if (book.cover_url) {
        const img = el("img", "lib-cover");
        img.src = book.cover_url;
        img.alt = "";
        img.loading = "lazy";
        card.append(img);
      } else {
        card.append(el("div", "lib-cover placeholder", (book.title || "?").charAt(0)));
      }
      card.append(
        el("div", "lib-title", book.title),
        el("div", "lib-author", book.author || "Unknown author"),
        el("div", "lib-meta mono", `${book.chapter_count} chapters · ${book.size_mb} MB`),
      );
      card.addEventListener("click", () => openBook(book));
      libGrid.append(card);
    });

    const none = books.length === 0;
    libGrid.classList.toggle("hidden", none);
    libEmpty.classList.toggle("hidden", !none);
    libEmpty.textContent = libBooks.length
      ? "No books match your search."
      : `No audiobooks found in ${libEmpty.dataset.folder || "your save folder"} yet. Create one and it will appear here.`;
  }
  libSearch.addEventListener("input", renderShelf);
  libSort.addEventListener("change", renderShelf);

  function showShelf() {
    libPlayer.pause();
    hide(libDetail);
    show(libShelf);
  }
  $("lib-back").addEventListener("click", showShelf);

  async function openBook(book) {
    libCurrent = book;
    $("lib-title").textContent = book.title;
    $("lib-author").textContent = book.author || "Unknown author";
    $("lib-meta").textContent = `${book.chapter_count} chapters · ${book.size_mb} MB`;
    const cover = $("lib-cover"), ph = $("lib-cover-ph");
    if (book.cover_url) { cover.src = book.cover_url; show(cover); hide(ph); }
    else { hide(cover); show(ph); }
    libChapters.replaceChildren();
    hide(libShelf);
    show(libDetail);

    const res = await fetch(`/api/library/chapters?path=${encodeURIComponent(book.path)}`);
    libTracks = res.ok ? await res.json() : [];
    libIndex = -1;
    libTracks.forEach((track, i) => {
      const row = el("li", "chapter-row");
      const btn = el("span", "chapter-play");
      btn.innerHTML = ICON_PLAY_ONLY;
      row.append(btn, el("span", "chapter-no mono", String(i + 1).padStart(2, "0")),
                 el("span", "chapter-title", track.title),
                 el("span", "chapter-dur mono", formatDuration(track.duration)));
      row.addEventListener("click", () => playTrack(i));
      libChapters.append(row);
    });
  }

  function syncPlayIcons() {
    Array.from(libChapters.children).forEach((row, n) => {
      const playing = n === libIndex && !libPlayer.paused;
      row.classList.toggle("playing", n === libIndex);
      row.querySelector(".chapter-play").innerHTML = playing ? ICON_PAUSE_ONLY : ICON_PLAY_ONLY;
    });
  }

  function playTrack(i) {
    if (i === libIndex && !libPlayer.paused) { libPlayer.pause(); return; }
    if (i !== libIndex) { libPlayer.src = libTracks[i].url; libIndex = i; }
    libPlayer.play();
  }
  libPlayer.addEventListener("play", syncPlayIcons);
  libPlayer.addEventListener("pause", syncPlayIcons);
  libPlayer.addEventListener("ended", () => {
    if (libIndex + 1 < libTracks.length) playTrack(libIndex + 1);
  });

  $("lib-open").addEventListener("click", () => {
    if (!libCurrent) return;
    const formData = new FormData();
    formData.append("path", libCurrent.path);
    fetch("/api/library/open", { method: "POST", body: formData });
  });

  // ---------- Theme ----------

  $("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("narratix_theme", next); } catch (err) { /* choice just won't persist */ }
  });

  loadVoices();
})();
