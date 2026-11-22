/* Global application state, safe escaping, theme sync, and CSV/JSON export helpers */
window.LL = window.LL || {};

(function (LL) {
  LL.state = {
    view: "atlas",
    data: null,
    // Atlas filters
    atlasPaper: "ALL",
    atlasArch: "ALL",
    atlasOnlyFft: false,
    atlasOnlyExt: false,
    atlasQuery: "",
    selectedPanelId: null,
    atlasOverlayOn: true,
    atlasShowCode: false,
    atlasRoiMode: false,
    // Vault state
    vaultPaper: "ALL",
    selectedVaultId: null,
    vaultOverlayOn: true,
    vaultShowCode: false,
    // True-Scale Comparator
    scaleSelected: [],
    scalePxPerUm: 100,
    scaleOverlayOn: true,
    // Relaxed Compare (Shift #2): dimensions toggled to strict (true) vs relaxed (false)
    compareMeasure: "ALL",
    strictDims: {
      taxon: false,
      scale_type: false,
      functional_architecture: false,
      life_stage: false,
      perturbation_modality: false,
      imaging_modality: false,
      view_orientation: false,
      hydration_and_prep: false,
    },
    // Audit tab
    auditPaper: "ALL",
    auditVerdict: "ALL",
    // Graph tab
    graphFilter: "ALL",
    graphSelectedNode: null,
    // Vocab & Formulas Explorer tab
    schemaTab: "vocab",
    vocabField: "ALL",
    vocabQuery: "",
    vocabFilter: "all", // all | used | defined | synonyms
    vocabMode: "tree",  // tree | flat
    selectedTermId: null,
    formulaScope: "ALL", // ALL | lepidoptera | shared
    formulaKind: "ALL",  // ALL | model | definition | derived
    formulaOnlyUsed: false,
    formulaQuery: "",
    selectedFormulaId: null,
    formulaCalcInputs: {},
  };

  LL.esc = function (s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  };

  LL.fmtNum = function (v, digits) {
    if (v == null || Number.isNaN(Number(v))) return "—";
    const n = Number(v);
    if (Math.abs(n) >= 100) return n.toFixed(digits != null ? Math.min(digits, 1) : 1);
    if (Math.abs(n) >= 1) return n.toFixed(digits != null ? digits : 3);
    return n.toFixed(digits != null ? digits : 4);
  };

  LL.downloadText = function (filename, content, mime) {
    const blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  LL.panelHasPlot = function (p) {
    const d = p.data || {};
    return !!(d.curves || d.digitized_scatter || d.digitized_boxplots || d.dotplot_matrix);
  };

  LL.panelHasFft = function (p) {
    const d = p.data || {};
    return d.periodic_fft_um != null;
  };

  LL.panelQaInfo = function (p) {
    const qa = (LL.state.data && LL.state.data.qa_reports && LL.state.data.qa_reports[p.paper]) || {};
    return (qa.panels && qa.panels[p.id]) || null;
  };

  LL.getThumb = function (panelId) {
    const t = (LL.state.data && LL.state.data.thumbs) || {};
    return t[panelId] || null;
  };

  LL.isDark = function () {
    return document.documentElement.getAttribute("data-theme") === "dark" ||
      document.documentElement.classList.contains("dark");
  };

  LL.setTheme = function (theme) {
    const t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    const btn = document.getElementById("btn-theme");
    if (btn) btn.textContent = t === "dark" ? "Light mode" : "Dark mode";
    window.dispatchEvent(new CustomEvent("ll-theme-redraw", { detail: { theme: t } }));
  };

  // Sync with host iframe themechange events (and manual toggle button)
  window.addEventListener("themechange", function (ev) {
    const d = ev && ev.detail;
    const dark = (d && (d.theme === "dark" || d === "dark")) ||
      document.documentElement.classList.contains("dark");
    LL.setTheme(dark ? "dark" : "light");
  });
})(window.LL);
