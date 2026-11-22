/* Application Router, Topbar KPIs, Drawer Delegation & Bundle Loader */
window.LL = window.LL || {};

(function (LL) {
  function renderActiveView() {
    const root = document.getElementById("app-root");
    let v = LL.state.view || "overview";
    // Backward compatibility for legacy subview names
    if (v === "atlas" || v === "vault" || v === "scale") {
      LL.state.figuresTab = v === "vault" ? "plots" : v;
      v = "figures";
      LL.state.view = "figures";
    }

    document.querySelectorAll(".nav-tab").forEach((el) => {
      const act = el.getAttribute("data-view") === v;
      el.classList.toggle("active", act);
      el.setAttribute("aria-selected", act ? "true" : "false");
    });

    if (v === "overview") LL.renderOverviewView(root);
    else if (v === "figures") LL.renderFiguresView(root);
    else if (v === "compare") LL.renderCompareView(root);
    else if (v === "audit") LL.renderAuditView(root);
    else if (v === "graph") LL.renderGraphView(root);
    else if (v === "schema") LL.renderVocabFormulasView(root);
    else if (v === "papers") LL.renderPapersView(root);
    else LL.renderOverviewView(root);
  }

  function hydrateTopbar(data) {
    const tagEl = document.getElementById("release-tag");
    if (tagEl) tagEl.textContent = data.tag || "pilot-v1";
    const nPanels = (data.panels || []).length;
    const nClaims = (data.claims || []).length;
    const nFft = (data.panels || []).filter(LL.panelHasFft).length;
    const nGrn = (data.genetic_relations || []).length;
    const nPapers = (data.papers || []).length;

    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set("cnt-figures", nPanels);
    set("cnt-audit", nClaims);
    set("cnt-grn", nGrn || "");
    set("cnt-papers", nPapers);

    const kpi = document.getElementById("kpi-inline");
    if (kpi) {
      kpi.textContent = `${nPapers} OA papers · ${nPanels} panels · ${nFft} FFT · ${nGrn} GRN · ${(data.summary && data.summary.n_digitized_series_points) || 0} pts`;
    }
  }

  function boot(data) {
    LL.state.data = data;
    hydrateTopbar(data);
    renderActiveView();

    document.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.onclick = () => {
        LL.state.view = btn.getAttribute("data-view");
        window.scrollTo(0, 0);
        renderActiveView();
      };
    });

    const themeBtn = document.getElementById("btn-theme");
    if (themeBtn) {
      themeBtn.onclick = () => LL.setTheme(LL.isDark() ? "light" : "dark");
    }

    document.getElementById("drawer-close").onclick = LL.closeDrawer;
    document.getElementById("drawer-backdrop").onclick = LL.closeDrawer;

    // Global event delegation for Audit Drawer & cross-tab jumps
    document.body.addEventListener("click", (ev) => {
      const itemBtn = ev.target.closest("[data-open-item]");
      if (itemBtn) {
        LL.openItemDrawer(itemBtn.getAttribute("data-open-item"));
        return;
      }
      const viewBtn = ev.target.closest("[data-jump-view]");
      if (viewBtn) {
        LL.closeDrawer();
        LL.state.view = viewBtn.getAttribute("data-jump-view") || "overview";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const figTabBtn = ev.target.closest("[data-jump-figures-tab]");
      if (figTabBtn) {
        LL.closeDrawer();
        LL.state.figuresTab = figTabBtn.getAttribute("data-jump-figures-tab") || "atlas";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const jumpPlotBtn = ev.target.closest("[data-jump-plot]");
      if (jumpPlotBtn) {
        LL.closeDrawer();
        LL.state.vaultPaper = "ALL";
        LL.state.vaultQuery = "";
        LL.state.selectedVaultId = jumpPlotBtn.getAttribute("data-jump-plot");
        LL.state.figuresTab = "plots";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
        renderActiveView();
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
        LL.state.figuresTab = "atlas";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
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
        LL.state.figuresTab = "atlas";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const pAtlasBtn = ev.target.closest("[data-jump-paper-atlas]");
      if (pAtlasBtn) {
        LL.closeDrawer();
        LL.state.atlasPaper = pAtlasBtn.getAttribute("data-jump-paper-atlas");
        LL.state.atlasArch = "ALL";
        LL.state.atlasOnlyFft = false;
        LL.state.atlasOnlyExt = false;
        LL.state.atlasQuery = "";
        LL.state.selectedPanelId = null;
        LL.state.figuresTab = "atlas";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const pPlotsBtn = ev.target.closest("[data-jump-paper-plots]");
      if (pPlotsBtn) {
        LL.closeDrawer();
        LL.state.vaultPaper = pPlotsBtn.getAttribute("data-jump-paper-plots");
        LL.state.vaultQuery = "";
        LL.state.selectedVaultId = null;
        LL.state.figuresTab = "plots";
        LL.state.view = "figures";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const pAuditBtn = ev.target.closest("[data-jump-paper-audit]");
      if (pAuditBtn) {
        LL.closeDrawer();
        LL.state.auditPaper = pAuditBtn.getAttribute("data-jump-paper-audit");
        LL.state.auditVerdict = "ALL";
        LL.state.auditTab = "claims";
        LL.state.view = "audit";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const pGrnBtn = ev.target.closest("[data-jump-paper-grn]");
      if (pGrnBtn) {
        LL.closeDrawer();
        LL.state.graphTab = "grn";
        LL.state.grnPaper = pGrnBtn.getAttribute("data-jump-paper-grn");
        LL.state.grnTier = "ALL";
        LL.state.grnSelectedRel = null;
        LL.state.view = "graph";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const auTabBtn = ev.target.closest("[data-jump-audit-tab]");
      if (auTabBtn) {
        LL.closeDrawer();
        LL.state.auditPaper = "ALL";
        LL.state.auditTab = auTabBtn.getAttribute("data-jump-audit-tab") || "claims";
        LL.state.view = "audit";
        window.scrollTo(0, 0);
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
        window.scrollTo(0, 0);
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
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const grnBtn = ev.target.closest("[data-jump-grn]");
      if (grnBtn) {
        LL.closeDrawer();
        const rid = grnBtn.getAttribute("data-jump-grn");
        const tabHint = grnBtn.getAttribute("data-jump-grn-tab");
        LL.state.graphTab = tabHint || "grn";
        LL.state.grnPaper = "ALL";
        LL.state.grnTier = "ALL";
        if (rid) LL.state.grnSelectedRel = rid;
        LL.state.view = "graph";
        window.scrollTo(0, 0);
        renderActiveView();
        return;
      }
      const cmpBtn = ev.target.closest("[data-jump-compare-measure]");
      if (cmpBtn) {
        LL.closeDrawer();
        LL.state.compareMeasure = cmpBtn.getAttribute("data-jump-compare-measure") || "measure:ridge_spacing";
        LL.state.view = "compare";
        window.scrollTo(0, 0);
        renderActiveView();
      }
    });

    // Re-render current view canvases/SVGs smoothly on live theme switch
    window.addEventListener("ll-theme-redraw", () => {
      if (["overview", "figures", "compare", "graph"].includes(LL.state.view)) renderActiveView();
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
