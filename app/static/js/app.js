// ── Theme Switcher (Modo Claro / Modo Oscuro) ──────────────────────────────
(function () {
  const THEME_KEY = "freshtrack_theme";
  const temaGuardado = localStorage.getItem(THEME_KEY);
  const prefiereOscuro = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const temaInicial = temaGuardado || (prefiereOscuro ? "dark" : "light");

  document.documentElement.setAttribute("data-theme", temaInicial);

  document.addEventListener("DOMContentLoaded", () => {
    const botonTema = document.getElementById("theme-toggle");
    if (!botonTema) return;

    botonTema.addEventListener("click", () => {
      const temaActual = document.documentElement.getAttribute("data-theme") || "light";
      const nuevoTema = temaActual === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", nuevoTema);
      localStorage.setItem(THEME_KEY, nuevoTema);

      if (window.Chart && window.Chart.instances) {
        Object.values(window.Chart.instances).forEach(chart => {
          try {
            const esOscuro = nuevoTema === "dark";
            const colorTexto = esOscuro ? "#8fa495" : "#64748b";
            const colorGrid = esOscuro ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.05)";
            if (chart.options?.scales?.x) {
              if (chart.options.scales.x.ticks) chart.options.scales.x.ticks.color = colorTexto;
              if (chart.options.scales.x.grid) chart.options.scales.x.grid.color = colorGrid;
            }
            if (chart.options?.scales?.y) {
              if (chart.options.scales.y.ticks) chart.options.scales.y.ticks.color = colorTexto;
              if (chart.options.scales.y.grid) chart.options.scales.y.grid.color = colorGrid;
            }
            chart.update();
          } catch (_) {}
        });
      }
    });
  });
})();

// ── Sidebar collapse & restore ──────────────────────────────────────────────
(function () {
  const sidebar = document.getElementById("sidebar");
  const toggle  = document.getElementById("sidebar-toggle");
  const logoBtn = document.getElementById("sidebar-logo-btn");
  if (!sidebar) return;
  const COLLAPSED_KEY = "sidebar_collapsed";
  if (localStorage.getItem(COLLAPSED_KEY) === "1") sidebar.classList.add("collapsed");

  const alternarSidebar = (e) => {
    if (e) e.preventDefault();
    sidebar.classList.toggle("collapsed");
    const estaColapsado = sidebar.classList.contains("collapsed");
    localStorage.setItem(COLLAPSED_KEY, estaColapsado ? "1" : "0");
  };

  if (toggle) toggle.addEventListener("click", alternarSidebar);
  if (logoBtn) logoBtn.addEventListener("click", alternarSidebar);
})();

// ── Selector dinámico de ventana de tiempo para métricas ───────────────────
document.addEventListener("DOMContentLoaded", () => {
  const botonesVentana = document.querySelectorAll(".btn-ventana");
  if (!botonesVentana.length) return;

  botonesVentana.forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      const dias = btn.dataset.dias;
      botonesVentana.forEach(b => b.classList.toggle("active", b.dataset.dias === dias));

      try {
        const res = await fetch(`/api/kpis/ventana?dias=${dias}`);
        if (!res.ok) throw new Error("Error en consulta de métricas");
        const data = await res.json();

        // 1. Resumen: Ventas
        const elVentasValor = document.getElementById("kpi-ventas-ingreso");
        const elVentasSub = document.getElementById("kpi-ventas-sub");
        if (elVentasValor) elVentasValor.textContent = data.ventas.ingreso_formato;
        if (elVentasSub) elVentasSub.textContent = `${data.ventas.unidades_formato} unidades vendidas`;

        // 2. Resumen: Merma
        const elMermaValor = document.getElementById("kpi-merma-valor");
        const elMermaSub = document.getElementById("kpi-merma-sub");
        if (elMermaValor) elMermaValor.textContent = data.merma.valor_formato;
        if (elMermaSub) elMermaSub.textContent = `${data.merma.unidades_formato} unidades perdidas`;

        // 3. Resumen: Tasa de merma
        const elTasaValor = document.getElementById("kpi-tasa-valor");
        const elTasaSub = document.getElementById("kpi-tasa-sub");
        if (elTasaValor) elTasaValor.textContent = `${data.tasa.tasa_pct}%`;
        if (elTasaSub) elTasaSub.textContent = `De lo recibido en ${data.etiqueta_periodo.toLowerCase()}`;

        // 4. Detalle pestaña Ventas
        const elTabVentasUds = document.getElementById("tab-ventas-unidades");
        const elTabVentasTickets = document.getElementById("tab-ventas-tickets");
        const elTabVentasSub = document.getElementById("tab-ventas-sub");
        if (elTabVentasUds) elTabVentasUds.textContent = data.ventas.unidades_formato;
        if (elTabVentasTickets) elTabVentasTickets.textContent = data.ventas.tickets_formato;
        if (elTabVentasSub) elTabVentasSub.textContent = data.etiqueta_periodo;

        // 5. Detalle pestaña Merma
        const elTabMermaValor = document.getElementById("tab-merma-valor");
        const elTabMermaUds = document.getElementById("tab-merma-unidades");
        const elTabMermaEventos = document.getElementById("tab-merma-eventos");
        const elTabMermaTasa = document.getElementById("tab-merma-tasa");
        const elTabMermaTasaSub = document.getElementById("tab-merma-tasa-sub");
        if (elTabMermaValor) elTabMermaValor.textContent = data.merma.valor_formato;
        if (elTabMermaUds) elTabMermaUds.textContent = data.merma.unidades_formato;
        if (elTabMermaEventos) elTabMermaEventos.textContent = `${data.merma.eventos_formato} registros de merma`;
        if (elTabMermaTasa) elTabMermaTasa.textContent = `${data.tasa.tasa_pct}%`;
        if (elTabMermaTasaSub) elTabMermaTasaSub.textContent = `${data.tasa.mermado_formato} de ${data.tasa.recibido_formato} unidades recibidas (${data.etiqueta_periodo.toLowerCase()})`;

      } catch (err) {
        console.error("Error al consultar métricas reales:", err);
      }
    });
  });
});

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
