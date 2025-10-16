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
      if (!response.ok) {
        throw new Error(data.detail || "Request failed");
      }
      if (messageEl) {
        messageEl.textContent = "Success";
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

  const organizationForm = document.getElementById("organization-form");
  if (organizationForm && organizationTableBody) {
    const organizationModal = document.querySelector("[data-role='organization-modal']");
    const organizationModalBackdrop = organizationModal?.querySelector(
      "[data-role='organization-modal-backdrop']"
    );
    const organizationModalCloseButtons = organizationModal
      ? organizationModal.querySelectorAll("[data-action='organization-modal-close']")
      : [];
    let organizationModalLastFocus = null;
    const organizationPanel = organizationTableBody.closest(".panel");
    const organizationSearchInput = organizationPanel
      ? organizationPanel.querySelector("[data-role='table-filter']")
      : null;
    const messageTarget = organizationForm.querySelector(
      "[data-role='organization-message']"
    );
    const submitButton = organizationForm.querySelector(
      "[data-role='organization-submit-label']"
    );
    const titleTarget = organizationForm
      .closest(".organization-form")
      ?.querySelector("[data-role='organization-form-title']");
    const subtitleTarget = organizationForm
      .closest(".organization-form")
      ?.querySelector("[data-role='organization-form-subtitle']");
    const nameInput = organizationForm.querySelector("#organization-name");
    const slugInput = organizationForm.querySelector("#organization-slug");
    const contactInput = organizationForm.querySelector("#organization-contact");
    const descriptionInput = organizationForm.querySelector(
      "#organization-description"
    );
    const newButton = document.querySelector("[data-action='organization-new']");
    const resetButton = organizationForm.querySelector("[data-action='organization-reset']");
    let slugManuallyEdited = false;

    function isOrganizationModalOpen() {
      return organizationModal?.classList.contains("is-visible") ?? false;
    }

    function openOrganizationModal() {
      if (!organizationModal || isOrganizationModalOpen()) {
        return;
      }
      const activeElement = document.activeElement;
      organizationModalLastFocus =
        activeElement instanceof HTMLElement ? activeElement : null;
      organizationModal.classList.add("is-visible");
      organizationModal.setAttribute("aria-hidden", "false");
      document.body.classList.add("has-open-modal");
    }

    function closeOrganizationModal({ resetForm = true } = {}) {
      if (!organizationModal || !isOrganizationModalOpen()) {
        return;
      }
      organizationModal.classList.remove("is-visible");
      organizationModal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("has-open-modal");
      if (resetForm) {
        setFormMode("create", null, { focus: false });
      }
      if (organizationModalLastFocus && typeof organizationModalLastFocus.focus === "function") {
        organizationModalLastFocus.focus();
      }
      organizationModalLastFocus = null;
    }

    if (organizationModalBackdrop) {
      organizationModalBackdrop.addEventListener("click", () => {
        closeOrganizationModal();
      });
    }

    if (organizationModalCloseButtons.length) {
      organizationModalCloseButtons.forEach((button) => {
        button.addEventListener("click", () => {
          closeOrganizationModal();
        });
      });
    }

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && isOrganizationModalOpen()) {
        event.preventDefault();
        closeOrganizationModal();
      }
    });

    function slugifyOrganization(value) {
      return value
        .toLowerCase()
        .trim()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .replace(/-{2,}/g, "-");
    }

    function normalizeOrganizationPayload(payload) {
      return {
        id: payload.id,
        name: payload.name,
        slug: payload.slug,
        description: payload.description || "",
        contact_email: payload.contact_email || "",
        is_archived: Boolean(payload.is_archived),
        created_at_iso: payload.created_at || "",
        updated_at_iso: payload.updated_at || payload.created_at || "",
      };
    }

    function removeEmptyState() {
      const emptyRow = organizationTableBody.querySelector(".organization-empty");
      if (emptyRow) {
        emptyRow.remove();
      }
    }

    function renderOrganizationRow(data) {
      const row = document.createElement("tr");
      row.dataset.organizationRow = "true";
      row.dataset.organizationId = String(data.id);
      row.dataset.organization = JSON.stringify(data);
      row.dataset.status = data.is_archived ? "archived" : "active";
      row.dataset.filterVisible = row.dataset.filterVisible || "true";
      row.dataset.searchVisible = row.dataset.searchVisible || "true";

      const nameCell = document.createElement("td");
      nameCell.dataset.sortValue = data.name.toLowerCase();
      const nameLabel = document.createElement("div");
      nameLabel.className = "organization-name";
      nameLabel.textContent = data.name;
      const slugLabel = document.createElement("div");
      slugLabel.className = "organization-slug";
      slugLabel.textContent = data.slug;
      nameCell.appendChild(nameLabel);
      nameCell.appendChild(slugLabel);
      if (data.description) {
        const descriptionLabel = document.createElement("div");
        descriptionLabel.className = "organization-description";
        descriptionLabel.textContent = data.description;
        nameCell.appendChild(descriptionLabel);
      }
      row.appendChild(nameCell);

      const contactCell = document.createElement("td");
      contactCell.dataset.sortValue = data.contact_email || "";
      if (data.contact_email) {
        const contactLink = document.createElement("a");
        contactLink.className = "organization-contact";
        contactLink.href = `mailto:${data.contact_email}`;
        contactLink.textContent = data.contact_email;
        contactCell.appendChild(contactLink);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "organization-contact organization-contact--empty";
        placeholder.textContent = "Not provided";
        contactCell.appendChild(placeholder);
      }
      row.appendChild(contactCell);

      const statusCell = document.createElement("td");
      statusCell.dataset.sortValue = data.is_archived ? "archived" : "active";
      const statusBadge = document.createElement("span");
      statusBadge.className = `status-pill ${
        data.is_archived ? "status-pill--archived" : "status-pill--success"
      }`;
      statusBadge.setAttribute("data-role", "organization-status-label");
      statusBadge.textContent = data.is_archived ? "Archived" : "Active";
      statusCell.appendChild(statusBadge);
      row.appendChild(statusCell);

      const createdCell = document.createElement("td");
      createdCell.dataset.sortValue = data.created_at_iso || "";
      if (data.created_at_iso) {
        createdCell.dataset.format = "datetime";
        createdCell.textContent = toLocalDatetime(data.created_at_iso);
      } else {
        createdCell.textContent = "—";
      }
      row.appendChild(createdCell);

      const updatedCell = document.createElement("td");
      updatedCell.dataset.sortValue = data.updated_at_iso || "";
      if (data.updated_at_iso) {
        updatedCell.dataset.format = "datetime";
        updatedCell.textContent = toLocalDatetime(data.updated_at_iso);
      } else {
        updatedCell.textContent = "—";
      }
      row.appendChild(updatedCell);

      const actionsCell = document.createElement("td");
      actionsCell.className = "table-actions";
      const actionGroup = document.createElement("div");
      actionGroup.className = "organization-actions";
      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.className = "button button--ghost";
      editButton.dataset.action = "edit-organization";
      editButton.dataset.organizationId = String(data.id);
      editButton.textContent = "✏️ Edit";
      const archiveButton = document.createElement("button");
      archiveButton.type = "button";
      archiveButton.className = "button button--ghost";
      archiveButton.dataset.action = "toggle-organization-archive";
      archiveButton.dataset.organizationId = String(data.id);
      archiveButton.textContent = data.is_archived ? "Restore" : "Archive";
      actionGroup.appendChild(editButton);
      actionGroup.appendChild(archiveButton);
      actionsCell.appendChild(actionGroup);
      row.appendChild(actionsCell);

      return row;
    }

    function insertOrganizationRow(row) {
      removeEmptyState();
      const rows = Array.from(
        organizationTableBody.querySelectorAll("tr[data-organization-row]")
      );
      const sortValue = row.querySelector("td")?.dataset.sortValue || "";
      let inserted = false;
      for (const existing of rows) {
        const existingValue = existing.querySelector("td")?.dataset.sortValue || "";
        if (collator.compare(sortValue, existingValue) < 0) {
          organizationTableBody.insertBefore(row, existing);
          inserted = true;
          break;
        }
      }
      if (!inserted) {
        organizationTableBody.appendChild(row);
      }
      ensureVisibilityFlags(row);
      updateTableRowVisibility(row);
    }

    function getOrganizationRowById(id) {
      return organizationTableBody.querySelector(
        `tr[data-organization-row][data-organization-id='${id}']`
      );
    }

    function applyActiveFilters() {
      if (organizationStatusFilter) {
        organizationStatusFilter.dispatchEvent(new Event("change"));
      }
      if (organizationSearchInput) {
        organizationSearchInput.dispatchEvent(new Event("input"));
      }
    }

    function setFormMode(mode, data, options = {}) {
      const { focus = true } = options;
      organizationForm.dataset.mode = mode;
      if (mode === "edit" && data) {
        organizationForm.dataset.organizationId = String(data.id);
        nameInput.value = data.name;
        slugInput.value = data.slug;
        contactInput.value = data.contact_email || "";
        descriptionInput.value = data.description || "";
        if (submitButton) {
          submitButton.textContent = "Save changes";
        }
        if (titleTarget) {
          titleTarget.textContent = `Edit ${data.name}`;
        }
        if (subtitleTarget) {
          subtitleTarget.textContent =
            "Update organisation profile, rotate contacts, or archive when operations cease.";
        }
        slugManuallyEdited = true;
      } else {
        delete organizationForm.dataset.organizationId;
        organizationForm.reset();
        if (submitButton) {
          submitButton.textContent = "Create organisation";
        }
        if (titleTarget) {
          titleTarget.textContent = "Create new organisation";
        }
        if (subtitleTarget) {
          subtitleTarget.textContent =
            "Capture the organisation name, assign a slug for API usage, and optionally record the operations contact.";
        }
        slugManuallyEdited = false;
      }
      if (messageTarget) {
        setStatusMessage(messageTarget, "");
      }
      if (focus && nameInput) {
        nameInput.focus();
      }
    }

    function handleOrganizationSuccess(payload, mode) {
      const normalized = normalizeOrganizationPayload(payload);
      const existingRow = getOrganizationRowById(normalized.id);
      const newRow = renderOrganizationRow(normalized);
      if (existingRow) {
        const previousFilterVisible = existingRow.dataset.filterVisible;
        const previousSearchVisible = existingRow.dataset.searchVisible;
        organizationTableBody.removeChild(existingRow);
        if (previousFilterVisible) {
          newRow.dataset.filterVisible = previousFilterVisible;
        }
        if (previousSearchVisible) {
          newRow.dataset.searchVisible = previousSearchVisible;
        }
      }
      insertOrganizationRow(newRow);
      applyActiveFilters();
      if (mode === "create") {
        setFormMode("create");
      } else {
        setFormMode("edit", normalized);
      }
    }

    async function submitOrganization(payload, method, url) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(url, {
          method,
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
          throw new Error(data.detail || "Unable to save organization");
        }
        return data;
      } finally {
        clearTimeout(timeout);
      }
    }

    if (newButton) {
      newButton.addEventListener("click", () => {
        openOrganizationModal();
        setFormMode("create");
      });
    }

    if (resetButton) {
      resetButton.addEventListener("click", () => {
        setFormMode("create");
      });
    }

    organizationForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!nameInput || !slugInput || !submitButton) {
        return;
      }
      const mode = organizationForm.dataset.mode === "edit" ? "edit" : "create";
      const formPayload = {
        name: nameInput.value.trim(),
        slug: slugInput.value.trim(),
        contact_email: contactInput?.value.trim() || null,
        description: descriptionInput?.value.trim() || null,
      };
      if (formPayload.contact_email === "") {
        formPayload.contact_email = null;
      }
      if (formPayload.description === "") {
        formPayload.description = null;
      }

      if (!formPayload.slug) {
        formPayload.slug = slugifyOrganization(formPayload.name);
        slugInput.value = formPayload.slug;
      }

      if (messageTarget) {
        setStatusMessage(
          messageTarget,
          mode === "edit" ? "Saving changes…" : "Creating organisation…"
        );
      }

      submitButton.disabled = true;
      try {
        const organizationId = organizationForm.dataset.organizationId;
        const url =
          mode === "edit"
            ? `/api/organizations/${encodeURIComponent(organizationId)}`
            : "/api/organizations";
        const method = mode === "edit" ? "PATCH" : "POST";
        const payload = await submitOrganization(formPayload, method, url);
        handleOrganizationSuccess(payload, mode);
        if (messageTarget) {
          setStatusMessage(
            messageTarget,
            mode === "edit"
              ? `${payload.name} updated successfully.`
              : `${payload.name} created successfully.`,
            "success"
          );
        }
      } catch (error) {
        if (messageTarget) {
          setStatusMessage(
            messageTarget,
            error.message || "Unable to save organisation",
            "error"
          );
        }
      } finally {
        submitButton.disabled = false;
      }
    });

    organizationTableBody.addEventListener("click", async (event) => {
      const editTrigger = event.target.closest("[data-action='edit-organization']");
      if (editTrigger) {
        const organizationId = editTrigger.dataset.organizationId;
        const row = getOrganizationRowById(organizationId);
        if (!row) {
          return;
        }
        try {
          const data = JSON.parse(row.dataset.organization || "{}");
          openOrganizationModal();
          setFormMode("edit", data);
        } catch (error) {
          console.error("Unable to parse organization dataset", error);
        }
        return;
      }

      const archiveTrigger = event.target.closest(
        "[data-action='toggle-organization-archive']"
      );
      if (archiveTrigger) {
        const organizationId = archiveTrigger.dataset.organizationId;
        const row = getOrganizationRowById(organizationId);
        if (!row) {
          return;
        }
        let rowData;
        try {
          rowData = JSON.parse(row.dataset.organization || "{}");
        } catch (error) {
          console.error("Unable to parse organization dataset", error);
          return;
        }
        const desiredState = !rowData.is_archived;
        archiveTrigger.disabled = true;
        if (messageTarget) {
          setStatusMessage(
            messageTarget,
            desiredState ? "Archiving organisation…" : "Restoring organisation…"
          );
        }
        try {
          const payload = await submitOrganization(
            { is_archived: desiredState },
            "PATCH",
            `/api/organizations/${encodeURIComponent(organizationId)}`
          );
          handleOrganizationSuccess(payload, "edit");
          if (messageTarget) {
            setStatusMessage(
              messageTarget,
              desiredState ? "Organisation archived." : "Organisation restored.",
              "success"
            );
          }
        } catch (error) {
          if (messageTarget) {
            setStatusMessage(
              messageTarget,
              error.message || "Unable to update organisation",
              "error"
            );
          }
        } finally {
          archiveTrigger.disabled = false;
        }
      }
    });

    if (nameInput && slugInput) {
      nameInput.addEventListener("input", () => {
        if (!slugManuallyEdited && organizationForm.dataset.mode !== "edit") {
          slugInput.value = slugifyOrganization(nameInput.value);
        }
      });
      slugInput.addEventListener("input", () => {
        slugManuallyEdited = slugInput.value.trim().length > 0;
      });
    }
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
    const cadenceInput = form?.querySelector("#automation-cadence");
    const triggerInput = form?.querySelector("#automation-trigger");
    const statusInput = form?.querySelector("#automation-status");
    const nextRunInput = form?.querySelector("#automation-next-run");
    const lastRunInput = form?.querySelector("#automation-last-run");
    const lastTriggerInput = form?.querySelector("#automation-last-trigger");

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
          cadence: cadenceInput?.value?.trim() || null,
          trigger: triggerInput?.value?.trim() || null,
          status: statusInput?.value?.trim() || null,
          next_run_at: localInputToIso(nextRunInput?.value),
          last_run_at: localInputToIso(lastRunInput?.value),
          last_trigger_at: localInputToIso(lastTriggerInput?.value),
        };

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
            if (cadenceInput) {
              cadenceInput.value = updated.cadence || "";
            }
            if (triggerInput) {
              triggerInput.value = updated.trigger || "";
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
