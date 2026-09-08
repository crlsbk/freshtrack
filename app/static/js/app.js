// ── Sidebar collapse ────────────────────────────────────────────────────────
(function () {
  const sidebar = document.getElementById("sidebar");
  const toggle  = document.getElementById("sidebar-toggle");
  if (!sidebar || !toggle) return;
  const COLLAPSED_KEY = "sidebar_collapsed";
  if (localStorage.getItem(COLLAPSED_KEY) === "1") sidebar.classList.add("collapsed");
  toggle.addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    localStorage.setItem(COLLAPSED_KEY, sidebar.classList.contains("collapsed") ? "1" : "0");
  });
})();

// ── Tab switcher ─────────────────────────────────────────────────────────────
function initTabs(containerSelector) {
  document.querySelectorAll(containerSelector || ".tabs").forEach(tabBar => {
    const target = tabBar.dataset.target;
    tabBar.querySelectorAll(".tab").forEach(tab => {
      tab.addEventListener("click", () => {
        const panelId = tab.dataset.panel;
        tabBar.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        document.querySelectorAll(`[data-panel-id]`).forEach(p => {
          p.classList.toggle("active", p.dataset.panelId === panelId);
          p.style.display = p.dataset.panelId === panelId ? "" : "none";
        });
      });
    });
  });
}
document.addEventListener("DOMContentLoaded", () => initTabs());

// ── Form toggle ──────────────────────────────────────────────────────────────
function toggleForm(formId) {
  const form = document.getElementById(formId);
  if (!form) return;
  form.style.display = form.style.display === "none" ? "" : "none";
}

// ── Audit row expand ─────────────────────────────────────────────────────────
function toggleAuditRow(id) {
  const row = document.getElementById("audit-detail-" + id);
  if (!row) return;
  row.style.display = row.style.display === "none" ? "" : "none";
}

// ── Flash dismiss ────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash-dismiss").forEach(btn => {
    btn.addEventListener("click", () => btn.closest(".flash")?.remove());
  });
});

// ── Login: demo hints ────────────────────────────────────────────────────────
function toggleHints() {
  const hints = document.getElementById("login-hints");
  const btn   = document.getElementById("hints-toggle-btn");
  if (!hints) return;
  const visible = hints.style.display !== "none";
  hints.style.display = visible ? "none" : "";
  if (btn) btn.textContent = visible ? "Ver credenciales de demostración" : "Ocultar credenciales de demostración";
}

function fillLogin(email, password) {
  const emailInput    = document.getElementById("login-email");
  const passwordInput = document.getElementById("login-password");
  if (emailInput)    emailInput.value    = email;
  if (passwordInput) passwordInput.value = password;
}
