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

  document.querySelectorAll('[data-sort-value]').forEach((cell) => {
    const value = cell.dataset.sortValue;
    if (!value) {
      return;
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      cell.textContent = parsed.toLocaleString();
    }
  });

  document.querySelectorAll("[data-role='table-filter']").forEach((filterInput) => {
    const container = filterInput.closest(".panel, .card, .table-container") || document;
    const table = container.querySelector("[data-role='sortable-table']");
    if (!table) {
      return;
    }
    filterInput.addEventListener("input", () => {
      const query = filterInput.value.toLowerCase();
      Array.from(table.tBodies[0].rows).forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? "" : "none";
      });
    });
  });

  const maintenanceOutput = document.querySelector("[data-role='maintenance-output']");
  const maintenanceTokenField = document.getElementById("maintenance-token");
  const maintenanceButtons = document.querySelectorAll("[data-action='maintenance-run']");

  maintenanceButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      if (!maintenanceTokenField || !maintenanceOutput) {
        return;
      }
      const token = maintenanceTokenField.value.trim();
      if (!token) {
        maintenanceOutput.textContent = "Enter the maintenance token before running a script.";
        return;
      }

      const endpoint = button.dataset.endpoint;
      if (!endpoint) {
        maintenanceOutput.textContent = "No endpoint defined for this action.";
        return;
      }

      maintenanceOutput.textContent = `Executing ${endpoint}…`;
      button.disabled = true;

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "X-Maintenance-Token": token,
            "Accept": "application/json",
          },
        });
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
