(() => {
  const root = document.documentElement;
  const THEME_KEY = "tacticaldesk-theme";

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }

  const storedTheme = localStorage.getItem(THEME_KEY);
  if (storedTheme) {
    root.setAttribute("data-theme", storedTheme);
  } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    root.setAttribute("data-theme", "dark");
  }

  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-action='toggle-theme']");
    if (!target) {
      return;
    }
    const currentTheme = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
    applyTheme(currentTheme === "dark" ? "light" : "dark");
  });

  async function submitJsonForm(form, url) {
    const messageEl = form.querySelector("[data-role='form-message']");
    if (messageEl) {
      messageEl.classList.remove("error", "success");
      messageEl.textContent = "";
    }

    const formData = new FormData(form);
    const payload = Object.fromEntries(formData.entries());
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json"
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
        credentials: "same-origin"
      });

      const data = await response.json().catch(() => ({}));
      const detailMessage = Array.isArray(data.detail)
        ? data.detail.join(" ")
        : data.detail;
      if (!response.ok) {
        throw new Error(detailMessage || "Request failed");
      }
      if (messageEl) {
        messageEl.textContent = detailMessage || "Success";
        messageEl.classList.add("success");
      }
      return data;
    } catch (error) {
      console.error(error);
      if (messageEl) {
        messageEl.textContent = error.message || "An unexpected error occurred";
        messageEl.classList.add("error");
      }
      return null;
    } finally {
      clearTimeout(timeout);
    }
  }

  const loginForm = document.getElementById("login-form");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const result = await submitJsonForm(loginForm, "/auth/login");
      if (result) {
        window.location.href = "/dashboard";
      }
    });
  }

  const registerForm = document.getElementById("register-form");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const password = registerForm.querySelector("#register-password").value;
      const confirm = registerForm.querySelector("#register-password-confirm").value;
      const messageEl = registerForm.querySelector("[data-role='form-message']");
      if (password !== confirm) {
        if (messageEl) {
          messageEl.textContent = "Passwords do not match";
          messageEl.classList.add("error");
        }
        return;
      }
      const result = await submitJsonForm(registerForm, "/auth/register");
      if (result) {
        if (messageEl) {
          messageEl.textContent = "Super admin created. Redirecting to sign in";
          messageEl.classList.add("success");
        }
        setTimeout(() => {
          window.location.href = "/";
        }, 1200);
      }
    });
  }

  const sortableTables = Array.from(document.querySelectorAll("[data-role='sortable-table']"));
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

  const ticketCreateModal = document.querySelector("[data-role='ticket-create-modal']");
  const ticketCreateForm = ticketCreateModal?.querySelector("[data-role='ticket-create-form']");
  const ticketCreateMessage = ticketCreateForm?.querySelector("[data-role='form-message']");
  let ticketCreateLastFocus = null;

  function resetTicketCreateForm() {
    if (!ticketCreateForm) {
      return;
    }
    ticketCreateForm.reset();
    if (ticketCreateMessage) {
      ticketCreateMessage.textContent = "";
      ticketCreateMessage.classList.remove("error", "success");
    }
  }

  function openTicketCreateModal() {
    if (!ticketCreateModal) {
      window.location.href = "/tickets?new=1";
      return;
    }
    ticketCreateLastFocus = document.activeElement;
    ticketCreateModal.classList.add("is-open");
    ticketCreateModal.setAttribute("aria-hidden", "false");
    const subjectInput = ticketCreateForm?.querySelector("input[name='subject']");
    if (subjectInput) {
      subjectInput.focus();
    }
  }

  function closeTicketCreateModal() {
    if (!ticketCreateModal) {
      return;
    }
    ticketCreateModal.classList.remove("is-open");
    ticketCreateModal.setAttribute("aria-hidden", "true");
    resetTicketCreateForm();
    if (ticketCreateLastFocus && typeof ticketCreateLastFocus.focus === "function") {
      ticketCreateLastFocus.focus();
    }
  }

  if (ticketCreateModal && ticketCreateModal.dataset.open === "true") {
    openTicketCreateModal();
    ticketCreateModal.dataset.open = "false";
  }

  if (ticketCreateForm) {
    ticketCreateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const submitButton = ticketCreateForm.querySelector("button[type='submit']");
      if (submitButton) {
        submitButton.disabled = true;
      }
      const targetUrl = ticketCreateForm.getAttribute("action") || "/tickets";
      const result = await submitJsonForm(ticketCreateForm, targetUrl);
      if (submitButton) {
        submitButton.disabled = false;
      }
      if (result) {
        closeTicketCreateModal();
        if (result.redirect_url) {
          window.open(result.redirect_url, "_blank", "noopener,noreferrer");
        }
        setTimeout(() => {
          window.location.reload();
        }, 400);
      }
    });
  }

  function updateTableRowVisibility(row) {
    if (!row) {
      return;
    }
    const matchesFilter = row.dataset.filterVisible !== "false";
    const matchesSearch = row.dataset.searchVisible !== "false";
    row.style.display = matchesFilter && matchesSearch ? "" : "none";
  }

  function ensureVisibilityFlags(row) {
    if (!row) {
      return;
    }
    if (!Object.prototype.hasOwnProperty.call(row.dataset, "filterVisible")) {
      row.dataset.filterVisible = "true";
    }
    if (!Object.prototype.hasOwnProperty.call(row.dataset, "searchVisible")) {
      row.dataset.searchVisible = "true";
    }
    updateTableRowVisibility(row);
  }

  sortableTables.forEach((table) => {
    const headers = table.tHead ? Array.from(table.tHead.rows[0].cells) : [];
    headers.forEach((header, headerIndex) => {
      header.addEventListener("click", () => {
        if (!header.dataset.sortKey) {
          return;
        }
        const currentDirection = header.dataset.sortDirection === "asc" ? "asc" : header.dataset.sortDirection === "desc" ? "desc" : null;
        const newDirection = currentDirection === "asc" ? "desc" : "asc";
        headers.forEach((h) => delete h.dataset.sortDirection);
        header.dataset.sortDirection = newDirection;
        const rows = Array.from(table.tBodies[0].rows);
        rows.sort((rowA, rowB) => {
          const cellA = rowA.cells[headerIndex];
          const cellB = rowB.cells[headerIndex];
          const valueA = cellA?.dataset.sortValue ?? cellA?.textContent?.trim() ?? "";
          const valueB = cellB?.dataset.sortValue ?? cellB?.textContent?.trim() ?? "";
          const comparison = collator.compare(valueA, valueB);
          return newDirection === "asc" ? comparison : -comparison;
        });
        const fragment = document.createDocumentFragment();
        rows.forEach((row) => fragment.appendChild(row));
        table.tBodies[0].appendChild(fragment);
      });
    });
  });

  document.querySelectorAll('[data-format="datetime"]').forEach((element) => {
    const value = element.dataset.sortValue || element.textContent?.trim();
    if (!value) {
      return;
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      element.textContent = parsed.toLocaleString();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && ticketCreateModal?.classList.contains("is-open")) {
      event.preventDefault();
      closeTicketCreateModal();
    }
  });

  document.querySelectorAll('[data-role="local-datetime"]').forEach((element) => {
    const value = element.getAttribute("datetime") || element.textContent?.trim();
    if (!value) {
      return;
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      element.textContent = parsed.toLocaleString();
    }
  });

  document.querySelectorAll("[data-role='table-filter']").forEach((filterInput) => {
    const container =
      filterInput.closest(
        ".ticket-board, .ticket-table-container, .panel, .card, .table-container"
      ) || document;
    const table = container.querySelector("[data-role='sortable-table']");
    if (!table || !table.tBodies.length) {
      return;
    }
    const getRows = () => Array.from(table.tBodies[0].rows);
    getRows().forEach(ensureVisibilityFlags);
    filterInput.addEventListener("input", () => {
      const query = filterInput.value.toLowerCase();
      getRows().forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.dataset.searchVisible = text.includes(query) ? "true" : "false";
        updateTableRowVisibility(row);
      });
    });
  });

  async function patchIntegration(slug, payload) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/integrations/${encodeURIComponent(slug)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload),
        credentials: "same-origin",
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Unable to update integration");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  function setStatusMessage(target, message, type) {
    if (!target) {
      return;
    }
    target.textContent = message || "";
    target.classList.remove("error", "success");
    if (type) {
      target.classList.add(type);
    }
  }

  function findIntegrationMessage(source) {
    if (!source) {
      return null;
    }
    return (
      source.closest(".content-section")?.querySelector("[data-role='integration-message']") ||
      source.closest(".panel")?.querySelector("[data-role='integration-message']") ||
      document.querySelector("[data-role='integration-message']")
    );
  }

  function setIntegrationBadge(badge, enabled) {
    if (!badge) {
      return;
    }
    badge.classList.toggle("status-open", Boolean(enabled));
    badge.classList.toggle("status-waiting", !enabled);
    badge.textContent = enabled ? "Enabled" : "Disabled";
  }

  function toLocalDatetime(value) {
    if (!value) {
      return "";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString();
  }

  const webhookMessageTarget = document.querySelector("[data-role='webhook-message']");

  function formatWebhookStatusLabel(status) {
    if (!status) {
      return "";
    }
    return status
      .toString()
      .replace(/[_\-]+/g, " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function findWebhookRow(webhookId) {
    if (!webhookId) {
      return null;
    }
    return document.querySelector(`[data-webhook-row='${webhookId}']`);
  }

  function ensureWebhookEmptyState(table) {
    if (!table || !table.tBodies.length) {
      return;
    }
    const tbody = table.tBodies[0];
    const hasRows = Boolean(tbody.querySelector("tr[data-webhook-row]"));
    const emptyRow = tbody.querySelector("[data-role='webhook-empty']");
    if (hasRows) {
      if (emptyRow) {
        emptyRow.remove();
      }
      return;
    }
    if (!emptyRow) {
      const row = document.createElement("tr");
      row.dataset.role = "webhook-empty";
      const cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = "All outbound webhooks are healthy.";
      row.appendChild(cell);
      tbody.appendChild(row);
    }
  }

  function updateWebhookRowFromPayload(row, payload) {
    if (!row || !payload) {
      return;
    }
    const statusCell = row.querySelector("[data-cell='status']");
    if (statusCell && payload.status) {
      statusCell.dataset.sortValue = payload.status;
      statusCell.textContent = formatWebhookStatusLabel(payload.status);
    }
    const lastAttemptCell = row.querySelector("[data-cell='last_attempt']");
    if (lastAttemptCell) {
      if (payload.last_attempt_at) {
        lastAttemptCell.dataset.sortValue = payload.last_attempt_at;
        lastAttemptCell.dataset.format = "datetime";
        lastAttemptCell.textContent = toLocalDatetime(payload.last_attempt_at);
      } else {
        lastAttemptCell.dataset.sortValue = "";
        delete lastAttemptCell.dataset.format;
        lastAttemptCell.textContent = "—";
      }
    }
    const nextRetryCell = row.querySelector("[data-cell='next_retry']");
    if (nextRetryCell) {
      if (payload.next_retry_at) {
        nextRetryCell.dataset.sortValue = payload.next_retry_at;
        nextRetryCell.dataset.format = "datetime";
        nextRetryCell.textContent = toLocalDatetime(payload.next_retry_at);
      } else {
        nextRetryCell.dataset.sortValue = "";
        delete nextRetryCell.dataset.format;
        nextRetryCell.textContent = "Paused";
      }
    }
    const pauseButton = row.querySelector("[data-action='webhook-pause']");
    const resumeButton = row.querySelector("[data-action='webhook-resume']");
    if (pauseButton) {
      pauseButton.hidden = payload.status === "paused";
    }
    if (resumeButton) {
      resumeButton.hidden = payload.status !== "paused";
    }
  }

  async function performWebhookAction(action, webhookId, trigger) {
    if (!webhookId) {
      return;
    }
    if (trigger) {
      trigger.disabled = true;
    }
    const messageMap = {
      pause: `Pausing webhook ${webhookId}…`,
      resume: `Resuming webhook ${webhookId}…`,
      delete: `Deleting webhook ${webhookId}…`,
    };
    setStatusMessage(webhookMessageTarget, messageMap[action] || "Processing…");

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);

    try {
      const targetUrl = `/api/webhooks/${encodeURIComponent(webhookId)}/${
        action === "delete" ? "" : `${action}`
      }`.replace(/\/$/, "");
      const init = {
        method: action === "delete" ? "DELETE" : "POST",
        headers: {
          Accept: "application/json",
        },
        credentials: "same-origin",
        signal: controller.signal,
      };
      const response = await fetch(targetUrl, init);
      if (!response.ok) {
        let errorDetail = "Request failed";
        try {
          const payload = await response.json();
          errorDetail = payload?.detail || errorDetail;
        } catch (error) {
          // Ignore JSON parse errors for non-JSON responses.
        }
        throw new Error(errorDetail);
      }

      if (action === "delete") {
        const row = findWebhookRow(webhookId);
        const table = row ? row.closest("table") : null;
        if (row) {
          row.remove();
        }
        if (table) {
          ensureWebhookEmptyState(table);
        }
        setStatusMessage(
          webhookMessageTarget,
          `Webhook ${webhookId} deleted.`,
          "success"
        );
        return;
      }

      const data = await response.json();
      const row = findWebhookRow(webhookId);
      updateWebhookRowFromPayload(row, data);
      setStatusMessage(
        webhookMessageTarget,
        `Webhook ${webhookId} ${action === "pause" ? "paused" : "resumed"}.`,
        "success"
      );
    } catch (error) {
      setStatusMessage(
        webhookMessageTarget,
        error?.message || "Unable to complete webhook request.",
        "error"
      );
    } finally {
      clearTimeout(timeout);
      if (trigger) {
        trigger.disabled = false;
      }
    }
  }

  function syncIntegrationNav(moduleData) {
    const navGroup = document.querySelector("[data-role='integration-nav']");
    if (!navGroup) {
      return;
    }
    const emptyState = navGroup.querySelector(".nav-empty");
    const existingLink = navGroup.querySelector(
      `[data-integration-link='${moduleData.slug}']`
    );

    if (moduleData.enabled) {
      if (emptyState) {
        emptyState.remove();
      }
      if (!existingLink) {
        const link = document.createElement("a");
        link.className = "nav-sublink";
        link.href = `/integrations/${moduleData.slug}`;
        link.dataset.integrationLink = moduleData.slug;
        link.innerHTML = `
          <span class="nav-icon" aria-hidden="true">${moduleData.icon || "🔌"}</span>
          <span>${moduleData.name}</span>
        `;
        navGroup.appendChild(link);
      } else {
        const icon = existingLink.querySelector(".nav-icon");
        if (icon) {
          icon.textContent = moduleData.icon || "🔌";
        }
        const label = existingLink.querySelector("span:last-child");
        if (label) {
          label.textContent = moduleData.name;
        }
      }
    } else {
      if (existingLink) {
        existingLink.remove();
      }
      if (!navGroup.querySelector("a.nav-sublink")) {
        const placeholder = document.createElement("p");
        placeholder.className = "nav-empty";
        placeholder.textContent = "No integrations enabled";
        navGroup.appendChild(placeholder);
      }
    }
  }

  const integrationToggles = Array.from(document.querySelectorAll("[data-role='integration-toggle']"));
  if (integrationToggles.length) {
    integrationToggles.forEach((toggle) => {
      toggle.addEventListener("change", async () => {
        const slug = toggle.dataset.slug;
        if (!slug) {
          return;
        }
        const desiredState = toggle.checked;
        const messageTarget = findIntegrationMessage(toggle);
        setStatusMessage(messageTarget, "Updating integration…");
        toggle.disabled = true;
        try {
          const payload = await patchIntegration(slug, { enabled: desiredState });
          toggle.checked = payload.enabled;
          setStatusMessage(
            messageTarget,
            `${payload.name} ${payload.enabled ? "enabled" : "disabled"}.`,
            "success"
          );

          const badges = [];
          const tableRow = toggle.closest("tr[data-integration-row]");
          if (tableRow) {
            const badge = tableRow.querySelector("[data-role='integration-status-label']");
            if (badge) {
              badges.push(badge);
            }
            const updatedCell = tableRow.querySelector("[data-label='Last updated']");
            if (updatedCell) {
              if (payload.updated_at) {
                updatedCell.dataset.sortValue = payload.updated_at;
                updatedCell.dataset.format = "datetime";
                updatedCell.textContent = toLocalDatetime(payload.updated_at);
              } else {
                updatedCell.dataset.sortValue = "";
                delete updatedCell.dataset.format;
                updatedCell.textContent = "Not configured";
              }
            }
          }

          const detailBadge = document.querySelector(
            ".integration-status-card [data-role='integration-status-label']"
          );
          if (detailBadge) {
            badges.push(detailBadge);
          }
          badges.forEach((badge) => setIntegrationBadge(badge, payload.enabled));

          const detailUpdated = document.querySelector("[data-role='integration-updated']");
          if (detailUpdated) {
            if (payload.updated_at) {
              detailUpdated.dataset.sortValue = payload.updated_at;
              detailUpdated.dataset.format = "datetime";
              detailUpdated.textContent = toLocalDatetime(payload.updated_at);
            } else {
              detailUpdated.dataset.sortValue = "";
              delete detailUpdated.dataset.format;
              detailUpdated.textContent = "Not configured";
            }
          }

          syncIntegrationNav(payload);
        } catch (error) {
          toggle.checked = !desiredState;
          setStatusMessage(
            messageTarget,
            error.message || "Unable to update integration",
            "error"
          );
        } finally {
          toggle.disabled = false;
        }
      });
    });
  }

  const integrationForm = document.getElementById("integration-settings-form");
  if (integrationForm) {
    integrationForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const slug = integrationForm.dataset.slug;
      if (!slug) {
        return;
      }
      const messageTarget = integrationForm.querySelector("[data-role='form-message']");
      setStatusMessage(messageTarget, "Saving settings…");
      const formData = new FormData(integrationForm);
      const settings = {};
      formData.forEach((value, key) => {
        if (typeof value === "string") {
          settings[key] = value.trim();
        } else {
          settings[key] = value;
        }
      });
      try {
        const payload = await patchIntegration(slug, { settings });
        setStatusMessage(messageTarget, "Settings saved.", "success");
        const detailUpdated = document.querySelector("[data-role='integration-updated']");
        if (detailUpdated) {
          if (payload.updated_at) {
            detailUpdated.dataset.sortValue = payload.updated_at;
            detailUpdated.dataset.format = "datetime";
            detailUpdated.textContent = toLocalDatetime(payload.updated_at);
          } else {
            detailUpdated.dataset.sortValue = "";
            delete detailUpdated.dataset.format;
            detailUpdated.textContent = "Not configured";
          }
        }
      } catch (error) {
        setStatusMessage(
          messageTarget,
          error.message || "Unable to save settings",
          "error"
        );
      }
    });
  }

  const ticketTable = document.querySelector("[data-ticket-table='true']");
  const ticketFilterButtons = Array.from(document.querySelectorAll("[data-action='ticket-filter']"));

  if (ticketTable && ticketTable.tBodies.length) {
    const ticketRows = Array.from(ticketTable.tBodies[0].rows);
    ticketRows.forEach(ensureVisibilityFlags);

    ticketFilterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const filterKey = button.dataset.filter || "all";
        ticketFilterButtons.forEach((btn) => btn.classList.toggle("is-active", btn === button));
        ticketRows.forEach((row) => {
          const keys = (row.dataset.filterKeys || "")
            .split(/\s+/)
            .map((value) => value.trim())
            .filter(Boolean);
          const matches = filterKey === "all" || keys.includes(filterKey);
          row.dataset.filterVisible = matches ? "true" : "false";
          updateTableRowVisibility(row);
        });
      });
    });
  }

  document.addEventListener("click", (event) => {
    const dashboardNewTicket = event.target.closest("[data-action='new-ticket']");
    if (dashboardNewTicket) {
      event.preventDefault();
      if (ticketCreateModal) {
        openTicketCreateModal();
      } else {
        window.location.href = "/tickets?new=1";
      }
      return;
    }

    const ticketCreateOpenButton = event.target.closest("[data-action='ticket-create-open']");
    if (ticketCreateOpenButton) {
      event.preventDefault();
      openTicketCreateModal();
      return;
    }

    const ticketCreateCloseButton = event.target.closest("[data-action='ticket-create-close']");
    if (ticketCreateCloseButton) {
      event.preventDefault();
      closeTicketCreateModal();
      return;
    }

    const webhookAdminButton = event.target.closest("[data-action='view-webhook-admin']");
    if (webhookAdminButton) {
      const targetUrl = webhookAdminButton.getAttribute("data-href") || "/admin/webhooks";
      window.location.href = targetUrl;
      return;
    }

    const webhookRefreshButton = event.target.closest("[data-action='webhook-refresh']");
    if (webhookRefreshButton) {
      window.location.reload();
      return;
    }

    const webhookPauseButton = event.target.closest("[data-action='webhook-pause']");
    if (webhookPauseButton) {
      event.preventDefault();
      const webhookId = webhookPauseButton.dataset.webhookId;
      if (webhookId) {
        performWebhookAction("pause", webhookId, webhookPauseButton);
      }
      return;
    }

    const webhookResumeButton = event.target.closest("[data-action='webhook-resume']");
    if (webhookResumeButton) {
      event.preventDefault();
      const webhookId = webhookResumeButton.dataset.webhookId;
      if (webhookId) {
        performWebhookAction("resume", webhookId, webhookResumeButton);
      }
      return;
    }

    const webhookDeleteButton = event.target.closest("[data-action='webhook-delete']");
    if (webhookDeleteButton) {
      event.preventDefault();
      const webhookId = webhookDeleteButton.dataset.webhookId;
      if (webhookId) {
        const confirmed = window.confirm(
          `Delete webhook ${webhookId}? Pending retries will be cleared.`
        );
        if (confirmed) {
          performWebhookAction("delete", webhookId, webhookDeleteButton);
        }
      }
      return;
    }

    const refreshButton = event.target.closest("[data-action='ticket-refresh']");
    if (refreshButton) {
      window.location.reload();
      return;
    }

    const selectAllButton = event.target.closest("[data-action='ticket-select-all']");
    if (selectAllButton && ticketTable) {
      const checkboxes = Array.from(ticketTable.querySelectorAll("tbody input[type='checkbox']"));
      if (checkboxes.length) {
        const shouldSelect = checkboxes.some((checkbox) => !checkbox.checked);
        checkboxes.forEach((checkbox) => {
          checkbox.checked = shouldSelect;
        });
      }
    }
  });

  const organizationTableBody = document.querySelector(
    "[data-role='organization-table-body']"
  );
  const organizationStatusFilter = document.querySelector(
    "[data-role='organization-status-filter']"
  );

  if (organizationTableBody) {
    const initialRows = Array.from(
      organizationTableBody.querySelectorAll("tr[data-organization-row]")
    );
    initialRows.forEach(ensureVisibilityFlags);
  }

  if (organizationStatusFilter && organizationTableBody) {
    const getOrganizationRows = () =>
      Array.from(organizationTableBody.querySelectorAll("tr[data-organization-row]"));

    organizationStatusFilter.addEventListener("change", () => {
      const desiredStatus = organizationStatusFilter.value;
      getOrganizationRows().forEach((row) => {
        const status = row.dataset.status || "active";
        const matches =
          desiredStatus === "all" || desiredStatus === "" || status === desiredStatus;
        row.dataset.filterVisible = matches ? "true" : "false";
        updateTableRowVisibility(row);
      });
    });

    organizationStatusFilter.dispatchEvent(new Event("change"));
  }

  function slugifyOrganization(value) {
    return value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .replace(/-{2,}/g, "-");
  }

  const organizationForm = document.getElementById("organization-form");
  if (organizationForm) {
    const nameInput = organizationForm.querySelector("#organization-name");
    const slugInput = organizationForm.querySelector("#organization-slug");
    let slugManuallyEdited = organizationForm.dataset.mode === "edit";
    if (nameInput && slugInput) {
      nameInput.addEventListener("input", () => {
        if (!slugManuallyEdited) {
          slugInput.value = slugifyOrganization(nameInput.value);
        }
      });
      slugInput.addEventListener("input", () => {
        slugManuallyEdited = slugInput.value.trim().length > 0;
      });
    }
  }

  if (organizationTableBody) {
    organizationTableBody.addEventListener("click", async (event) => {
      const archiveTrigger = event.target.closest(
        "[data-action='toggle-organization-archive']"
      );
      if (!archiveTrigger) {
        return;
      }
      const organizationId = archiveTrigger.dataset.organizationId;
      if (!organizationId) {
        return;
      }
      const isArchived = archiveTrigger.dataset.isArchived === "true";
      const desiredState = !isArchived;
      const confirmationMessage = desiredState
        ? "Archive this organisation? Contacts remain preserved for future reference."
        : "Restore this organisation to the active directory?";
      const confirmed = window.confirm(confirmationMessage);
      if (!confirmed) {
        return;
      }
      archiveTrigger.disabled = true;
      try {
        const response = await fetch(
          `/api/organizations/${encodeURIComponent(organizationId)}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            body: JSON.stringify({ is_archived: desiredState }),
            credentials: "same-origin",
          }
        );
        if (!response.ok) {
          let detail = "Unable to update organisation";
          try {
            const payload = await response.json();
            detail = payload?.detail || detail;
          } catch (error) {
            // Ignore JSON parse errors for non-JSON responses.
          }
          throw new Error(detail);
        }
        window.location.reload();
      } catch (error) {
        window.alert(error.message || "Unable to update organisation");
      } finally {
        archiveTrigger.disabled = false;
      }
    });
  }

  function isoToLocalInputValue(value) {
    if (!value) {
      return "";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return "";
    }
    const offset = parsed.getTimezoneOffset();
    const local = new Date(parsed.getTime() - offset * 60000);
    return local.toISOString().slice(0, 16);
  }

  function localInputToIso(value) {
    if (!value) {
      return null;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return parsed.toISOString();
  }

  async function patchAutomation(automationId, payload) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(`/api/automations/${encodeURIComponent(automationId)}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || "Unable to update automation");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  function setAutomationFormMessage(target, message, type) {
    if (!target) {
      return;
    }
    target.textContent = message || "";
    target.classList.remove("success", "error");
    if (type) {
      target.classList.add(type);
    }
  }

  const automationEditPage = document.querySelector("[data-role='automation-edit-page']");
  if (automationEditPage) {
    const automationId = automationEditPage.dataset.automationId;
    const returnUrl = automationEditPage.dataset.returnUrl;
    const form = automationEditPage.querySelector("[data-role='automation-edit-form']");
    const messageTarget = automationEditPage.querySelector("[data-role='automation-message']");
    const submitButton = form?.querySelector("[data-role='automation-submit']");
    const nameInput = form?.querySelector("#automation-name");
    const playbookInput = form?.querySelector("#automation-playbook");
    const descriptionInput = form?.querySelector("#automation-description");
    const cronInput = form?.querySelector("#automation-cron-expression");
    const triggerInput = form?.querySelector("#automation-trigger");
    const triggerMatchInput = form?.querySelector("#automation-trigger-match");
    const statusInput = form?.querySelector("#automation-status");
    const nextRunInput = form?.querySelector("#automation-next-run");
    const lastRunInput = form?.querySelector("#automation-last-run");
    const lastTriggerInput = form?.querySelector("#automation-last-trigger");
    const triggerConditionsRoot = form?.querySelector("[data-role='trigger-conditions']");
    const triggerConditionList = triggerConditionsRoot?.querySelector(
      "[data-role='trigger-condition-list']"
    );
    const triggerConditionTemplate = triggerConditionsRoot?.querySelector(
      "[data-role='trigger-condition-template']"
    );
    const addTriggerConditionButton = triggerConditionsRoot?.querySelector(
      "[data-action='add-trigger-condition']"
    );
    const triggerConditionFilter = triggerConditionsRoot?.querySelector(
      "[data-role='trigger-condition-filter']"
    );
    const triggerSortButton = triggerConditionsRoot?.querySelector(
      "[data-role='trigger-sort']"
    );

    let valueRequiredTriggers = new Set();
    if (triggerConditionsRoot) {
      const valueRequiredDataset = triggerConditionsRoot.dataset.valueRequired;
      if (valueRequiredDataset) {
        try {
          const parsedRequired = JSON.parse(valueRequiredDataset);
          if (Array.isArray(parsedRequired)) {
            valueRequiredTriggers = new Set(parsedRequired);
          }
        } catch (error) {
          console.warn("Unable to parse value required triggers", error);
        }
      }
    }

    if (form) {
      const datetimeInputs = Array.from(
        form.querySelectorAll("[data-automation-datetime]")
      );
      datetimeInputs.forEach((input) => {
        if (!(input instanceof HTMLInputElement)) {
          return;
        }
        const isoValue = input.dataset.isoValue;
        if (isoValue) {
          input.value = isoToLocalInputValue(isoValue);
        }
      });

      let initialTriggerFilters = null;
      const filtersDataset = form.dataset.triggerFilters;
      if (filtersDataset) {
        try {
          initialTriggerFilters = JSON.parse(filtersDataset);
        } catch (error) {
          console.warn("Unable to parse trigger filters", error);
        }
      }

      function normalizeTriggerCondition(raw) {
        if (!raw) {
          return null;
        }
        if (typeof raw === "string") {
          return { type: raw };
        }
        if (typeof raw === "object") {
          const type = raw.type || raw.trigger || raw.label;
          if (!type) {
            return null;
          }
          const condition = { type };
          if (raw.operator) {
            condition.operator = raw.operator;
          }
          if (raw.value) {
            condition.value = raw.value;
          }
          return condition;
        }
        return null;
      }

      function syncTriggerConditionRow(row) {
        if (!row) {
          return;
        }
        const typeSelect = row.querySelector(
          "[data-role='trigger-condition-select']"
        );
        const operatorSelect = row.querySelector(
          "[data-role='trigger-condition-operator']"
        );
        const valueInput = row.querySelector(
          "[data-role='trigger-condition-value']"
        );
        if (!(typeSelect instanceof HTMLSelectElement)) {
          return;
        }
        const requiresValue = valueRequiredTriggers.has(typeSelect.value);
        if (operatorSelect instanceof HTMLSelectElement) {
          operatorSelect.disabled = !requiresValue;
          operatorSelect.required = requiresValue;
          if (!requiresValue) {
            operatorSelect.value = "";
          }
        }
        if (valueInput instanceof HTMLInputElement) {
          valueInput.disabled = !requiresValue;
          valueInput.required = requiresValue;
          if (!requiresValue) {
            valueInput.value = "";
          }
        }
      }

      function updateTriggerConditionRemoveButtons() {
        if (!triggerConditionList) {
          return;
        }
        const rows = Array.from(
          triggerConditionList.querySelectorAll("[data-role='trigger-condition']")
        );
        rows.forEach((row) => {
          const removeButton = row.querySelector(
            "[data-action='remove-trigger-condition']"
          );
          if (removeButton) {
            removeButton.disabled = rows.length === 0;
          }
        });
      }

      function applyTriggerFilter() {
        if (!triggerConditionList || !triggerConditionFilter) {
          return;
        }
        const query = triggerConditionFilter.value.trim().toLowerCase();
        const rows = Array.from(
          triggerConditionList.querySelectorAll("[data-role='trigger-condition']")
        );
        rows.forEach((row) => {
          const textContent = Array.from(
            row.querySelectorAll(
              "[data-role='trigger-condition-select'], [data-role='trigger-condition-operator'], [data-role='trigger-condition-value']"
            )
          )
            .map((element) => {
              if (element instanceof HTMLSelectElement) {
                const option = element.selectedOptions[0];
                return option ? option.textContent || "" : "";
              }
              if (element instanceof HTMLInputElement) {
                return element.value || "";
              }
              return "";
            })
            .join(" ")
            .toLowerCase();
          const matches = query === "" || textContent.includes(query);
          row.classList.toggle("is-hidden", !matches);
        });
      }

      function sortTriggerRows(direction = "asc") {
        if (!triggerConditionList) {
          return;
        }
        const rows = Array.from(
          triggerConditionList.querySelectorAll("[data-role='trigger-condition']")
        );
        rows.sort((a, b) => {
          const selectA = a.querySelector(
            "[data-role='trigger-condition-select']"
          );
          const selectB = b.querySelector(
            "[data-role='trigger-condition-select']"
          );
          const textA =
            selectA instanceof HTMLSelectElement && selectA.selectedOptions[0]
              ? selectA.selectedOptions[0].textContent || ""
              : "";
          const textB =
            selectB instanceof HTMLSelectElement && selectB.selectedOptions[0]
              ? selectB.selectedOptions[0].textContent || ""
              : "";
          const compare = textA.localeCompare(textB, undefined, {
            sensitivity: "base",
          });
          return direction === "desc" ? compare * -1 : compare;
        });
        rows.forEach((row) => {
          triggerConditionList.appendChild(row);
        });
      }

      function addTriggerConditionRow(condition = null) {
        if (!triggerConditionTemplate || !triggerConditionList) {
          return null;
        }
        const fragment = document.importNode(
          triggerConditionTemplate.content,
          true
        );
        const row = fragment.querySelector("[data-role='trigger-condition']");
        if (!row) {
          return null;
        }
        const typeSelect = row.querySelector(
          "[data-role='trigger-condition-select']"
        );
        const operatorSelect = row.querySelector(
          "[data-role='trigger-condition-operator']"
        );
        const valueInput = row.querySelector(
          "[data-role='trigger-condition-value']"
        );
        if (condition) {
          if (typeSelect instanceof HTMLSelectElement && condition.type) {
            typeSelect.value = condition.type;
          }
          if (operatorSelect instanceof HTMLSelectElement && condition.operator) {
            operatorSelect.value = condition.operator;
          }
          if (valueInput instanceof HTMLInputElement && condition.value) {
            valueInput.value = condition.value;
          }
        }
        triggerConditionList.appendChild(fragment);
        const insertedRow = triggerConditionList.lastElementChild;
        if (insertedRow) {
          syncTriggerConditionRow(insertedRow);
        }
        updateTriggerConditionRemoveButtons();
        applyTriggerFilter();
        return insertedRow;
      }

      function setTriggerConditionValues(values) {
        if (!triggerConditionList) {
          return;
        }
        triggerConditionList.innerHTML = "";
        const normalized =
          Array.isArray(values) && values.length ? values : [null];
        normalized.forEach((value) => {
          const condition = normalizeTriggerCondition(value);
          addTriggerConditionRow(condition);
        });
        updateTriggerConditionRemoveButtons();
        applyTriggerFilter();
      }

      function collectTriggerConditionValues() {
        if (!triggerConditionList) {
          return { conditions: [], errors: [] };
        }
        const rows = Array.from(
          triggerConditionList.querySelectorAll("[data-role='trigger-condition']")
        );
        const conditions = [];
        const errors = [];
        rows.forEach((row, index) => {
          const typeSelect = row.querySelector(
            "[data-role='trigger-condition-select']"
          );
          const operatorSelect = row.querySelector(
            "[data-role='trigger-condition-operator']"
          );
          const valueInput = row.querySelector(
            "[data-role='trigger-condition-value']"
          );
          if (!(typeSelect instanceof HTMLSelectElement)) {
            return;
          }
          const typeValue = typeSelect.value.trim();
          if (!typeValue) {
            return;
          }
          const requiresValue = valueRequiredTriggers.has(typeValue);
          const condition = { type: typeValue };
          if (requiresValue) {
            const operatorValue =
              operatorSelect instanceof HTMLSelectElement
                ? operatorSelect.value.trim()
                : "";
            const textValue =
              valueInput instanceof HTMLInputElement
                ? valueInput.value.trim()
                : "";
            if (!operatorValue) {
              errors.push(
                `Operator is required for condition ${index + 1}.`
              );
            }
            if (!textValue) {
              errors.push(`Value is required for condition ${index + 1}.`);
            }
            if (operatorValue) {
              condition.operator = operatorValue;
            }
            if (textValue) {
              condition.value = textValue;
            }
          }
          conditions.push(condition);
        });
        return { conditions, errors };
      }

      const selectedConditionsRaw = Array.isArray(
        initialTriggerFilters?.conditions
      )
        ? initialTriggerFilters.conditions
        : [];
      const singleTrigger = form.dataset.triggerValue || "";
      const valuesToSelect = selectedConditionsRaw.length
        ? selectedConditionsRaw
        : singleTrigger
        ? [{ type: singleTrigger }]
        : [];

      if (triggerConditionsRoot) {
        setTriggerConditionValues(valuesToSelect);
        if (triggerSortButton instanceof HTMLButtonElement) {
          triggerSortButton.dataset.sortIndicator = "▲";
        }
      } else if (
        triggerInput instanceof HTMLSelectElement &&
        triggerInput.multiple
      ) {
        const selectedSet = new Set(
          valuesToSelect
            .map((value) => {
              const condition = normalizeTriggerCondition(value);
              return condition ? condition.type : null;
            })
            .filter((value) => Boolean(value))
        );
        Array.from(triggerInput.options).forEach((option) => {
          option.selected = selectedSet.has(option.value);
        });
      }

      if (addTriggerConditionButton) {
        addTriggerConditionButton.addEventListener("click", () => {
          const newRow = addTriggerConditionRow();
          const select = newRow?.querySelector(
            "[data-role='trigger-condition-select']"
          );
          if (select instanceof HTMLSelectElement) {
            select.focus();
          }
        });
      }

      if (triggerConditionFilter instanceof HTMLInputElement) {
        triggerConditionFilter.addEventListener("input", () => {
          applyTriggerFilter();
        });
      }

      if (triggerSortButton instanceof HTMLButtonElement) {
        let sortDirection = "asc";
        triggerSortButton.addEventListener("click", () => {
          sortDirection = sortDirection === "asc" ? "desc" : "asc";
          triggerSortButton.dataset.sortIndicator =
            sortDirection === "asc" ? "▲" : "▼";
          sortTriggerRows(sortDirection);
        });
      }

      if (triggerConditionList) {
        triggerConditionList.addEventListener("click", (event) => {
          const removeButton = event.target.closest(
            "[data-action='remove-trigger-condition']"
          );
          if (!removeButton) {
            return;
          }
          const row = removeButton.closest("[data-role='trigger-condition']");
          if (!row) {
            return;
          }
          row.remove();
          updateTriggerConditionRemoveButtons();
          applyTriggerFilter();
        });

        triggerConditionList.addEventListener("change", (event) => {
          const row = event.target.closest("[data-role='trigger-condition']");
          if (!row) {
            return;
          }
          syncTriggerConditionRow(row);
          applyTriggerFilter();
        });

        triggerConditionList.addEventListener("input", (event) => {
          const row = event.target.closest("[data-role='trigger-condition']");
          if (!row) {
            return;
          }
          applyTriggerFilter();
        });
      }

      if (triggerMatchInput instanceof HTMLSelectElement) {
        const matchValue =
          initialTriggerFilters && initialTriggerFilters.match === "all"
            ? "all"
            : "any";
        triggerMatchInput.value = matchValue;
      }

      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!submitButton) {
          return;
        }
        if (!automationId) {
          setAutomationFormMessage(
            messageTarget,
            "Unable to determine automation identifier.",
            "error"
          );
          return;
        }

        const nameValue = nameInput?.value?.trim() || "";
        if (!nameValue) {
          setAutomationFormMessage(messageTarget, "Name is required.", "error");
          nameInput?.focus();
          return;
        }

        const playbookValue = playbookInput?.value?.trim() || "";
        if (!playbookValue) {
          setAutomationFormMessage(
            messageTarget,
            "Playbook is required.",
            "error"
          );
          playbookInput?.focus();
          return;
        }

        const payload = {
          name: nameValue,
          playbook: playbookValue,
          description: descriptionInput?.value?.trim() || null,
        };

        if (cronInput) {
          payload.cron_expression = cronInput.value?.trim() || null;
        }

        if (triggerConditionsRoot) {
          const { conditions: selectedValues, errors: conditionErrors } =
            collectTriggerConditionValues();
          if (conditionErrors.length > 0) {
            setAutomationFormMessage(
              messageTarget,
              conditionErrors[0],
              "error"
            );
            return;
          }

          if (selectedValues.length > 0) {
            const matchValue =
              triggerMatchInput instanceof HTMLSelectElement &&
              triggerMatchInput.value === "all"
                ? "all"
                : "any";
            payload.trigger_filters = {
              match: matchValue,
              conditions: selectedValues,
            };
            payload.trigger = null;
          } else {
            payload.trigger_filters = null;
            payload.trigger = null;
          }
        } else if (
          triggerInput instanceof HTMLSelectElement &&
          triggerInput.multiple
        ) {
          const selectedValues = Array.from(triggerInput.selectedOptions)
            .map((option) => option.value)
            .filter((value) => value);
          if (selectedValues.length === 1) {
            payload.trigger = selectedValues[0];
          } else {
            payload.trigger = null;
          }

          if (selectedValues.length > 0) {
            const matchValue =
              triggerMatchInput instanceof HTMLSelectElement &&
              triggerMatchInput.value === "all"
                ? "all"
                : "any";
            payload.trigger_filters = {
              match: matchValue,
              conditions: selectedValues,
            };
          } else {
            payload.trigger_filters = null;
          }
        } else if (triggerInput) {
          payload.trigger = triggerInput.value?.trim() || null;
        }

        if (statusInput) {
          payload.status = statusInput.value?.trim() || null;
        }

        if (nextRunInput) {
          payload.next_run_at = localInputToIso(nextRunInput.value);
        }

        if (lastRunInput) {
          payload.last_run_at = localInputToIso(lastRunInput.value);
        }

        if (lastTriggerInput) {
          payload.last_trigger_at = localInputToIso(lastTriggerInput.value);
        }

        setAutomationFormMessage(messageTarget, "Updating automation…");
        const previousLabel = submitButton.textContent;
        submitButton.disabled = true;
        submitButton.textContent = "Saving…";

        try {
          const updated = await patchAutomation(automationId, payload);
          if (updated) {
            if (typeof updated.name === "string" && nameInput) {
              nameInput.value = updated.name;
            }
            if (typeof updated.playbook === "string" && playbookInput) {
              playbookInput.value = updated.playbook;
            }
            if (descriptionInput) {
              descriptionInput.value = updated.description || "";
            }
            if (cronInput) {
              cronInput.value = updated.cron_expression || "";
            }
            if (triggerConditionsRoot) {
              const updatedConditions = Array.isArray(
                updated.trigger_filters?.conditions
              )
                ? updated.trigger_filters.conditions
                : updated.trigger
                ? [updated.trigger]
                : [];
              setTriggerConditionValues(updatedConditions);
            } else if (
              triggerInput instanceof HTMLSelectElement &&
              triggerInput.multiple
            ) {
              const updatedConditions = Array.isArray(
                updated.trigger_filters?.conditions
              )
                ? updated.trigger_filters.conditions
                : updated.trigger
                ? [updated.trigger]
                : [];
              const conditionSet = new Set(updatedConditions);
              Array.from(triggerInput.options).forEach((option) => {
                option.selected = conditionSet.has(option.value);
              });
            } else if (triggerInput) {
              triggerInput.value = updated.trigger || "";
            }
            if (triggerMatchInput instanceof HTMLSelectElement) {
              const updatedMatch =
                updated.trigger_filters?.match === "all" ? "all" : "any";
              triggerMatchInput.value = updatedMatch;
            }
            if (statusInput) {
              statusInput.value = updated.status || "";
            }
            if (nextRunInput) {
              const nextIso = updated.next_run_at || "";
              nextRunInput.dataset.isoValue = nextIso;
              nextRunInput.value = nextIso ? isoToLocalInputValue(nextIso) : "";
            }
            if (lastRunInput) {
              const lastIso = updated.last_run_at || "";
              lastRunInput.dataset.isoValue = lastIso;
              lastRunInput.value = lastIso ? isoToLocalInputValue(lastIso) : "";
            }
            if (lastTriggerInput) {
              const triggerIso = updated.last_trigger_at || "";
              lastTriggerInput.dataset.isoValue = triggerIso;
              lastTriggerInput.value = triggerIso
                ? isoToLocalInputValue(triggerIso)
                : "";
            }
            if (form) {
              form.dataset.triggerFilters = JSON.stringify(
                updated.trigger_filters ?? null
              );
              form.dataset.triggerValue = updated.trigger || "";
            }
          }

          setAutomationFormMessage(
            messageTarget,
            "Automation updated successfully.",
            "success"
          );

          if (returnUrl) {
            setTimeout(() => {
              window.location.href = returnUrl;
            }, 900);
          }
        } catch (error) {
          setAutomationFormMessage(
            messageTarget,
            error?.message || "Unable to update automation.",
            "error"
          );
        } finally {
          submitButton.disabled = false;
          submitButton.textContent = previousLabel || "Save changes";
        }
      });
    }
  }

  const contactPage = document.querySelector("[data-role='contact-page']");
  if (contactPage) {
    const organizationId = contactPage.dataset.organizationId;
    if (!organizationId) {
      console.warn("Contact page missing organization identifier");
      return;
    }
    const contactTableBody = contactPage.querySelector("[data-role='contact-table-body']");
    const contactModal = document.querySelector("[data-role='contact-modal']");
    const contactForm = contactModal?.querySelector("#contact-form");
    const contactMessage = contactForm?.querySelector("[data-role='contact-form-message']");
    const contactSubmitButton = contactForm?.querySelector(
      "[data-role='contact-submit-label']"
    );
    const contactTitle = contactModal?.querySelector("[data-role='contact-form-title']");
    const contactIdInput = contactForm?.querySelector("[data-role='contact-id']");
    const contactFilter = contactPage.querySelector("[data-role='contact-filter']");
    const contactSearchInput = contactPage.querySelector("[data-role='table-filter']");
    const contactEmptyState = contactPage.querySelector("[data-role='contact-empty-state']");
    const contactCountTarget = contactPage.querySelector("[data-role='contact-count']");
    const newContactButton = document.querySelector("[data-action='contact-new']");
    const contactResetButton = contactForm?.querySelector("[data-action='contact-reset']");
    const contactCloseTriggers = contactModal
      ? contactModal.querySelectorAll("[data-action='contact-modal-close']")
      : [];
    const nameInput = contactForm?.querySelector("#contact-name");
    const jobInput = contactForm?.querySelector("#contact-job-title");
    const emailInput = contactForm?.querySelector("#contact-email");
    const phoneInput = contactForm?.querySelector("#contact-phone");
    const notesInput = contactForm?.querySelector("#contact-notes");
    let contactModalLastFocus = null;

    function getContactRows() {
      return contactTableBody
        ? Array.from(contactTableBody.querySelectorAll("[data-contact-row]"))
        : [];
    }

    function updateContactCount() {
      if (!contactCountTarget) {
        return;
      }
      contactCountTarget.textContent = String(getContactRows().length);
    }

    function updateEmptyState() {
      if (!contactEmptyState) {
        return;
      }
      const hasContacts = getContactRows().length > 0;
      contactEmptyState.classList.toggle("is-hidden", hasContacts);
    }

    function sanitizeValue(value) {
      if (value == null) {
        return "";
      }
      return typeof value === "string" ? value : String(value);
    }

    function normalizeContactPayload(raw) {
      if (!raw || typeof raw !== "object") {
        return null;
      }
      return {
        id: raw.id,
        organization_id: raw.organization_id,
        name: sanitizeValue(raw.name || ""),
        job_title: sanitizeValue(raw.job_title || ""),
        email: sanitizeValue(raw.email || ""),
        phone: sanitizeValue(raw.phone || ""),
        notes: sanitizeValue(raw.notes || ""),
        created_at_iso: sanitizeValue(raw.created_at || raw.created_at_iso || ""),
        updated_at_iso: sanitizeValue(raw.updated_at || raw.updated_at_iso || raw.created_at || ""),
      };
    }

    function applyFilterForRow(row) {
      if (!row) {
        return;
      }
      const filterValue = contactFilter ? contactFilter.value : "all";
      let matches = true;
      if (filterValue === "has-email") {
        matches = row.dataset.hasEmail === "true";
      } else if (filterValue === "has-phone") {
        matches = row.dataset.hasPhone === "true";
      }
      row.dataset.filterVisible = matches ? "true" : "false";
      updateTableRowVisibility(row);
    }

    function refreshFilters() {
      getContactRows().forEach((row) => {
        ensureVisibilityFlags(row);
        applyFilterForRow(row);
      });
    }

    function applySearchFilter() {
      if (contactSearchInput) {
        contactSearchInput.dispatchEvent(new Event("input"));
      }
    }

    function formatDatetimeCell(cell, isoValue) {
      if (!cell) {
        return;
      }
      const iso = isoValue || "";
      cell.dataset.sortValue = iso;
      cell.dataset.format = "datetime";
      if (!iso) {
        cell.textContent = "—";
        return;
      }
      const parsed = new Date(iso);
      cell.textContent = Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
    }

    function renderContactRow(contactPayload) {
      if (!contactTableBody) {
        return;
      }
      const contact = normalizeContactPayload(contactPayload);
      if (!contact) {
        return;
      }
      const contactId = String(contact.id);
      let row = contactTableBody.querySelector(
        `[data-contact-id='${contactId}']`
      );
      if (!row) {
        row = document.createElement("tr");
        row.dataset.contactRow = "true";
        row.dataset.contactId = contactId;
        contactTableBody.appendChild(row);
      }

      row.dataset.contact = JSON.stringify(contact);
      row.dataset.hasEmail = contact.email ? "true" : "false";
      row.dataset.hasPhone = contact.phone ? "true" : "false";

      while (row.firstChild) {
        row.removeChild(row.firstChild);
      }

      const nameCell = document.createElement("td");
      nameCell.dataset.sortValue = contact.name.toLowerCase();
      const nameWrapper = document.createElement("div");
      nameWrapper.className = "contact-name";
      nameWrapper.textContent = contact.name;
      nameCell.appendChild(nameWrapper);
      row.appendChild(nameCell);

      const jobCell = document.createElement("td");
      jobCell.dataset.sortValue = contact.job_title.toLowerCase();
      if (contact.job_title) {
        const jobSpan = document.createElement("span");
        jobSpan.className = "contact-job";
        jobSpan.textContent = contact.job_title;
        jobCell.appendChild(jobSpan);
      } else {
        const emptySpan = document.createElement("span");
        emptySpan.className = "contact-metadata contact-metadata--empty";
        emptySpan.textContent = "Not set";
        jobCell.appendChild(emptySpan);
      }
      row.appendChild(jobCell);

      const emailCell = document.createElement("td");
      emailCell.dataset.sortValue = contact.email.toLowerCase();
      if (contact.email) {
        const emailLink = document.createElement("a");
        emailLink.className = "contact-link";
        emailLink.href = `mailto:${contact.email}`;
        emailLink.textContent = contact.email;
        emailCell.appendChild(emailLink);
      } else {
        const emptySpan = document.createElement("span");
        emptySpan.className = "contact-metadata contact-metadata--empty";
        emptySpan.textContent = "No email";
        emailCell.appendChild(emptySpan);
      }
      row.appendChild(emailCell);

      const phoneCell = document.createElement("td");
      phoneCell.dataset.sortValue = contact.phone.toLowerCase();
      if (contact.phone) {
        const phoneLink = document.createElement("a");
        phoneLink.className = "contact-link";
        phoneLink.href = `tel:${contact.phone}`;
        phoneLink.textContent = contact.phone;
        phoneCell.appendChild(phoneLink);
      } else {
        const emptySpan = document.createElement("span");
        emptySpan.className = "contact-metadata contact-metadata--empty";
        emptySpan.textContent = "No phone";
        phoneCell.appendChild(emptySpan);
      }
      row.appendChild(phoneCell);

      const notesCell = document.createElement("td");
      notesCell.dataset.sortValue = contact.notes.toLowerCase();
      if (contact.notes) {
        const notesSpan = document.createElement("span");
        notesSpan.className = "contact-notes";
        notesSpan.textContent = contact.notes;
        notesSpan.title = contact.notes;
        notesCell.appendChild(notesSpan);
      } else {
        const emptySpan = document.createElement("span");
        emptySpan.className = "contact-metadata contact-metadata--empty";
        emptySpan.textContent = "No notes";
        notesCell.appendChild(emptySpan);
      }
      row.appendChild(notesCell);

      const updatedCell = document.createElement("td");
      formatDatetimeCell(updatedCell, contact.updated_at_iso);
      row.appendChild(updatedCell);

      const actionsCell = document.createElement("td");
      actionsCell.className = "table-actions";
      const actionsWrapper = document.createElement("div");
      actionsWrapper.className = "contact-actions";

      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "button button--ghost";
      editButton.dataset.action = "contact-edit";
      editButton.dataset.contactId = contactId;
      editButton.textContent = "✏️ Edit";
      actionsWrapper.appendChild(editButton);

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "button button--ghost";
      deleteButton.dataset.action = "contact-delete";
      deleteButton.dataset.contactId = contactId;
      deleteButton.textContent = "🗑️ Delete";
      actionsWrapper.appendChild(deleteButton);

      actionsCell.appendChild(actionsWrapper);
      row.appendChild(actionsCell);

      ensureVisibilityFlags(row);
      applyFilterForRow(row);
      updateTableRowVisibility(row);
      return row;
    }

    function resetContactForm() {
      if (!contactForm) {
        return;
      }
      contactForm.reset();
      contactForm.dataset.mode = "create";
      if (contactIdInput) {
        contactIdInput.value = "";
      }
      if (contactMessage) {
        setStatusMessage(contactMessage, "");
      }
    }

    function isContactModalOpen() {
      return contactModal?.classList.contains("is-visible") ?? false;
    }

    function openContactModal(mode, contactData) {
      if (!contactModal || !contactForm || isContactModalOpen()) {
        return;
      }
      const activeElement = document.activeElement;
      contactModalLastFocus =
        activeElement instanceof HTMLElement ? activeElement : null;
      contactModal.classList.add("is-visible");
      contactModal.setAttribute("aria-hidden", "false");
      document.body.classList.add("has-open-modal");
      contactForm.dataset.mode = mode;
      if (contactTitle) {
        contactTitle.textContent =
          mode === "edit" ? "Edit organisation contact" : "Add organisation contact";
      }
      if (contactSubmitButton) {
        contactSubmitButton.textContent =
          mode === "edit" ? "Save changes" : "Save contact";
      }
      if (contactMessage) {
        setStatusMessage(contactMessage, "");
      }

      if (mode === "edit" && contactData) {
        const payload = normalizeContactPayload(contactData);
        if (payload) {
          if (contactIdInput) {
            contactIdInput.value = String(payload.id);
          }
          if (nameInput) {
            nameInput.value = payload.name;
          }
          if (jobInput) {
            jobInput.value = payload.job_title;
          }
          if (emailInput) {
            emailInput.value = payload.email;
          }
          if (phoneInput) {
            phoneInput.value = payload.phone;
          }
          if (notesInput) {
            notesInput.value = payload.notes;
          }
        }
      } else {
        resetContactForm();
      }

      if (nameInput) {
        nameInput.focus();
      }
    }

    function closeContactModal({ resetForm = true } = {}) {
      if (!contactModal || !isContactModalOpen()) {
        return;
      }
      contactModal.classList.remove("is-visible");
      contactModal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("has-open-modal");
      if (resetForm) {
        resetContactForm();
      }
      if (contactModalLastFocus && typeof contactModalLastFocus.focus === "function") {
        contactModalLastFocus.focus();
      }
      contactModalLastFocus = null;
    }

    if (contactCloseTriggers.length) {
      contactCloseTriggers.forEach((trigger) => {
        trigger.addEventListener("click", () => {
          closeContactModal();
        });
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isContactModalOpen()) {
        event.preventDefault();
        closeContactModal();
      }
    });

    if (newContactButton) {
      newContactButton.addEventListener("click", () => {
        resetContactForm();
        openContactModal("create");
      });
    }

    if (contactResetButton) {
      contactResetButton.addEventListener("click", () => {
        resetContactForm();
        if (nameInput) {
          nameInput.focus();
        }
      });
    }

    function buildContactPayload() {
      if (!contactForm) {
        return null;
      }
      const formData = new FormData(contactForm);
      const normalize = (value) => {
        if (value == null) {
          return null;
        }
        const trimmed = String(value).trim();
        return trimmed ? trimmed : null;
      };
      const nameValue = normalize(formData.get("name"));
      if (!nameValue) {
        throw new Error("Name is required");
      }
      return {
        name: nameValue,
        job_title: normalize(formData.get("job_title")),
        email: normalize(formData.get("email")),
        phone: normalize(formData.get("phone")),
        notes: normalize(formData.get("notes")),
      };
    }

    async function sendContactRequest({ url, method, payload, errorMessage }) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const options = {
          method,
          headers: {
            Accept: "application/json",
          },
          credentials: "same-origin",
          signal: controller.signal,
        };
        if (payload) {
          options.headers["Content-Type"] = "application/json";
          options.body = JSON.stringify(payload);
        }
        const response = await fetch(url, options);
        if (method === "DELETE") {
          if (!response.ok) {
            const details = await response.json().catch(() => ({}));
            throw new Error(details.detail || errorMessage || "Unable to delete contact");
          }
          return null;
        }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || errorMessage || "Unable to save contact");
        }
        return data;
      } finally {
        clearTimeout(timeout);
      }
    }

    if (contactForm && contactTableBody) {
      contactForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        let payload;
        try {
          payload = buildContactPayload();
        } catch (error) {
          if (contactMessage) {
            setStatusMessage(contactMessage, error.message || "Invalid input", "error");
          }
          return;
        }

        if (contactMessage) {
          const mode = contactForm.dataset.mode === "edit" ? "edit" : "create";
          setStatusMessage(
            contactMessage,
            mode === "edit" ? "Saving contact…" : "Creating contact…"
          );
        }

        if (contactSubmitButton) {
          contactSubmitButton.disabled = true;
        }

        try {
          const mode = contactForm.dataset.mode === "edit" ? "edit" : "create";
          const contactId = contactIdInput?.value?.trim();
          if (mode === "edit" && !contactId) {
            throw new Error("Contact identifier missing");
          }
          const url =
            mode === "edit"
              ? `/api/organizations/${encodeURIComponent(organizationId)}/contacts/${encodeURIComponent(contactId || "")}`
              : `/api/organizations/${encodeURIComponent(organizationId)}/contacts`;
          const method = mode === "edit" ? "PATCH" : "POST";
          const responsePayload = await sendContactRequest({
            url,
            method,
            payload,
            errorMessage: mode === "edit" ? "Unable to update contact" : "Unable to create contact",
          });
          if (!responsePayload) {
            return;
          }
          const normalized = normalizeContactPayload(responsePayload);
          if (!normalized) {
            return;
          }
          renderContactRow(normalized);
          updateContactCount();
          updateEmptyState();
          applySearchFilter();
          refreshFilters();
          closeContactModal();
        } catch (error) {
          if (contactMessage) {
            setStatusMessage(
              contactMessage,
              error.message || "Unable to save contact",
              "error"
            );
          }
        } finally {
          if (contactSubmitButton) {
            contactSubmitButton.disabled = false;
          }
        }
      });

      contactTableBody.addEventListener("click", async (event) => {
        const editTrigger = event.target.closest("[data-action='contact-edit']");
        if (editTrigger) {
          const row = editTrigger.closest("[data-contact-row]");
          if (!row) {
            return;
          }
          try {
            const data = JSON.parse(row.dataset.contact || "{}");
            openContactModal("edit", data);
          } catch (error) {
            console.error("Unable to parse contact dataset", error);
          }
          return;
        }

        const deleteTrigger = event.target.closest("[data-action='contact-delete']");
        if (deleteTrigger) {
          const row = deleteTrigger.closest("[data-contact-row]");
          if (!row) {
            return;
          }
          let contactData = null;
          try {
            contactData = JSON.parse(row.dataset.contact || "{}");
          } catch (error) {
            console.error("Unable to parse contact dataset", error);
          }
          const confirmed = window.confirm(
            contactData?.name
              ? `Delete ${contactData.name}? This action cannot be undone.`
              : "Delete this contact?"
          );
          if (!confirmed) {
            return;
          }
          deleteTrigger.disabled = true;
          try {
            await sendContactRequest({
              url: `/api/organizations/${encodeURIComponent(
                organizationId
              )}/contacts/${encodeURIComponent(String(row.dataset.contactId || ""))}`,
              method: "DELETE",
              errorMessage: "Unable to delete contact",
            });
            row.remove();
            updateContactCount();
            updateEmptyState();
            applySearchFilter();
            refreshFilters();
          } catch (error) {
            window.alert(error.message || "Unable to delete contact");
          } finally {
            deleteTrigger.disabled = false;
          }
        }
      });
    }

    if (contactFilter) {
      contactFilter.addEventListener("change", () => {
        refreshFilters();
      });
    }

    refreshFilters();
    updateContactCount();
    updateEmptyState();
    applySearchFilter();
  }

  function resolveAutomationFeedback(button) {
    if (!button) {
      return document.querySelector("#automation-update-output");
    }
    const selector = button.dataset.feedback;
    if (selector) {
      const target = document.querySelector(selector);
      if (target) {
        return target;
      }
    }
    return document.querySelector("#automation-update-output");
  }

  const automationRunButtons = document.querySelectorAll(
    "[data-action='automation-run']"
  );

  automationRunButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const endpoint = button.dataset.endpoint;
      if (!endpoint) {
        console.warn("Automation run button missing endpoint", { button });
        return;
      }

      const feedbackTarget = resolveAutomationFeedback(button);
      const row = button.closest("[data-automation-row]");
      const lastRunCell = row?.querySelector("[data-cell='last_run']");
      const originalContent = button.innerHTML;

      button.disabled = true;
      button.innerHTML = "⏳";

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(
            typeof payload.detail === "string"
              ? payload.detail
              : "Unable to run automation"
          );
        }

        if (feedbackTarget) {
          feedbackTarget.textContent =
            payload.detail || "Automation queued for execution.";
        }

        if (payload.last_run_at && lastRunCell) {
          lastRunCell.dataset.sortValue = payload.last_run_at;
          let timeEl = lastRunCell.querySelector("time[data-role='local-datetime']");
          if (!timeEl) {
            timeEl = document.createElement("time");
            timeEl.dataset.role = "local-datetime";
            lastRunCell.innerHTML = "";
            lastRunCell.appendChild(timeEl);
          }
          timeEl.setAttribute("datetime", payload.last_run_at);
          const parsed = new Date(payload.last_run_at);
          timeEl.textContent = Number.isNaN(parsed.getTime())
            ? payload.last_run_at
            : parsed.toLocaleString();
        }
      } catch (error) {
        if (feedbackTarget) {
          feedbackTarget.textContent =
            error.message || "Unable to run automation";
        }
        window.alert(error.message || "Unable to run automation");
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.innerHTML = originalContent;
        }
      }
    });
  });

  const automationDeleteButtons = document.querySelectorAll(
    "[data-action='automation-delete']"
  );

  automationDeleteButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const endpoint = button.dataset.endpoint;
      if (!endpoint) {
        console.warn("Automation delete button missing endpoint", { button });
        return;
      }

      const row = button.closest("[data-automation-row]");
      const automationName =
        row?.querySelector(".automation-name__title")?.textContent?.trim() ||
        "this automation";
      const confirmed = window.confirm(
        `Delete ${automationName}? This action cannot be undone.`
      );
      if (!confirmed) {
        return;
      }

      const feedbackTarget = resolveAutomationFeedback(button);
      const originalContent = button.innerHTML;
      button.disabled = true;
      button.innerHTML = "…";

      try {
        const response = await fetch(endpoint, {
          method: "DELETE",
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });

        if (response.status !== 204) {
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(
              typeof payload.detail === "string"
                ? payload.detail
                : "Unable to delete automation"
            );
          }
        }

        if (row) {
          row.remove();
        }
        if (feedbackTarget) {
          feedbackTarget.textContent = `${automationName} deleted.`;
        }
      } catch (error) {
        if (feedbackTarget) {
          feedbackTarget.textContent =
            error.message || "Unable to delete automation";
        }
        window.alert(error.message || "Unable to delete automation");
      } finally {
        if (button.isConnected) {
          button.disabled = false;
          button.innerHTML = originalContent;
        }
      }
    });
  });

  const maintenanceButtons = document.querySelectorAll("[data-action='maintenance-run']");

  function resolveMaintenanceOutput(button) {
    const explicitSelector = button.dataset.output;
    if (explicitSelector) {
      const target = document.querySelector(explicitSelector);
      if (target) {
        return target;
      }
    }

    const scopedContainer = button.closest("[data-maintenance-container]") || button.parentElement;
    if (scopedContainer) {
      const existing = scopedContainer.querySelector("[data-role='maintenance-output']");
      if (existing) {
        return existing;
      }
      const created = document.createElement("pre");
      created.dataset.role = "maintenance-output";
      created.textContent = "Awaiting execution…";
      scopedContainer.appendChild(created);
      return created;
    }
    return null;
  }

  maintenanceButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const maintenanceOutput = resolveMaintenanceOutput(button);

      if (!maintenanceOutput) {
        console.warn("Maintenance action missing output target", {
          button,
        });
        return;
      }

      const endpoint = button.dataset.endpoint;
      if (!endpoint) {
        maintenanceOutput.textContent = "No endpoint defined for this action.";
        return;
      }

      const tokenFieldSelector = button.dataset.tokenField;
      let tokenValue = "";
      if (tokenFieldSelector) {
        const tokenField = document.querySelector(tokenFieldSelector);
        tokenValue = tokenField?.value?.trim() ?? "";
      }

      maintenanceOutput.textContent = `Executing ${endpoint}…`;
      button.disabled = true;

      try {
        const headers = {
          Accept: "application/json",
        };
        const fetchOptions = {
          method: "POST",
          headers,
          credentials: "same-origin",
        };
        if (tokenValue) {
          headers["Content-Type"] = "application/json";
          fetchOptions.body = JSON.stringify({ token: tokenValue });
        }

        const response = await fetch(endpoint, fetchOptions);
        const payload = await response.json().catch(() => ({ detail: "No response payload" }));
        if (!response.ok) {
          throw new Error(typeof payload.detail === "string" ? payload.detail : "Request failed");
        }
        maintenanceOutput.textContent = JSON.stringify(payload, null, 2);
      } catch (error) {
        maintenanceOutput.textContent = error.message || "Unable to execute script";
      } finally {
        button.disabled = false;
      }
    });
  });
})();
