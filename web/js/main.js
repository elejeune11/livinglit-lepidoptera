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
    else if (v === "schema") LL.renderVocabFormulasView(root);
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
    const nTerms = (data.terms || []).length;
    const nFormulas = (data.formulas || []).length;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("cnt-atlas", nPanels);
    set("cnt-vault", nPlots);
    set("cnt-compare", nComp);
    set("cnt-audit", nClaims);
    set("cnt-schema", `${nTerms}·${nFormulas}`);

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

    // Global event delegation for Audit Drawer & cross-tab jumps (panels, terms, formulas, compare)
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
        LL.state.atlasQuery = "";
        LL.state.view = "atlas";
        renderActiveView();
        return;
      }
      const atlasQBtn = ev.target.closest("[data-jump-atlas-query]");
      if (atlasQBtn) {
        LL.closeDrawer();
        LL.state.atlasPaper = "ALL";
        LL.state.atlasArch = "ALL";
        LL.state.atlasOnlyFft = false;
        LL.state.atlasOnlyExt = false;
        LL.state.atlasQuery = atlasQBtn.getAttribute("data-jump-atlas-query") || "";
        LL.state.selectedPanelId = null;
        LL.state.view = "atlas";
        renderActiveView();
        return;
      }
      const termBtn = ev.target.closest("[data-jump-term]");
      if (termBtn) {
        LL.closeDrawer();
        const tid = termBtn.getAttribute("data-jump-term");
        const fieldHint = termBtn.getAttribute("data-jump-field");
        LL.state.schemaTab = "vocab";
        LL.state.vocabQuery = "";
        LL.state.vocabFilter = "all";
        if (fieldHint) LL.state.vocabField = fieldHint;
        else if (tid && tid.includes(":")) LL.state.vocabField = tid.split(":")[0];
        else LL.state.vocabField = "ALL";
        if (tid) LL.state.selectedTermId = tid;
        LL.state.view = "schema";
        renderActiveView();
        return;
      }
      const formulaBtn = ev.target.closest("[data-jump-formula]");
      if (formulaBtn) {
        LL.closeDrawer();
        const fid = formulaBtn.getAttribute("data-jump-formula");
        const scopeHint = formulaBtn.getAttribute("data-jump-scope");
        LL.state.schemaTab = "formulas";
        LL.state.formulaQuery = "";
        LL.state.formulaKind = "ALL";
        LL.state.formulaOnlyUsed = false;
        LL.state.formulaScope = scopeHint || "ALL";
        if (fid) LL.state.selectedFormulaId = fid;
        LL.state.view = "schema";
        renderActiveView();
        return;
      }
      const cmpBtn = ev.target.closest("[data-jump-compare-measure]");
      if (cmpBtn) {
        LL.closeDrawer();
        LL.state.compareMeasure = cmpBtn.getAttribute("data-jump-compare-measure") || "ALL";
        LL.state.view = "compare";
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
