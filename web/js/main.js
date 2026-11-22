/* Application Router, Topbar KPIs, Drawer Delegation & Bundle Loader */
window.LL = window.LL || {};

(function (LL) {
  function renderActiveView() {
    const root = document.getElementById("app-root");
    const v = LL.state.view;
    document.querySelectorAll(".nav-tab").forEach((el) => {
      const act = el.getAttribute("data-view") === v;
      el.classList.toggle("active", act);
      el.setAttribute("aria-selected", act ? "true" : "false");
    });

    if (v === "atlas") LL.renderAtlasView(root);
    else if (v === "vault") LL.renderVaultView(root);
    else if (v === "scale") LL.renderScaleView(root);
    else if (v === "compare") LL.renderCompareView(root);
    else if (v === "audit") LL.renderAuditView(root);
    else if (v === "graph") LL.renderGraphView(root);
    else if (v === "papers") LL.renderPapersView(root);
  }

  function hydrateTopbar(data) {
    const tagEl = document.getElementById("release-tag");
    if (tagEl) tagEl.textContent = data.tag || "pilot-v1";
    const nPanels = (data.panels || []).length;
    const nPlots = (data.panels || []).filter(LL.panelHasPlot).length;
    const nComp = (data.comparisons || []).length;
    const nClaims = (data.claims || []).length;
    const nFft = (data.panels || []).filter(LL.panelHasFft).length;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("cnt-atlas", nPanels);
    set("cnt-vault", nPlots);
    set("cnt-compare", nComp);
    set("cnt-audit", nClaims);

    const kpi = document.getElementById("kpi-inline");
    if (kpi) {
      kpi.textContent = `${(data.papers || []).length} OA papers · ${nPanels} panels · ${nFft} FFT · ${(data.summary && data.summary.n_digitized_series_points) || 0} pts`;
    }
  }

  function boot(data) {
    LL.state.data = data;
    hydrateTopbar(data);
    renderActiveView();

    document.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.onclick = () => {
        LL.state.view = btn.getAttribute("data-view");
        renderActiveView();
      };
    });

    const themeBtn = document.getElementById("btn-theme");
    if (themeBtn) {
      themeBtn.onclick = () => LL.setTheme(LL.isDark() ? "light" : "dark");
    }

    document.getElementById("drawer-close").onclick = LL.closeDrawer;
    document.getElementById("drawer-backdrop").onclick = LL.closeDrawer;

    // Global event delegation for opening Audit Drawer or jumping to a panel in Atlas
    document.body.addEventListener("click", (ev) => {
      const itemBtn = ev.target.closest("[data-open-item]");
      if (itemBtn) {
        LL.openItemDrawer(itemBtn.getAttribute("data-open-item"));
        return;
      }
      const jumpBtn = ev.target.closest("[data-jump-panel]");
      if (jumpBtn) {
        LL.closeDrawer();
        LL.state.selectedPanelId = jumpBtn.getAttribute("data-jump-panel");
        LL.state.atlasPaper = "ALL";
        LL.state.atlasArch = "ALL";
        LL.state.atlasOnlyFft = false;
        LL.state.atlasOnlyExt = false;
        LL.state.view = "atlas";
        renderActiveView();
      }
    });

    // Re-render current view canvases smoothly on live theme switch
    window.addEventListener("ll-theme-redraw", () => {
      if (["vault", "compare"].includes(LL.state.view)) renderActiveView();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (window.__LL_DATA__) {
      boot(window.__LL_DATA__);
    } else {
      fetch("data/bundle.json")
        .then((r) => r.json())
        .then((d) => boot(d))
        .catch((err) => {
          document.getElementById("app-root").innerHTML = `<div class="card">Failed to load bundle.json: ${LL.esc(err)}</div>`;
        });
    }
  });
})(window.LL);
