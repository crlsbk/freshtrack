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

// ── Columnas numéricas a la derecha ──────────────────────────────────────────
// Si todas las celdas con texto de una columna son cifras ($, %, comas, unidades
// cortas), la columna y su encabezado se alinean a la derecha para comparar fácil.
document.addEventListener("DOMContentLoaded", () => {
  const esCifra = t => /^[-+$]?\s?[\d.,]+\s?(%|d|días?|u\.?|ms)?$/i.test(t);
  document.querySelectorAll("table").forEach(tabla => {
    const filas = [...tabla.querySelectorAll("tbody tr")].filter(f => !f.querySelector("td[colspan]"));
    if (!filas.length) return;
    const columnas = Math.max(...filas.map(f => f.children.length));
    for (let i = 0; i < columnas; i++) {
      const textos = filas.map(f => f.children[i]?.innerText.trim()).filter(Boolean);
      if (textos.length && textos.every(esCifra)) {
        filas.forEach(f => f.children[i]?.classList.add("num"));
        tabla.querySelector(`thead tr`)?.children[i]?.classList.add("num");
      }
    }
  });
});

// ── Ayuda (?) dentro de tarjetas enlazadas: mostrar, no navegar ─────────────
document.addEventListener("click", e => {
  const ayuda = e.target.closest(".ayuda");
  if (ayuda) { e.preventDefault(); e.stopPropagation(); ayuda.focus(); }
}, true);

// ── Pestañas de contenido (data-pestanas) ───────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-pestanas]").forEach(panel => {
    const botones = panel.querySelectorAll(":scope > .tabs [data-pestana]");
    const contenidos = panel.querySelectorAll(":scope > [data-pestana-id]");
    botones.forEach(b => b.addEventListener("click", () => {
      botones.forEach(x => x.classList.toggle("active", x === b));
      contenidos.forEach(c => { c.hidden = c.dataset.pestanaId !== b.dataset.pestana; });
    }));
  });
});
