(function () {
  const state = window.APP_STATE || null;
  const jobState = window.APP_JOB_STATE || null;
  const importState = window.APP_IMPORT_STATE || null;
  const audio = document.getElementById("audio-player");
  const toggle = document.getElementById("player-toggle");
  const currentTime = document.getElementById("current-time");
  const durationTime = document.getElementById("duration-time");
  const progress = document.getElementById("audio-progress");
  const waveformSegments = Array.from(document.querySelectorAll("[data-wave-start]"));
  const playerNow = document.getElementById("player-now");
  const playerNowText = document.getElementById("player-now-text");
  const playerNowTime = document.getElementById("player-now-time");
  const followPlaybackToggle = document.getElementById("follow-playback-toggle");
  const search = document.getElementById("segment-search");
  const searchPrevious = document.getElementById("segment-search-prev");
  const searchNext = document.getElementById("segment-search-next");
  const searchScopeButtons = document.querySelectorAll("[data-search-scope]");
  const tabs = document.querySelectorAll(".tab");
  const panes = document.querySelectorAll(".pane");
  const densityButtons = document.querySelectorAll("[data-density]");
  const segmentList = document.getElementById("segment-list");
  const copyButton = document.getElementById("copy-button");
  const copyPlainTextButton = document.getElementById("copy-plain-text-button");
  const plainTextOutput = document.getElementById("plain-text-output");
  const plainTextStatus = document.getElementById("plain-text-status");
  const renameButton = document.getElementById("rename-button");
  const deleteButton = document.getElementById("delete-button");
  const deleteLocalDataButton = document.getElementById("delete-local-data-button");
  const collectionEditor = document.getElementById("collection-editor");
  const collectionInput = document.getElementById("collection-input");
  const collectionFilter = document.getElementById("collection-filter");
  const tagFilter = document.getElementById("tag-filter");
  const tagEditor = document.getElementById("tag-editor");
  const tagsInput = document.getElementById("tags-input");
  const speakerFilter = document.getElementById("speaker-filter");
  const notesEditor = document.getElementById("notes-editor");
  const notesInput = document.getElementById("notes-input");
  const notesStatus = document.getElementById("notes-status");
  const refreshSummaryButton = document.getElementById("refresh-summary-button");
  const copySummaryButton = document.getElementById("copy-summary-button");
  const summaryCards = document.getElementById("summary-cards");
  const summaryProviderLabel = document.getElementById("summary-provider-label");
  const summaryState = document.getElementById("summary-state");
  const titleEl = document.getElementById("record-title");
  const jobStatus = document.getElementById("job-status");
  const jobStatusTitle = document.getElementById("job-status-title");
  const jobStatusMessage = document.getElementById("job-status-message");
  const jobMeta = jobStatus ? jobStatus.querySelector(".job-meta") : null;
  const jobCancelButton = document.getElementById("job-cancel-button");
  const importStatus = document.getElementById("import-status");
  const importStatusTitle = document.getElementById("import-status-title");
  const importStatusMessage = document.getElementById("import-status-message");
  const importProgress = document.getElementById("import-progress");
  const importMeta = document.getElementById("import-meta");
  const importJobList = document.getElementById("import-job-list");
  const importOpenFirst = document.getElementById("import-open-first");
  const transcribeForm = document.getElementById("transcribe-form");
  const transcribeButton = document.getElementById("transcribe-button");
  const transcribeStatus = document.getElementById("transcribe-status");
  const fileInput = document.getElementById("audio-file-input");
  const uploadCard = document.getElementById("upload-card");
  const uploadPanel = document.getElementById("upload-panel");
  const workspaceComposer = document.getElementById("workspace-composer");
  const settingsWorkspace = document.getElementById("settings-workspace");
  const detailPanel = document.querySelector(".detail-panel");
  const sidebar = document.querySelector(".sidebar");
  const sidebarToggle = document.getElementById("sidebar-toggle");
  const contextBackdrop = document.getElementById("context-backdrop");
  const closeUploadPanel = document.getElementById("close-upload-panel");
  const fileNameLabel = document.getElementById("selected-file-name");
  const openUploadButtons = document.querySelectorAll("[data-open-upload]");
  const searchCount = document.getElementById("segment-search-count");
  const workspaceModeButtons = document.querySelectorAll("[data-workspace-mode]");
  const confirmModal = document.getElementById("confirm-modal");
  const confirmModalTitle = document.getElementById("confirm-modal-title");
  const confirmModalMessage = document.getElementById("confirm-modal-message");
  const confirmModalCancel = document.getElementById("confirm-modal-cancel");
  const confirmModalConfirm = document.getElementById("confirm-modal-confirm");
  const appSettings = (state && state.settings) || { autoplay_on_seek: true, confirm_before_delete: true };
  const summaryProviderNames = {
    local_instruction_quality: "Quality local instruction (Qwen3 1.7B)",
    local_instruction: "Fast local instruction (Qwen3 0.6B)",
    local_transformer: "Experimental German mT5",
    extractive: "Extractive fallback"
  };
  const segmentRows = Array.from(document.querySelectorAll(".segment[data-start]"));
  const segmentFragments = Array.from(document.querySelectorAll(".segment-fragment[data-start]"));
  let lastActiveSegment = null;
  let followPlayback = window.localStorage.getItem("whisperLocal.followPlayback") !== "false";
  let transcriptDensity = window.localStorage.getItem("whisperLocal.transcriptDensity") || "comfortable";
  let searchScope = window.localStorage.getItem("whisperLocal.searchScope") || "transcript";
  let activeCollectionFilter = window.localStorage.getItem("whisperLocal.collectionFilter") || "all";
  let activeTagFilter = window.localStorage.getItem("whisperLocal.tagFilter") || "all";
  let isSidebarCollapsed = window.localStorage.getItem("whisperLocal.sidebarCollapsed") === "true";
  const formatTime = (seconds) => {
    const total = Math.max(0, Math.floor(seconds || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };
  const setWaveformDuration = (duration) => {
    if (!Number.isFinite(duration) || duration <= 0 || !waveformSegments.length) return;
    waveformSegments.forEach((bar, index) => {
      const start = (duration * index) / waveformSegments.length;
      const end = (duration * (index + 1)) / waveformSegments.length;
      bar.dataset.waveStart = start.toFixed(2);
      bar.dataset.waveEnd = end.toFixed(2);
      bar.setAttribute("aria-label", `Seek to ${formatTime(start)}`);
    });
  };
  const renderDecodedWaveform = async () => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!audio || !waveformSegments.length || !audio.currentSrc || !AudioContextClass) return;
    try {
      const response = await fetch(audio.currentSrc);
      if (!response.ok) return;
      const bytes = await response.arrayBuffer();
      const context = new AudioContextClass();
      const buffer = await context.decodeAudioData(bytes);
      const channel = buffer.getChannelData(0);
      const samplesPerBar = Math.max(1, Math.floor(channel.length / waveformSegments.length));
      waveformSegments.forEach((bar, index) => {
        const start = index * samplesPerBar;
        const end = Math.min(channel.length, start + samplesPerBar);
        let sum = 0;
        let sampled = 0;
        const stride = Math.max(1, Math.floor((end - start) / 240));
        for (let sampleIndex = start; sampleIndex < end; sampleIndex += stride) {
          const value = channel[sampleIndex] || 0;
          sum += value * value;
          sampled += 1;
        }
        const rms = Math.sqrt(sum / Math.max(sampled, 1));
        const height = Math.round(9 + Math.min(1, rms * 7) * 36);
        bar.style.setProperty("--wave-height", `${height}px`);
      });
      setWaveformDuration(buffer.duration);
      if (typeof context.close === "function") {
        await context.close();
      }
    } catch (error) {
      console.debug("audio waveform decode failed", error);
    }
  };
  const statusLabel = (status) => {
    if (status === "queued") return "Queued";
    if (status === "running") return "Transcribing";
    if (status === "complete") return "Complete";
    if (status === "skipped") return "Skipped";
    if (status === "failed") return "Failed";
    if (status === "canceled") return "Canceled";
    return status || "Unknown";
  };
  const copyTextToClipboard = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.left = "-9999px";
    document.body.appendChild(helper);
    helper.select();
    document.execCommand("copy");
    helper.remove();
  };
  const ensureSpeakerOption = (speaker) => {
    if (!speakerFilter || !speaker || Array.from(speakerFilter.options).some((option) => option.value === speaker)) return;
    const option = document.createElement("option");
    option.value = speaker;
    option.textContent = speaker;
    speakerFilter.appendChild(option);
  };

  const setSidebarCollapsed = (collapsed) => {
    isSidebarCollapsed = Boolean(collapsed);
    document.body.classList.toggle("sidebar-collapsed", isSidebarCollapsed);
    if (sidebar) sidebar.dataset.collapsed = String(isSidebarCollapsed);
    if (sidebarToggle) {
      sidebarToggle.setAttribute("aria-expanded", String(!isSidebarCollapsed));
      sidebarToggle.setAttribute("aria-label", isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar");
      sidebarToggle.title = isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar";
    }
    window.localStorage.setItem("whisperLocal.sidebarCollapsed", String(isSidebarCollapsed));
  };

  if (sidebarToggle) {
    setSidebarCollapsed(isSidebarCollapsed);
    sidebarToggle.addEventListener("click", () => {
      setSidebarCollapsed(!isSidebarCollapsed);
    });
  }

  if (jobState && jobStatus) {
    const renderJobMeta = (job) => {
      if (!jobMeta) return;
      jobMeta.innerHTML = "";
      [
        `Model: ${job.model}`,
        `Mode: ${job.processing_mode || "CPU"}`,
        `Stage: ${statusLabel(job.status)}`,
        `Elapsed: ${formatTime(job.elapsed_seconds || 0)}`,
        `Estimate: ${job.estimated_duration || "Local processing time varies"}`,
        `File: ${job.source_size_label || "Unknown size"}`
      ].forEach((item) => {
        const span = document.createElement("span");
        span.textContent = item;
        jobMeta.appendChild(span);
      });
    };
    const pollJob = async () => {
      try {
        const response = await fetch(`/jobs/${jobState.id}.json`);
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Job status unavailable.");
        const job = payload.job;
        if (jobStatusTitle) {
          jobStatusTitle.textContent =
            job.status === "failed"
              ? "Transcription failed"
              : job.status === "canceled"
                ? "Transcription canceled"
                : job.status === "complete"
                  ? "Transcription complete"
                  : "Transcribing audio";
        }
        if (jobStatusMessage) {
          jobStatusMessage.textContent =
            job.status === "failed"
              ? job.error || "Transcription failed."
              : job.status === "canceled"
                ? "The queued transcription was canceled before it started."
              : job.status === "complete"
                ? "Opening transcript..."
                : `${job.source_name} is ${job.status}; no cloud upload occurs.`;
        }
        if (jobCancelButton) jobCancelButton.hidden = !job.can_cancel;
        renderJobMeta(job);
        if (job.status === "complete" && payload.redirect_url) {
          window.location.href = payload.redirect_url;
          return;
        }
        if (job.status !== "failed" && job.status !== "canceled") {
          window.setTimeout(pollJob, 1500);
        }
      } catch (error) {
        if (jobStatusTitle) jobStatusTitle.textContent = "Status unavailable";
        if (jobStatusMessage) jobStatusMessage.textContent = error.message || "Could not read job status.";
      }
    };
    if (jobCancelButton) {
      jobCancelButton.hidden = !jobState.can_cancel;
      jobCancelButton.addEventListener("click", async () => {
        jobCancelButton.disabled = true;
        jobCancelButton.textContent = "Canceling...";
        try {
          const response = await fetch(`/jobs/${jobState.id}/cancel`, { method: "POST" });
          const payload = await response.json();
          if (!response.ok || !payload.ok) throw new Error(payload.error || "Cancel failed.");
          if (jobStatusTitle) jobStatusTitle.textContent = "Transcription canceled";
          if (jobStatusMessage) jobStatusMessage.textContent = "The queued transcription was canceled before it started.";
          if (payload.job) renderJobMeta(payload.job);
          jobCancelButton.hidden = true;
        } catch (error) {
          jobCancelButton.disabled = false;
          jobCancelButton.textContent = "Cancel queued job";
          if (jobStatusMessage) jobStatusMessage.textContent = error.message || "Could not cancel queued job.";
        }
      });
    }
    window.setTimeout(pollJob, 800);
  }

  if (importState && importStatus) {
    const renderImportBatch = (batch) => {
      const total = batch.total_count || 0;
      const finished = batch.finished_count || 0;
      const failed = batch.failed_count || 0;
      const canceled = batch.canceled_count || 0;
      const skipped = batch.skipped_count || 0;
      const isComplete = total > 0 && finished >= total;
      if (importStatusTitle) {
        importStatusTitle.textContent = isComplete ? "Import complete" : "Importing audio";
      }
      if (importStatusMessage) {
        const issueCount = failed + canceled;
        let suffix = ".";
        if (skipped && issueCount) {
          suffix = `; ${skipped} skipped as duplicate${skipped === 1 ? "" : "s"}; ${issueCount} need attention.`;
        } else if (skipped) {
          suffix = `; ${skipped} skipped as duplicate${skipped === 1 ? "" : "s"}.`;
        } else if (issueCount) {
          suffix = `; ${issueCount} need attention.`;
        }
        importStatusMessage.textContent =
          `${finished} of ${total} file${total === 1 ? "" : "s"} finished` + suffix;
      }
      if (importProgress) {
        importProgress.value = Number(batch.progress_percent || 0);
      }
      if (importMeta) {
        importMeta.innerHTML = "";
        [
          `${batch.complete_count || 0} complete`,
          `${batch.skipped_count || 0} skipped`,
          `${batch.running_count || 0} running`,
          `${batch.queued_count || 0} queued`,
          `${batch.failed_count || 0} failed`
        ].forEach((text) => {
          const span = document.createElement("span");
          span.textContent = text;
          importMeta.appendChild(span);
        });
      }
      if (importJobList) {
        importJobList.innerHTML = "";
        (batch.jobs || []).forEach((job) => {
          const row = document.createElement("div");
          const name = document.createElement("span");
          const status = document.createElement("span");
          row.className = "import-job-row";
          row.dataset.importJob = job.id;
          name.className = "import-job-row__name";
          status.className = "import-job-row__status";
          status.dataset.status = job.status;
          name.textContent = job.source_name || "Audio file";
          status.textContent = statusLabel(job.status);
          if (job.skip_reason) row.title = job.skip_reason;
          row.append(name, status);
          importJobList.appendChild(row);
        });
      }
      const firstUrl = batch.first_record_url || (batch.first_record_id ? `/transcripts/${batch.first_record_id}` : "");
      if (importOpenFirst) {
        importOpenFirst.hidden = !firstUrl;
        if (firstUrl) importOpenFirst.href = firstUrl;
      }
      return isComplete;
    };

    const pollImport = async () => {
      try {
        const response = await fetch(`/imports/${importState.id}.json`);
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Import status unavailable.");
        const isComplete = renderImportBatch(payload.batch);
        if (!isComplete) {
          window.setTimeout(pollImport, 1500);
        }
      } catch (error) {
        if (importStatusTitle) importStatusTitle.textContent = "Import status unavailable";
        if (importStatusMessage) importStatusMessage.textContent = error.message || "Could not read import status.";
      }
    };

    renderImportBatch(importState);
    if (importState.status !== "complete") {
      window.setTimeout(pollImport, 800);
    }
  }

  const setWorkspaceMode = (mode) => {
    const nextMode = mode === "settings" ? "settings" : "history";
    if (settingsWorkspace) settingsWorkspace.hidden = nextMode !== "settings";
    if (workspaceComposer) workspaceComposer.hidden = nextMode === "settings";
    workspaceModeButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.workspaceMode === nextMode);
    });
    document.body.dataset.workspaceMode = nextMode;
    window.localStorage.setItem("whisperLocal.workspaceMode", nextMode);
  };

  if (workspaceModeButtons.length) {
    const savedMode = window.localStorage.getItem("whisperLocal.workspaceMode");
    setWorkspaceMode(savedMode === "settings" ? "settings" : "history");
    workspaceModeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setWorkspaceMode(button.dataset.workspaceMode);
      });
    });
  }

  const getCollectionButtons = () => Array.from(document.querySelectorAll("[data-collection-filter]"));
  const getTagButtons = () => Array.from(document.querySelectorAll("[data-tag-filter]"));
  const getCollectionRows = () => Array.from(document.querySelectorAll("[data-record-row]"));
  const setLibraryFilters = (collection, tag) => {
    const collectionButtons = getCollectionButtons();
    const tagButtons = getTagButtons();
    const hasCollection = collection === "all" || collectionButtons.some((button) => button.dataset.collectionFilter === collection);
    const hasTag = tag === "all" || tagButtons.some((button) => button.dataset.tagFilter === tag);
    activeCollectionFilter = hasCollection ? collection : "all";
    activeTagFilter = hasTag ? tag : "all";
    getCollectionRows().forEach((row) => {
      const tags = (row.dataset.tags || "").split("|").filter(Boolean);
      const collectionMatch = activeCollectionFilter === "all" || row.dataset.collection === activeCollectionFilter;
      const tagMatch = activeTagFilter === "all" || tags.includes(activeTagFilter);
      row.hidden = !collectionMatch || !tagMatch;
    });
    collectionButtons.forEach((button) => {
      const isActive = button.dataset.collectionFilter === activeCollectionFilter;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
    tagButtons.forEach((button) => {
      const isActive = button.dataset.tagFilter === activeTagFilter;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
    window.localStorage.setItem("whisperLocal.collectionFilter", activeCollectionFilter);
    window.localStorage.setItem("whisperLocal.tagFilter", activeTagFilter);
  };
  const setCollectionFilter = (collection) => {
    setLibraryFilters(collection, activeTagFilter);
  };
  const setTagFilter = (tag) => {
    setLibraryFilters(activeCollectionFilter, tag);
  };
  const adjustCollectionCount = (collection, delta) => {
    if (!collection) return;
    const button = getCollectionButtons().find((item) => item.dataset.collectionFilter === collection);
    const countEl = button && button.querySelector("strong");
    if (!countEl) return;
    const nextCount = Math.max(0, Number(countEl.textContent || 0) + delta);
    countEl.textContent = String(nextCount);
  };
  const ensureCollectionButton = (collection) => {
    if (!collectionFilter || !collection || getCollectionButtons().some((item) => item.dataset.collectionFilter === collection)) return;
    const button = document.createElement("button");
    const label = document.createElement("span");
    const count = document.createElement("strong");
    button.className = "collection-filter__button";
    button.type = "button";
    button.dataset.collectionFilter = collection;
    button.setAttribute("aria-pressed", "false");
    label.textContent = collection;
    count.textContent = "0";
    button.append(label, count);
    button.addEventListener("click", () => setCollectionFilter(collection));
    collectionFilter.appendChild(button);
  };

  if (collectionFilter) {
    getCollectionButtons().forEach((button) => {
      button.addEventListener("click", () => setCollectionFilter(button.dataset.collectionFilter || "all"));
    });
  }

  if (tagFilter) {
    getTagButtons().forEach((button) => {
      button.addEventListener("click", () => setTagFilter(button.dataset.tagFilter || "all"));
    });
  }

  setLibraryFilters(activeCollectionFilter, activeTagFilter);

  const setActiveTab = (targetId) => {
    tabs.forEach((item) => item.classList.toggle("is-active", item.dataset.tabTarget === targetId));
    panes.forEach((pane) => pane.classList.toggle("is-active", pane.id === targetId));
    document.body.dataset.activePane = targetId;
  };

  document.body.dataset.activePane = document.querySelector(".pane.is-active")?.id || "transcript-pane";

  const setTranscriptDensity = (density) => {
    transcriptDensity = density === "compact" ? "compact" : "comfortable";
    if (segmentList) {
      segmentList.classList.toggle("is-compact", transcriptDensity === "compact");
    }
    densityButtons.forEach((button) => {
      const isActive = button.dataset.density === transcriptDensity;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
    window.localStorage.setItem("whisperLocal.transcriptDensity", transcriptDensity);
  };

  setTranscriptDensity(transcriptDensity);

  densityButtons.forEach((button) => {
    button.addEventListener("click", () => setTranscriptDensity(button.dataset.density));
  });

  const setPlayingState = (isPlaying) => {
    document.body.classList.toggle("is-playing", isPlaying);
  };

  const syncActiveSegment = (timeSeconds) => {
    let activeRow = null;
    waveformSegments.forEach((bar) => {
      const start = Number(bar.dataset.waveStart || 0);
      const end = Number(bar.dataset.waveEnd || 0);
      bar.classList.toggle("is-played", end <= timeSeconds);
      bar.classList.toggle("is-active", timeSeconds >= start && timeSeconds < end);
    });
    segmentRows.forEach((row) => {
      const start = Number(row.dataset.start || 0);
      const end = Number(row.dataset.end || 0);
      const isActive = timeSeconds >= start && timeSeconds < end;
      row.classList.toggle("is-active", isActive);
      if (isActive) activeRow = row;
    });
    let activeFragment = null;
    segmentFragments.forEach((fragment) => {
      const start = Number(fragment.dataset.start || 0);
      const end = Number(fragment.dataset.end || 0);
      const isActive = timeSeconds >= start && timeSeconds < end;
      fragment.classList.toggle("is-active", isActive);
      if (isActive) activeFragment = fragment;
    });
    if (activeRow && playerNowText) {
      const textEl = activeRow.querySelector("p");
      const timeEl = activeRow.querySelector(".segment-time");
      playerNowText.textContent = activeFragment ? activeFragment.textContent.trim() : textEl ? textEl.textContent.trim() : "";
      if (playerNowTime) playerNowTime.textContent = activeFragment ? activeFragment.dataset.startLabel || "" : timeEl ? timeEl.textContent.trim() : "";
      if (playerNow) playerNow.classList.add("has-segment");
    } else if (!activeRow && playerNowText && titleEl) {
      playerNowText.textContent = titleEl.textContent || "";
      if (playerNowTime) playerNowTime.textContent = "";
      if (playerNow) playerNow.classList.remove("has-segment");
    }
    const isFiltering = Boolean(search && search.value.trim());
    if (activeRow && activeRow !== lastActiveSegment && followPlayback && !isFiltering) {
      activeRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
      lastActiveSegment = activeRow;
    }
  };

  const renderFollowPlayback = () => {
    if (!followPlaybackToggle) return;
    followPlaybackToggle.classList.toggle("is-active", followPlayback);
    followPlaybackToggle.setAttribute("aria-pressed", String(followPlayback));
  };

  renderFollowPlayback();

  if (followPlaybackToggle) {
    followPlaybackToggle.addEventListener("click", () => {
      followPlayback = !followPlayback;
      window.localStorage.setItem("whisperLocal.followPlayback", String(followPlayback));
      renderFollowPlayback();
      if (followPlayback && audio) {
        syncActiveSegment(audio.currentTime || 0);
      }
    });
  }

  const askForConfirmation = ({ title, message, confirmLabel = "Delete" }) =>
    new Promise((resolve) => {
      if (!confirmModal || !confirmModalTitle || !confirmModalMessage || !confirmModalCancel || !confirmModalConfirm) {
        resolve(window.confirm(message));
        return;
      }

      confirmModalTitle.textContent = title;
      confirmModalMessage.textContent = message;
      confirmModalConfirm.textContent = confirmLabel;
      confirmModal.hidden = false;

      const cleanup = (result) => {
        confirmModal.hidden = true;
        confirmModalCancel.removeEventListener("click", onCancel);
        confirmModalConfirm.removeEventListener("click", onConfirm);
        confirmModal.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKeydown);
        resolve(result);
      };

      const onCancel = () => cleanup(false);
      const onConfirm = () => cleanup(true);
      const onBackdrop = (event) => {
        if (event.target === confirmModal) cleanup(false);
      };
      const onKeydown = (event) => {
        if (event.key === "Escape") cleanup(false);
      };

      confirmModalCancel.addEventListener("click", onCancel);
      confirmModalConfirm.addEventListener("click", onConfirm);
      confirmModal.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKeydown);
    });

  if (audio && currentTime) {
    const syncProgress = () => {
      if (!progress) return;
      const duration = Number.isFinite(audio.duration) ? audio.duration : Number(progress.max || 0);
      if (duration > 0) {
        progress.max = String(duration);
        progress.value = String(audio.currentTime || 0);
        const percent = ((audio.currentTime || 0) / duration) * 100;
        progress.style.setProperty("--progress", `${percent}%`);
      } else {
        progress.value = "0";
        progress.style.setProperty("--progress", "0%");
      }
    };

    audio.addEventListener("loadedmetadata", () => {
      if (durationTime) durationTime.textContent = formatTime(audio.duration);
      setWaveformDuration(audio.duration);
      renderDecodedWaveform();
      syncProgress();
      syncActiveSegment(audio.currentTime || 0);
    });

    audio.addEventListener("timeupdate", () => {
      currentTime.textContent = formatTime(audio.currentTime);
      syncProgress();
      syncActiveSegment(audio.currentTime);
    });

    audio.addEventListener("ended", () => {
      if (toggle) toggle.textContent = "▶";
      setPlayingState(false);
    });

    audio.addEventListener("play", () => setPlayingState(true));
    audio.addEventListener("pause", () => setPlayingState(false));

    if (toggle) {
      toggle.addEventListener("click", () => {
        if (audio.paused) {
          audio.play();
          toggle.textContent = "❚❚";
        } else {
          audio.pause();
          toggle.textContent = "▶";
        }
      });
    }

    if (progress) {
      progress.addEventListener("input", () => {
        audio.currentTime = Number(progress.value || 0);
        currentTime.textContent = formatTime(audio.currentTime);
        syncProgress();
        syncActiveSegment(audio.currentTime);
      });
    }

    waveformSegments.forEach((bar) => {
      bar.addEventListener("click", () => {
        audio.currentTime = Number(bar.dataset.waveStart || 0);
        currentTime.textContent = formatTime(audio.currentTime);
        syncProgress();
        syncActiveSegment(audio.currentTime);
      });
    });

    document.querySelectorAll(".segment-play").forEach((button) => {
      button.addEventListener("click", () => {
        const start = Number(button.dataset.start || 0);
        audio.currentTime = start;
        if (appSettings.autoplay_on_seek) {
          audio.play();
        }
        currentTime.textContent = formatTime(audio.currentTime);
        syncProgress();
        syncActiveSegment(audio.currentTime);
        if (toggle) toggle.textContent = appSettings.autoplay_on_seek ? "❚❚" : "▶";
      });
    });

    segmentFragments.forEach((fragment) => {
      fragment.addEventListener("click", (event) => {
        event.stopPropagation();
        audio.currentTime = Number(fragment.dataset.start || 0);
        if (appSettings.autoplay_on_seek) {
          audio.play();
        }
        currentTime.textContent = formatTime(audio.currentTime);
        syncProgress();
        syncActiveSegment(audio.currentTime);
        if (toggle) toggle.textContent = appSettings.autoplay_on_seek ? "❚❚" : "▶";
      });
    });

    segmentRows.forEach((row) => {
      row.addEventListener("click", (event) => {
        if (
          event.target instanceof HTMLElement &&
          event.target.closest(".segment-play, .segment-fragment, .segment-tools, .segment-editor, .segment-speaker-editor")
        ) {
          return;
        }
        audio.currentTime = Number(row.dataset.start || 0);
        currentTime.textContent = formatTime(audio.currentTime);
        syncProgress();
        syncActiveSegment(audio.currentTime);
      });
    });

    if (durationTime && (!durationTime.textContent || durationTime.textContent.endsWith("s"))) {
      durationTime.textContent = formatTime(Number(progress && progress.max ? progress.max : 0));
    }
    syncProgress();
    syncActiveSegment(audio.currentTime || 0);
    setPlayingState(!audio.paused);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      setActiveTab(tab.dataset.tabTarget);
    });
  });

  if (search) {
    const allSegments = Array.from(document.querySelectorAll(".segment"));
    const getSummaryCards = () => Array.from(document.querySelectorAll(".summary-card"));
    let searchMatches = [];
    let activeSearchIndex = -1;
    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const getSearchTextEl = (item) => item.querySelector("p") || item;
    const getSearchItems = () => (searchScope === "summary" ? getSummaryCards() : allSegments);
    const getInactiveSearchItems = () => (searchScope === "summary" ? allSegments : getSummaryCards());
    const getSegmentSpeaker = (item) => {
      const label = item.querySelector("[data-segment-speaker-label]");
      return label && !label.hidden ? label.textContent.trim() : "";
    };
    const clearHighlight = (item) => {
      const textEl = getSearchTextEl(item);
      if (!textEl || textEl.dataset.originalText === undefined) return;
      textEl.textContent = textEl.dataset.originalText;
    };
    const clearActiveSearchHit = () => {
      allSegments.forEach((segment) => segment.classList.remove("is-search-active"));
      getSummaryCards().forEach((card) => card.classList.remove("is-search-active"));
    };
    const renderSearchScope = () => {
      searchScope = searchScope === "summary" ? "summary" : "transcript";
      searchScopeButtons.forEach((button) => {
        const isActive = button.dataset.searchScope === searchScope;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      search.placeholder = searchScope === "summary" ? "Search summary..." : "Search transcript...";
      if (speakerFilter) speakerFilter.disabled = searchScope === "summary";
      window.localStorage.setItem("whisperLocal.searchScope", searchScope);
    };
    const updateSearchControls = () => {
      const hasMatches = searchMatches.length > 0;
      const speakerFiltered = speakerFilter && !speakerFilter.disabled && speakerFilter.value !== "all";
      if (searchPrevious) searchPrevious.disabled = !hasMatches;
      if (searchNext) searchNext.disabled = !hasMatches;
      if (searchCount) {
        if (!search.value.trim() && !speakerFiltered) {
          searchCount.textContent = "";
        } else if (hasMatches) {
          searchCount.textContent = `${activeSearchIndex + 1} of ${searchMatches.length} ${searchScope} matches`;
        } else {
          searchCount.textContent = "0 matches";
        }
      }
    };
    const focusSearchHit = (index) => {
      if (!searchMatches.length) {
        activeSearchIndex = -1;
        clearActiveSearchHit();
        updateSearchControls();
        return;
      }
      activeSearchIndex = (index + searchMatches.length) % searchMatches.length;
      clearActiveSearchHit();
      const segment = searchMatches[activeSearchIndex];
      segment.classList.add("is-search-active");
      segment.scrollIntoView({ block: "center", behavior: "smooth" });
      updateSearchControls();
    };
    const moveSearchHit = (delta) => {
      if (!searchMatches.length) return;
      focusSearchHit(activeSearchIndex + delta);
    };
    const highlightMatch = (item, query) => {
      const textEl = getSearchTextEl(item);
      if (!textEl) return;
      const original = textEl.dataset.originalText || textEl.textContent;
      textEl.dataset.originalText = original;
      textEl.textContent = "";
      if (!query) {
        textEl.textContent = original;
        return;
      }

      const pattern = new RegExp(`(${escapeRegExp(query)})`, "ig");
      const parts = original.split(pattern);
      parts.forEach((part) => {
        if (!part) return;
        if (part.toLowerCase() === query.toLowerCase()) {
          const mark = document.createElement("mark");
          mark.textContent = part;
          textEl.appendChild(mark);
        } else {
          textEl.appendChild(document.createTextNode(part));
        }
      });
    };
    const renderSearch = () => {
      const query = search.value.trim().toLowerCase();
      const speakerValue = speakerFilter && !speakerFilter.disabled ? speakerFilter.value : "all";
      searchMatches = [];
      clearActiveSearchHit();
      getInactiveSearchItems().forEach((item) => {
        item.hidden = false;
        clearHighlight(item);
      });
      if (query || (searchScope === "transcript" && speakerValue !== "all")) {
        setActiveTab(searchScope === "summary" ? "summary-pane" : "transcript-pane");
      }
      getSearchItems().forEach((item) => {
        const textEl = getSearchTextEl(item);
        const haystack = (textEl && (textEl.dataset.originalText || textEl.textContent) || item.textContent).toLowerCase();
        const speakerMatch = searchScope !== "transcript" || speakerValue === "all" || getSegmentSpeaker(item) === speakerValue;
        const isMatch = (!query || haystack.includes(query)) && speakerMatch;
        item.hidden = !isMatch;
        if ((query || speakerValue !== "all") && isMatch) {
          searchMatches.push(item);
          if (query) highlightMatch(item, query);
        } else {
          clearHighlight(item);
        }
      });
      if ((query || speakerValue !== "all") && searchMatches.length) {
        focusSearchHit(0);
      } else {
        activeSearchIndex = -1;
        updateSearchControls();
      }
      if (!query) {
        syncActiveSegment(audio ? audio.currentTime : 0);
      }
    };

    search.addEventListener("input", renderSearch);
    search.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      moveSearchHit(event.shiftKey ? -1 : 1);
    });
    searchScopeButtons.forEach((button) => {
      button.addEventListener("click", () => {
        searchScope = button.dataset.searchScope;
        renderSearchScope();
        renderSearch();
      });
    });
    if (searchPrevious) searchPrevious.addEventListener("click", () => moveSearchHit(-1));
    if (searchNext) searchNext.addEventListener("click", () => moveSearchHit(1));
    if (speakerFilter) speakerFilter.addEventListener("change", renderSearch);
    renderSearchScope();
    updateSearchControls();
  }

  const getFocusableElements = (root) => {
    if (!root) return [];
    return Array.from(
      root.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((element) => element instanceof HTMLElement && element.offsetParent !== null);
  };
  let uploadPanelLastFocus = null;

  const setBackgroundInert = (isInert) => {
    [sidebar, detailPanel, settingsWorkspace].forEach((element) => {
      if (!element) return;
      if (isInert) {
        element.setAttribute("inert", "");
        element.setAttribute("aria-hidden", "true");
      } else {
        element.removeAttribute("inert");
        element.removeAttribute("aria-hidden");
      }
    });
  };

  const setUploadPanelOpen = (isOpen) => {
    if (!uploadPanel || !contextBackdrop) return;
    if (isOpen) {
      uploadPanelLastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setWorkspaceMode("history");
    }
    uploadPanel.hidden = !isOpen;
    contextBackdrop.hidden = !isOpen;
    uploadPanel.classList.toggle("is-open", isOpen);
    uploadPanel.setAttribute("role", "dialog");
    uploadPanel.setAttribute("aria-modal", String(isOpen));
    document.body.classList.toggle("is-upload-open", isOpen);
    setBackgroundInert(isOpen);
    if (isOpen) {
      window.setTimeout(() => {
        const firstFocusable = getFocusableElements(uploadPanel)[0];
        (fileInput || firstFocusable || uploadPanel).focus();
      }, 80);
    } else if (uploadPanelLastFocus && document.contains(uploadPanelLastFocus)) {
      uploadPanelLastFocus.focus();
      uploadPanelLastFocus = null;
    }
  };

  openUploadButtons.forEach((button) => {
    button.addEventListener("click", () => setUploadPanelOpen(true));
  });

  if (closeUploadPanel) {
    closeUploadPanel.addEventListener("click", () => setUploadPanelOpen(false));
  }

  if (contextBackdrop) {
    contextBackdrop.addEventListener("click", () => setUploadPanelOpen(false));
  }

  if (uploadPanel && !uploadPanel.hidden) {
    setUploadPanelOpen(true);
  }

  if (fileInput && fileNameLabel) {
    const renderFileName = (files) => {
      const selectedFiles = Array.from(files || []);
      if (!selectedFiles.length) {
        fileNameLabel.textContent = "Supported formats: opus, oga, ogg, mp3, wav, m4a, flac, webm";
        return;
      }
      if (selectedFiles.length === 1) {
        fileNameLabel.textContent = `Selected: ${selectedFiles[0].name}`;
        return;
      }
      fileNameLabel.textContent = `Selected: ${selectedFiles.length} files`;
    };

    const assignFiles = (files) => {
      const selectedFiles = Array.from(files || []);
      if (!selectedFiles.length) return;
      const transfer = new DataTransfer();
      selectedFiles.forEach((file) => transfer.items.add(file));
      fileInput.files = transfer.files;
      renderFileName(fileInput.files);
      setUploadPanelOpen(true);
    };

    fileInput.addEventListener("change", () => {
      renderFileName(fileInput.files);
    });

    if (uploadCard) {
      ["dragenter", "dragover"].forEach((eventName) => {
        uploadCard.addEventListener(eventName, (event) => {
          event.preventDefault();
          uploadCard.classList.add("is-dragover");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        uploadCard.addEventListener(eventName, (event) => {
          event.preventDefault();
          uploadCard.classList.remove("is-dragover");
        });
      });

      uploadCard.addEventListener("drop", (event) => {
        assignFiles(event.dataTransfer && event.dataTransfer.files);
      });
    }

    let dragDepth = 0;
    document.addEventListener("dragenter", (event) => {
      if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes("Files")) return;
      dragDepth += 1;
      document.body.classList.add("is-dragging-file");
      setUploadPanelOpen(true);
    });

    document.addEventListener("dragover", (event) => {
      if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes("Files")) return;
      event.preventDefault();
    });

    document.addEventListener("dragleave", () => {
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) {
        document.body.classList.remove("is-dragging-file");
      }
    });

    document.addEventListener("drop", (event) => {
      if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes("Files")) return;
      event.preventDefault();
      dragDepth = 0;
      document.body.classList.remove("is-dragging-file");
      assignFiles(event.dataTransfer.files);
    });
  }

  if (transcribeForm && transcribeButton) {
    transcribeForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (transcribeForm.dataset.submitting === "true") {
        return;
      }
      const selectedFiles = Array.from((fileInput && fileInput.files) || []);
      if (!selectedFiles.length) {
        if (transcribeStatus) transcribeStatus.textContent = "Choose at least one audio file.";
        return;
      }
      transcribeForm.dataset.submitting = "true";
      transcribeForm.classList.add("is-submitting");
      transcribeButton.disabled = true;
      transcribeButton.textContent = selectedFiles.length === 1 ? "Starting import..." : `Starting ${selectedFiles.length} imports...`;
      if (transcribeStatus) {
        transcribeStatus.textContent =
          selectedFiles.length === 1
            ? `Queueing local transcription for ${selectedFiles[0].name}.`
            : `Queueing ${selectedFiles.length} local transcriptions.`;
      }
      try {
        const response = await fetch(transcribeForm.action, {
          method: "POST",
          body: new FormData(transcribeForm),
          headers: { "X-Requested-With": "fetch" }
        });
        const contentType = response.headers.get("Content-Type") || "";
        const payload = contentType.includes("application/json") ? await response.json() : null;
        if (!response.ok || !payload || !payload.ok) {
          throw new Error((payload && payload.error) || "Import could not be started.");
        }
        window.location.href = payload.redirect_url;
      } catch (error) {
        transcribeForm.dataset.submitting = "false";
        transcribeForm.classList.remove("is-submitting");
        transcribeButton.disabled = false;
        transcribeButton.textContent = "Transcribe locally";
        if (transcribeStatus) transcribeStatus.textContent = error.message || "Import could not be started.";
      }
    });
  }

  if (copyButton && state) {
    copyButton.addEventListener("click", async () => {
      try {
        await copyTextToClipboard(state.transcriptText || "");
        copyButton.textContent = "✓";
        window.setTimeout(() => {
          copyButton.textContent = "⧉";
        }, 1200);
      } catch (error) {
        console.error(error);
      }
    });
  }

  if (copyPlainTextButton && plainTextOutput) {
    copyPlainTextButton.addEventListener("click", async () => {
      const text = plainTextOutput.value || "";
      try {
        await copyTextToClipboard(text);
        copyPlainTextButton.textContent = "Copied";
        if (plainTextStatus) plainTextStatus.textContent = "Copied text without timestamps.";
        window.setTimeout(() => {
          copyPlainTextButton.textContent = "Copy plain text";
          if (plainTextStatus) plainTextStatus.textContent = "";
        }, 1400);
      } catch (error) {
        if (plainTextStatus) plainTextStatus.textContent = "Copy failed.";
        console.error(error);
      }
    });
  }

  if (copySummaryButton && summaryCards) {
    copySummaryButton.addEventListener("click", async () => {
      const text = Array.from(summaryCards.querySelectorAll(".summary-card"))
        .map((item) => item.textContent.trim())
        .filter(Boolean)
        .join("\n");
      try {
        await copyTextToClipboard(text);
        copySummaryButton.textContent = "Copied";
        window.setTimeout(() => {
          copySummaryButton.textContent = "Copy summary";
        }, 1400);
      } catch (error) {
        console.error(error);
      }
    });
  }

  if (renameButton && titleEl && state) {
    renameButton.addEventListener("click", async () => {
      const nextTitle = window.prompt("Rename title", titleEl.textContent || "");
      if (!nextTitle) return;
      const response = await fetch(`/transcripts/${state.recordId}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: nextTitle })
      });
      const payload = await response.json();
      if (payload.ok) {
        titleEl.textContent = payload.title;
        titleEl.title = payload.title;
        const sidebarTitle = document.querySelector(`[data-record-title="${state.recordId}"]`);
        if (sidebarTitle) sidebarTitle.textContent = payload.title;
      }
    });
  }

  if (collectionEditor && collectionInput && state) {
    collectionEditor.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = await fetch(`/transcripts/${state.recordId}/collection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ collection: collectionInput.value })
      });
      const payload = await response.json();
      if (!payload.ok) return;
      const nextCollection = payload.collection || "Inbox";
      const row = document.querySelector(`[data-record-row="${state.recordId}"]`);
      const previousCollection = row ? row.dataset.collection : "";
      collectionInput.value = nextCollection;
      document.querySelectorAll(`[data-record-collection-label="${state.recordId}"]`).forEach((label) => {
        label.textContent = nextCollection;
      });
      if (row) row.dataset.collection = nextCollection;
      if (previousCollection !== nextCollection) {
        ensureCollectionButton(nextCollection);
        adjustCollectionCount(previousCollection, -1);
        adjustCollectionCount(nextCollection, 1);
      }
      setCollectionFilter(activeCollectionFilter);
    });
  }

  if (tagEditor && tagsInput && state) {
    tagEditor.addEventListener("submit", async (event) => {
      event.preventDefault();
      const response = await fetch(`/transcripts/${state.recordId}/tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags: tagsInput.value.split(",") })
      });
      const payload = await response.json();
      if (payload.ok) {
        tagsInput.value = payload.tags.join(", ");
        const row = document.querySelector(`[data-record-row="${state.recordId}"]`);
        if (row) row.dataset.tags = payload.tags.join("|");
        setLibraryFilters(activeCollectionFilter, activeTagFilter);
      }
    });
  }

  if (notesEditor && notesInput && state) {
    notesEditor.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (notesStatus) notesStatus.textContent = "Saving...";
      const response = await fetch(`/transcripts/${state.recordId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notesInput.value })
      });
      const payload = await response.json();
      if (payload.ok) {
        notesInput.value = payload.notes || "";
        if (notesStatus) notesStatus.textContent = "Saved";
        window.setTimeout(() => {
          if (notesStatus && notesStatus.textContent === "Saved") notesStatus.textContent = "";
        }, 1400);
      } else if (notesStatus) {
        notesStatus.textContent = payload.error || "Could not save notes.";
      }
    });
  }

  document.querySelectorAll("[data-speaker-segment]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!state) return;
      const segment = button.closest(".segment");
      const speakerLabel = segment && segment.querySelector("[data-segment-speaker-label]");
      if (!segment || !speakerLabel || segment.classList.contains("is-labeling-speaker")) return;
      const editor = document.createElement("form");
      const input = document.createElement("input");
      const save = document.createElement("button");
      const clear = document.createElement("button");
      const cancel = document.createElement("button");

      editor.className = "segment-speaker-editor";
      input.type = "text";
      input.value = speakerLabel.hidden ? "" : speakerLabel.textContent.trim();
      input.placeholder = "Speaker name";
      input.setAttribute("aria-label", "Speaker name");
      save.className = "secondary-action";
      save.type = "submit";
      save.textContent = "Save";
      clear.className = "secondary-action";
      clear.type = "button";
      clear.textContent = "Clear";
      cancel.className = "secondary-action";
      cancel.type = "button";
      cancel.textContent = "Cancel";
      editor.append(input, save, clear, cancel);

      const closeEditor = () => {
        editor.remove();
        button.hidden = false;
        segment.classList.remove("is-labeling-speaker");
      };
      const saveSpeaker = async (speaker) => {
        save.disabled = true;
        clear.disabled = true;
        cancel.disabled = true;
        try {
          const response = await fetch(`/transcripts/${state.recordId}/segments/${button.dataset.speakerSegment}/speaker`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ speaker })
          });
          const payload = await response.json();
          if (!payload.ok) throw new Error(payload.error || "Speaker update failed.");
          const nextSpeaker = (payload.segment && payload.segment.speaker) || "";
          speakerLabel.textContent = nextSpeaker;
          speakerLabel.hidden = !nextSpeaker;
          ensureSpeakerOption(nextSpeaker);
          closeEditor();
        } catch (error) {
          console.error(error);
          save.disabled = false;
          clear.disabled = false;
          cancel.disabled = false;
        }
      };

      cancel.addEventListener("click", closeEditor);
      clear.addEventListener("click", () => saveSpeaker(""));
      editor.addEventListener("submit", (event) => {
        event.preventDefault();
        saveSpeaker(input.value);
      });

      segment.classList.add("is-labeling-speaker");
      button.hidden = true;
      segment.appendChild(editor);
      input.focus();
      input.select();
    });
  });

  document.querySelectorAll("[data-edit-segment]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!state) return;
      const segment = button.closest(".segment");
      const textEl = segment && segment.querySelector("p");
      if (!segment || !textEl || segment.classList.contains("is-editing")) return;
      const currentText = textEl.dataset.originalText || textEl.textContent || "";
      const editor = document.createElement("form");
      const textarea = document.createElement("textarea");
      const actions = document.createElement("div");
      const save = document.createElement("button");
      const cancel = document.createElement("button");
      const status = document.createElement("span");

      editor.className = "segment-editor";
      textarea.value = currentText;
      textarea.rows = 3;
      textarea.setAttribute("aria-label", "Segment text");
      actions.className = "segment-editor__actions";
      save.className = "secondary-action";
      save.type = "submit";
      save.textContent = "Save";
      cancel.className = "secondary-action";
      cancel.type = "button";
      cancel.textContent = "Cancel";
      status.className = "segment-editor__status";
      status.setAttribute("aria-live", "polite");
      actions.append(save, cancel, status);
      editor.append(textarea, actions);

      const closeEditor = () => {
        editor.remove();
        textEl.hidden = false;
        button.hidden = false;
        segment.classList.remove("is-editing");
      };

      cancel.addEventListener("click", closeEditor);
      editor.addEventListener("submit", async (event) => {
        event.preventDefault();
        const nextText = textarea.value.trim();
        if (!nextText || nextText === currentText.trim()) {
          closeEditor();
          return;
        }
        save.disabled = true;
        cancel.disabled = true;
        status.textContent = "Saving...";
        try {
          const response = await fetch(`/transcripts/${state.recordId}/segments/${button.dataset.editSegment}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: nextText })
          });
          const payload = await response.json();
          if (!payload.ok) throw new Error(payload.error || "Segment update failed.");
          textEl.textContent = nextText;
          textEl.dataset.originalText = nextText;
          segment.dataset.text = nextText.toLowerCase();
          state.transcriptText = payload.transcript_text || state.transcriptText;
          if (plainTextOutput) plainTextOutput.value = state.transcriptText || "";
          closeEditor();
        } catch (error) {
          save.disabled = false;
          cancel.disabled = false;
          status.textContent = error.message || "Could not save segment.";
        }
      });

      segment.classList.add("is-editing");
      textEl.hidden = true;
      button.hidden = true;
      textEl.after(editor);
      textarea.focus();
      textarea.select();
    });
  });

  document.querySelectorAll("[data-segment-flag]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state) return;
      const segment = button.closest(".segment");
      if (!segment) return;
      const flag = button.dataset.segmentFlag;
      const nextValue = button.getAttribute("aria-pressed") !== "true";
      button.disabled = true;
      try {
        const response = await fetch(`/transcripts/${state.recordId}/segments/${segment.dataset.segmentId}/flags`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [flag]: nextValue })
        });
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Segment flag update failed.");
        const segmentPayload = payload.segment || {};
        const isBookmarked = Boolean(segmentPayload.bookmarked);
        const isHighlighted = Boolean(segmentPayload.highlighted);
        segment.dataset.bookmarked = String(isBookmarked);
        segment.dataset.highlighted = String(isHighlighted);
        segment.classList.toggle("is-bookmarked", isBookmarked);
        segment.classList.toggle("is-highlighted", isHighlighted);
        segment.querySelectorAll("[data-segment-flag]").forEach((flagButton) => {
          const isActive = flagButton.dataset.segmentFlag === "bookmarked" ? isBookmarked : isHighlighted;
          flagButton.setAttribute("aria-pressed", String(isActive));
        });
      } catch (error) {
        console.error(error);
      } finally {
        button.disabled = false;
      }
    });
  });

  const deleteRecord = async (recordId) => {
    const response = await fetch(`/transcripts/${recordId}/delete`, { method: "POST" });
    const payload = await response.json();
    if (!payload.ok) return;
    window.location.href = payload.redirect_url;
  };

  if (deleteButton && state) {
    deleteButton.addEventListener("click", async () => {
      const confirmed =
        !appSettings.confirm_before_delete ||
        (await askForConfirmation({
          title: "Delete transcription?",
          message: "This will remove the transcript from history and delete its saved audio and text files.",
          confirmLabel: "Delete"
        }));
      if (!confirmed) return;
      await deleteRecord(state.recordId);
    });
  }

  document.querySelectorAll("[data-delete-record]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const recordId = button.dataset.deleteRecord;
      const confirmed =
        !appSettings.confirm_before_delete ||
        (await askForConfirmation({
          title: "Delete from history?",
          message: "This will remove the transcript from history and delete its saved files.",
          confirmLabel: "Delete"
        }));
      if (!confirmed) return;
      await deleteRecord(recordId);
    });
  });

  if (deleteLocalDataButton) {
    deleteLocalDataButton.addEventListener("click", async () => {
      const confirmed = await askForConfirmation({
        title: "Delete saved transcripts?",
        message: "This removes every saved transcript and uploaded audio file from this app's local data folder. Model caches and app settings stay in place.",
        confirmLabel: "Delete all"
      });
      if (!confirmed) return;
      const response = await fetch("/local-data/delete", { method: "POST" });
      const payload = await response.json();
      if (payload.ok) {
        window.location.href = payload.redirect_url;
      }
    });
  }

  if (refreshSummaryButton && state) {
    const setSummaryState = (status, message) => {
      if (!summaryState) return;
      summaryState.textContent = message;
      summaryState.className = `summary-state summary-state--${status}`;
      summaryState.dataset.status = status;
    };

    refreshSummaryButton.addEventListener("click", async () => {
      const isRetry = summaryState && summaryState.dataset.status === "error";
      refreshSummaryButton.disabled = true;
      refreshSummaryButton.textContent = "Refreshing...";
      setSummaryState(isRetry ? "generating" : "generating", isRetry ? "Retrying locally" : "Generating locally");
      if (summaryCards) {
        summaryCards.setAttribute("aria-busy", "true");
        summaryCards.innerHTML = '<article class="summary-card summary-card--loading">Refreshing summary...</article>';
      }
      try {
        const response = await fetch(`/transcripts/${state.recordId}/resummarize`, { method: "POST" });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || "Summary refresh failed.");
        }
        if (payload.ok && summaryCards && summaryProviderLabel) {
          summaryCards.innerHTML = "";
          const summaryItems = payload.summary && payload.summary.length ? payload.summary : ["No summary available yet."];
          summaryItems.forEach((item) => {
            const article = document.createElement("article");
            article.className = "summary-card";
            article.textContent = item;
            summaryCards.appendChild(article);
          });
          summaryProviderLabel.textContent = `Generated with: ${summaryProviderNames[payload.provider] || payload.provider}`;
          setSummaryState(
            payload.provider === "extractive" ? "fallback" : "ready",
            payload.provider === "extractive" ? "Fallback summary ready" : "Local model summary ready"
          );
          if (payload.title && titleEl) {
            titleEl.textContent = payload.title;
            titleEl.title = payload.title;
            const sidebarTitle = document.querySelector(`[data-record-title="${state.recordId}"]`);
            if (sidebarTitle) sidebarTitle.textContent = payload.title;
          }
          setActiveTab("summary-pane");
        }
      } catch (error) {
        if (summaryCards) {
          summaryCards.innerHTML = "";
          const article = document.createElement("article");
          article.className = "summary-card summary-card--error";
          article.textContent = error.message || "Summary refresh failed.";
          summaryCards.appendChild(article);
        }
        setSummaryState("error", "Summary failed");
      } finally {
        if (summaryCards) {
          summaryCards.removeAttribute("aria-busy");
        }
        refreshSummaryButton.disabled = false;
        refreshSummaryButton.textContent = "Refresh summary";
      }
    });
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const isTyping =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      target instanceof HTMLSelectElement ||
      (target instanceof HTMLElement && target.isContentEditable);
    const modalOpen = confirmModal && !confirmModal.hidden;
    const uploadOpen = uploadPanel && !uploadPanel.hidden;

    if (modalOpen) return;

    if (uploadOpen && event.key === "Tab") {
      const focusable = getFocusableElements(uploadPanel);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }

    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      setUploadPanelOpen(true);
      return;
    }

    if (event.key === "Escape" && uploadOpen) {
      event.preventDefault();
      setUploadPanelOpen(false);
      return;
    }

    if (event.key === "/" && search && !isTyping) {
      event.preventDefault();
      search.focus();
      return;
    }

    if (!audio || isTyping) return;

    if (event.code === "Space") {
      event.preventDefault();
      if (toggle) {
        toggle.click();
      } else if (audio.paused) {
        audio.play();
      } else {
        audio.pause();
      }
      return;
    }

    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      const delta = event.key === "ArrowLeft" ? -5 : 5;
      const duration = Number.isFinite(audio.duration) ? audio.duration : Number(progress && progress.max ? progress.max : 0);
      audio.currentTime = Math.max(0, Math.min(duration || Number.MAX_SAFE_INTEGER, audio.currentTime + delta));
      if (currentTime) currentTime.textContent = formatTime(audio.currentTime);
      if (progress) {
        progress.value = String(audio.currentTime);
        const percent = duration > 0 ? (audio.currentTime / duration) * 100 : 0;
        progress.style.setProperty("--progress", `${percent}%`);
      }
      syncActiveSegment(audio.currentTime);
    }
  });
})();
