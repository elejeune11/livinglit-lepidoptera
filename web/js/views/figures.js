/* Unified Figures Workspace: Panel Atlas (594) · Digitized Plots (110) · True-Scale Micrographs */
window.LL = window.LL || {};

(function (LL) {
  LL.renderFiguresView = function (root) {
    const st = LL.state;
    const panels = (st.data && st.data.panels) || [];
    const nPanels = panels.length;
    const nPlots = panels.filter(LL.panelHasPlot).length;
    const nCal = panels.filter((p) => (p.data || {}).um_per_px != null && (p.data || {}).um_per_px < 0.5).length;

    const tab = st.figuresTab || "atlas";
    const subCopy = tab === "plots"
      ? "Verify digitized curves, scatter plots, boxplots, and dotplots overlaid directly on source crops with live re-plots, Python extractors, and CSV/JSON export."
      : (tab === "scale"
        ? "Compare calibrated micrographs rescaled to the exact same physical magnification (µm/px) across species and papers."
        : "Browse every atomic 1-letter figure panel with live 2D-FFT ridge gratings, scale bars, interactive drag-ROI periodicity, and verbatim caption quotes.");

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Figures, Digitized Plots &amp; Microscopy Metrology</h2>
          <div class="muted" style="margin-top:2px">${subCopy}</div>
        </div>
        <div class="seg-switch" role="tablist" aria-label="Figures workspace modes">
          <button type="button" class="seg-btn ${tab === "atlas" ? "active" : ""}" data-figures-tab="atlas" role="tab">Panel Atlas <span class="pill">${nPanels}</span></button>
          <button type="button" class="seg-btn ${tab === "plots" ? "active" : ""}" data-figures-tab="plots" role="tab">Digitized Plots <span class="pill">${nPlots}</span></button>
          <button type="button" class="seg-btn ${tab === "scale" ? "active" : ""}" data-figures-tab="scale" role="tab">True-Scale Micrographs <span class="pill">${nCal}</span></button>
        </div>
      </div>
      <div id="figures-body"></div>
    `;

    root.querySelectorAll("[data-figures-tab]").forEach((btn) => {
      btn.onclick = () => {
        st.figuresTab = btn.getAttribute("data-figures-tab");
        LL.renderFiguresView(root);
      };
    });

    const body = root.querySelector("#figures-body");
    if (tab === "plots") LL.renderVaultView(body);
    else if (tab === "scale") LL.renderScaleView(body);
    else LL.renderAtlasView(body);
  };
})(window.LL);
