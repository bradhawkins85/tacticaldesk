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
      const targetUrl = webhookAdminButton.getAttribute("data-href") || "/admin/maintenance#webhook-monitor";
      window.location.href = targetUrl;
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
