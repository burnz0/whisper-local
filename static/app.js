(function () {
  const state = window.APP_STATE || null;
  const jobState = window.APP_JOB_STATE || null;
  const audio = document.getElementById("audio-player");
  const toggle = document.getElementById("player-toggle");
  const currentTime = document.getElementById("current-time");
  const durationTime = document.getElementById("duration-time");
  const progress = document.getElementById("audio-progress");
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
  const renameButton = document.getElementById("rename-button");
  const deleteButton = document.getElementById("delete-button");
  const tagEditor = document.getElementById("tag-editor");
  const tagsInput = document.getElementById("tags-input");
  const refreshSummaryButton = document.getElementById("refresh-summary-button");
  const summaryCards = document.getElementById("summary-cards");
  const summaryProviderLabel = document.getElementById("summary-provider-label");
  const titleEl = document.getElementById("record-title");
  const jobStatus = document.getElementById("job-status");
  const jobStatusTitle = document.getElementById("job-status-title");
  const jobStatusMessage = document.getElementById("job-status-message");
  const transcribeForm = document.getElementById("transcribe-form");
  const transcribeButton = document.getElementById("transcribe-button");
  const transcribeStatus = document.getElementById("transcribe-status");
  const fileInput = document.getElementById("audio-file-input");
  const uploadCard = document.getElementById("upload-card");
  const uploadPanel = document.getElementById("upload-panel");
  const contextBackdrop = document.getElementById("context-backdrop");
  const closeUploadPanel = document.getElementById("close-upload-panel");
  const fileNameLabel = document.getElementById("selected-file-name");
  const openUploadButtons = document.querySelectorAll("[data-open-upload]");
  const searchCount = document.getElementById("segment-search-count");
  const sidebarNavButtons = document.querySelectorAll("[data-sidebar-target]");
  const sidebarPanels = document.querySelectorAll(".sidebar-panel");
  const confirmModal = document.getElementById("confirm-modal");
  const confirmModalTitle = document.getElementById("confirm-modal-title");
  const confirmModalMessage = document.getElementById("confirm-modal-message");
  const confirmModalCancel = document.getElementById("confirm-modal-cancel");
  const confirmModalConfirm = document.getElementById("confirm-modal-confirm");
  const appSettings = (state && state.settings) || { autoplay_on_seek: true, confirm_before_delete: true };
  const summaryProviderNames = {
    local_transformer: "Local German model",
    extractive: "Fallback extractive"
  };
  const segmentRows = Array.from(document.querySelectorAll(".segment[data-start]"));
  let lastActiveSegment = null;
  let followPlayback = window.localStorage.getItem("whisperLocal.followPlayback") !== "false";
  let transcriptDensity = window.localStorage.getItem("whisperLocal.transcriptDensity") || "comfortable";
  let searchScope = window.localStorage.getItem("whisperLocal.searchScope") || "transcript";
  const formatTime = (seconds) => {
    const total = Math.max(0, Math.floor(seconds || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };

  if (jobState && jobStatus) {
    const pollJob = async () => {
      try {
        const response = await fetch(`/jobs/${jobState.id}.json`);
        const payload = await response.json();
        if (!payload.ok) throw new Error(payload.error || "Job status unavailable.");
        const job = payload.job;
        if (jobStatusTitle) {
          jobStatusTitle.textContent =
            job.status === "failed" ? "Transcription failed" : job.status === "complete" ? "Transcription complete" : "Transcribing audio";
        }
        if (jobStatusMessage) {
          jobStatusMessage.textContent =
            job.status === "failed"
              ? job.error || "Transcription failed."
              : job.status === "complete"
                ? "Opening transcript..."
                : `Running locally with ${job.model}. ${job.source_name} is ${job.status}; no cloud upload occurs.`;
        }
        if (job.status === "complete" && payload.redirect_url) {
          window.location.href = payload.redirect_url;
          return;
        }
        if (job.status !== "failed") {
          window.setTimeout(pollJob, 1500);
        }
      } catch (error) {
        if (jobStatusTitle) jobStatusTitle.textContent = "Status unavailable";
        if (jobStatusMessage) jobStatusMessage.textContent = error.message || "Could not read job status.";
      }
    };
    window.setTimeout(pollJob, 800);
  }

  const setSidebarPanel = (targetId) => {
    sidebarPanels.forEach((panel) => {
      panel.hidden = panel.id !== targetId;
    });
    sidebarNavButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.sidebarTarget === targetId);
    });
    window.localStorage.setItem("whisperLocal.sidebarPanel", targetId);
  };

  if (sidebarNavButtons.length) {
    const savedPanel = window.localStorage.getItem("whisperLocal.sidebarPanel");
    const initialPanel = document.getElementById(savedPanel) ? savedPanel : "history-panel";
    setSidebarPanel(initialPanel);
    sidebarNavButtons.forEach((button) => {
      button.addEventListener("click", () => {
        setSidebarPanel(button.dataset.sidebarTarget);
      });
    });
  }

  const setActiveTab = (targetId) => {
    tabs.forEach((item) => item.classList.toggle("is-active", item.dataset.tabTarget === targetId));
    panes.forEach((pane) => pane.classList.toggle("is-active", pane.id === targetId));
  };

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
    segmentRows.forEach((row) => {
      const start = Number(row.dataset.start || 0);
      const end = Number(row.dataset.end || 0);
      const isActive = timeSeconds >= start && timeSeconds < end;
      row.classList.toggle("is-active", isActive);
      if (isActive) activeRow = row;
    });
    if (activeRow && playerNowText) {
      const textEl = activeRow.querySelector("p");
      const timeEl = activeRow.querySelector(".segment-time");
      playerNowText.textContent = textEl ? textEl.textContent.trim() : "";
      if (playerNowTime) playerNowTime.textContent = timeEl ? timeEl.textContent.trim() : "";
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

    segmentRows.forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target instanceof HTMLElement && event.target.closest(".segment-play")) return;
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
    const allSummaryCards = Array.from(document.querySelectorAll(".summary-card"));
    let searchMatches = [];
    let activeSearchIndex = -1;
    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const getSearchTextEl = (item) => item.querySelector("p") || item;
    const getSearchItems = () => (searchScope === "summary" ? allSummaryCards : allSegments);
    const getInactiveSearchItems = () => (searchScope === "summary" ? allSegments : allSummaryCards);
    const clearHighlight = (item) => {
      const textEl = getSearchTextEl(item);
      if (!textEl || textEl.dataset.originalText === undefined) return;
      textEl.textContent = textEl.dataset.originalText;
    };
    const clearActiveSearchHit = () => {
      allSegments.forEach((segment) => segment.classList.remove("is-search-active"));
      allSummaryCards.forEach((card) => card.classList.remove("is-search-active"));
    };
    const renderSearchScope = () => {
      searchScope = searchScope === "summary" ? "summary" : "transcript";
      searchScopeButtons.forEach((button) => {
        const isActive = button.dataset.searchScope === searchScope;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      search.placeholder = searchScope === "summary" ? "Search summary..." : "Search transcript...";
      window.localStorage.setItem("whisperLocal.searchScope", searchScope);
    };
    const updateSearchControls = () => {
      const hasMatches = searchMatches.length > 0;
      if (searchPrevious) searchPrevious.disabled = !hasMatches;
      if (searchNext) searchNext.disabled = !hasMatches;
      if (searchCount) {
        if (!search.value.trim()) {
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
      searchMatches = [];
      clearActiveSearchHit();
      getInactiveSearchItems().forEach((item) => {
        item.hidden = false;
        clearHighlight(item);
      });
      if (query) {
        setActiveTab(searchScope === "summary" ? "summary-pane" : "transcript-pane");
      }
      getSearchItems().forEach((item) => {
        const textEl = getSearchTextEl(item);
        const haystack = (textEl && (textEl.dataset.originalText || textEl.textContent) || item.textContent).toLowerCase();
        const isMatch = !query || haystack.includes(query);
        item.hidden = !isMatch;
        if (query && isMatch) {
          searchMatches.push(item);
          highlightMatch(item, query);
        } else {
          clearHighlight(item);
        }
      });
      if (query && searchMatches.length) {
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
    renderSearchScope();
    updateSearchControls();
  }

  const setUploadPanelOpen = (isOpen) => {
    if (!uploadPanel || !contextBackdrop) return;
    uploadPanel.hidden = !isOpen;
    contextBackdrop.hidden = !isOpen;
    uploadPanel.classList.toggle("is-open", isOpen);
    if (isOpen && fileInput) {
      window.setTimeout(() => fileInput.focus(), 80);
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

  if (fileInput && fileNameLabel) {
    const renderFileName = (file) => {
      fileNameLabel.textContent = file ? `Selected: ${file.name}` : "Supported formats: ogg, mp3, wav, m4a, flac, webm";
    };

    const assignFile = (file) => {
      if (!file) return;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      renderFileName(file);
      setUploadPanelOpen(true);
    };

    fileInput.addEventListener("change", () => {
      renderFileName(fileInput.files && fileInput.files[0]);
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
        const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        assignFile(file);
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
      assignFile(event.dataTransfer.files && event.dataTransfer.files[0]);
    });
  }

  if (transcribeForm && transcribeButton) {
    transcribeForm.addEventListener("submit", (event) => {
      if (transcribeForm.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }
      const file = fileInput && fileInput.files && fileInput.files[0];
      transcribeForm.dataset.submitting = "true";
      transcribeForm.classList.add("is-submitting");
      transcribeButton.disabled = true;
      transcribeButton.textContent = "Transcribing locally...";
      if (transcribeStatus) {
        transcribeStatus.textContent = file ? `Running local transcription for ${file.name}. No upload occurs.` : "Running local transcription.";
      }
    });
  }

  if (copyButton && state) {
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(state.transcriptText || "");
        copyButton.textContent = "✓";
        window.setTimeout(() => {
          copyButton.textContent = "⧉";
        }, 1200);
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
        const sidebarTitle = document.querySelector(`[data-record-title="${state.recordId}"]`);
        if (sidebarTitle) sidebarTitle.textContent = payload.title;
      }
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
      }
    });
  }

  document.querySelectorAll("[data-edit-segment]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state) return;
      const segment = button.closest(".segment");
      const textEl = segment && segment.querySelector("p");
      if (!segment || !textEl) return;
      const currentText = textEl.dataset.originalText || textEl.textContent || "";
      const nextText = window.prompt("Edit segment text", currentText);
      if (!nextText || nextText.trim() === currentText.trim()) return;
      const response = await fetch(`/transcripts/${state.recordId}/segments/${button.dataset.editSegment}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: nextText })
      });
      const payload = await response.json();
      if (!payload.ok) return;
      textEl.textContent = nextText.trim();
      textEl.dataset.originalText = nextText.trim();
      segment.dataset.text = nextText.trim().toLowerCase();
      state.transcriptText = payload.transcript_text || state.transcriptText;
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

  if (refreshSummaryButton && state) {
    refreshSummaryButton.addEventListener("click", async () => {
      refreshSummaryButton.disabled = true;
      refreshSummaryButton.textContent = "Refreshing...";
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
          if (payload.title && titleEl) {
            titleEl.textContent = payload.title;
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

    if (modalOpen) return;

    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      setUploadPanelOpen(true);
      return;
    }

    if (event.key === "Escape" && uploadPanel && !uploadPanel.hidden) {
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
