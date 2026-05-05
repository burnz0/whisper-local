(function () {
  const state = window.APP_STATE || null;
  const audio = document.getElementById("audio-player");
  const toggle = document.getElementById("player-toggle");
  const currentTime = document.getElementById("current-time");
  const durationTime = document.getElementById("duration-time");
  const progress = document.getElementById("audio-progress");
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
  const fileInput = document.getElementById("audio-file-input");
  const uploadCard = document.getElementById("upload-card");
  const fileNameLabel = document.getElementById("selected-file-name");
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

  const setSidebarPanel = (targetId) => {
    sidebarPanels.forEach((panel) => {
      panel.hidden = panel.id !== targetId;
    });
    sidebarNavButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.sidebarTarget === targetId);
    });
  };

  if (sidebarNavButtons.length) {
    setSidebarPanel("history-panel");
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
    segmentRows.forEach((row) => {
      const start = Number(row.dataset.start || 0);
      const end = Number(row.dataset.end || 0);
      row.classList.toggle("is-active", timeSeconds >= start && timeSeconds < end);
    });
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
    const formatTime = (seconds) => {
      const total = Math.max(0, Math.floor(seconds || 0));
      const mins = Math.floor(total / 60);
      const secs = total % 60;
      return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
    };

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
    search.addEventListener("input", () => {
      const query = search.value.trim().toLowerCase();
      document.querySelectorAll(".segment").forEach((segment) => {
        const haystack = segment.dataset.text || segment.textContent.toLowerCase();
        segment.style.display = !query || haystack.includes(query) ? "" : "none";
      });
    });
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
      try {
        const response = await fetch(`/transcripts/${state.recordId}/resummarize`, { method: "POST" });
        const payload = await response.json();
        if (payload.ok && summaryCards && summaryProviderLabel) {
          summaryCards.innerHTML = "";
          payload.summary.forEach((item) => {
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
      } finally {
        refreshSummaryButton.disabled = false;
        refreshSummaryButton.textContent = "Refresh summary";
      }
    });
  }
})();
