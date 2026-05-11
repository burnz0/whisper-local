(function () {
  const state = window.APP_STATE || null;
  const jobState = window.APP_JOB_STATE || null;
  const audio = document.getElementById("audio-player");
  const toggle = document.getElementById("player-toggle");
  const currentTime = document.getElementById("current-time");
  const durationTime = document.getElementById("duration-time");
  const progress = document.getElementById("audio-progress");
  const playerNow = document.getElementById("player-now");
  const search = document.getElementById("segment-search");
  const tabs = document.querySelectorAll(".tab");
  const panes = document.querySelectorAll(".pane");
  const copyButton = document.getElementById("copy-button");
  const renameButton = document.getElementById("rename-button");
  const deleteButton = document.getElementById("delete-button");
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
  const fileNameLabel = document.getElementById("selected-file-name");
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
            job.status === "failed" ? job.error || "Transcription failed." : job.status === "complete" ? "Opening transcript..." : `${job.source_name} is ${job.status}.`;
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
    if (activeRow && playerNow) {
      const textEl = activeRow.querySelector("p");
      playerNow.textContent = textEl ? textEl.textContent.trim() : "";
    } else if (!activeRow && playerNow && titleEl) {
      playerNow.textContent = titleEl.textContent || "";
    }
    const isFiltering = Boolean(search && search.value.trim());
    if (activeRow && activeRow !== lastActiveSegment && !isFiltering) {
      activeRow.scrollIntoView({ block: "nearest", behavior: "smooth" });
      lastActiveSegment = activeRow;
    }
  };

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
    const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const clearHighlight = (segment) => {
      const textEl = segment.querySelector("p");
      if (!textEl || textEl.dataset.originalText === undefined) return;
      textEl.textContent = textEl.dataset.originalText;
    };
    const highlightMatch = (segment, query) => {
      const textEl = segment.querySelector("p");
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
      let matches = 0;
      allSegments.forEach((segment) => {
        const textEl = segment.querySelector("p");
        const haystack = (textEl && (textEl.dataset.originalText || textEl.textContent) || segment.textContent).toLowerCase();
        const isMatch = !query || haystack.includes(query);
        segment.hidden = !isMatch;
        if (query && isMatch) {
          matches += 1;
          highlightMatch(segment, query);
        } else {
          clearHighlight(segment);
        }
      });
      if (searchCount) {
        searchCount.textContent = query ? `${matches} match${matches === 1 ? "" : "es"}` : "";
      }
      if (!query) {
        syncActiveSegment(audio ? audio.currentTime : 0);
      }
    };

    search.addEventListener("input", renderSearch);
  }

  if (fileInput && fileNameLabel) {
    const renderFileName = (file) => {
      fileNameLabel.textContent = file ? `Selected: ${file.name}` : "Supported formats: ogg, mp3, wav, m4a, flac, webm";
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
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        fileInput.files = transfer.files;
        renderFileName(file);
      });
    }
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
      transcribeButton.textContent = "Transcribing...";
      if (transcribeStatus) {
        transcribeStatus.textContent = file ? `Transcribing ${file.name}.` : "Transcribing audio.";
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
