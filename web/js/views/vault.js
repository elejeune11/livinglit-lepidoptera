/* Digitized Quantitative Plot Vault: Interactive Re-Plot + Live Overlay Proof + Inline .py + CSV Export */
window.LL = window.LL || {};

(function (LL) {
  function panelToCsv(panel) {
    const d = panel.data || {};
    const rows = ["panel_id,series,kind,x,y,lo,hi,x_unit,y_unit"];
    Object.entries(d.curves || {}).forEach(([cn, c]) => {
      const xs = c.x || [], ys = c.y || [], lo = c.lo || [], hi = c.hi || [];
      for (let i = 0; i < xs.length; i++) {
        rows.push([panel.id, cn, "curve", xs[i], ys[i], lo[i] ?? "", hi[i] ?? "", c.x_unit || "", c.y_unit || ""].join(","));
      }
    });
    Object.entries(d.digitized_scatter || {}).forEach(([gn, g]) => {
      const xs = g.x || [], ys = g.y || [], ylo = g.y_lo || [], yhi = g.y_hi || [];
      for (let i = 0; i < xs.length; i++) {
        rows.push([panel.id, gn, "scatter", xs[i], ys[i], ylo[i] ?? "", yhi[i] ?? "", g.x_unit || "", g.y_unit || ""].join(","));
      }
    });
    Object.entries(d.digitized_boxplots || {}).forEach(([gn, b]) => {
      rows.push([panel.id, gn, "boxplot_median_iqr", gn, b.median ?? "", b.q1 ?? "", b.q3 ?? "", `whiskers:${b.whisker_lo}..${b.whisker_hi}`, b.y_unit || ""].join(","));
    });
    if (d.dotplot_matrix && d.dotplot_matrix.cells) {
      d.dotplot_matrix.cells.forEach((c) => {
        rows.push([panel.id, `${c.cluster}::${c.gene}`, "dotplot_cell", c.pct, c.expr, "", "", "%_expressing", "avg_expr"].join(","));
      });
    }
    return rows.join("\n") + "\n";
  }

  LL.renderVaultView = function (root) {
    const st = LL.state;
    const allPlots = (st.data.panels || []).filter(LL.panelHasPlot);
    const papers = [...new Set(allPlots.map((p) => p.paper))];
    const list = allPlots.filter((p) => st.vaultPaper === "ALL" || p.paper === st.vaultPaper);
    if (!st.selectedVaultId || !list.some((p) => p.id === st.selectedVaultId)) {
      const pref = list.find((p) => p.id === "2025_Loh/F10/B") || list.find((p) => p.id === "2026_Finet/F5/D_prime") || list.find((p) => p.id === "2024_Lloyd/F8/E") || list[0];
      st.selectedVaultId = pref ? pref.id : null;
    }
    const sel = list.find((p) => p.id === st.selectedVaultId) || null;
    const selDotCells = sel && sel.data && sel.data.dotplot_matrix && sel.data.dotplot_matrix.cells ? sel.data.dotplot_matrix.cells.length : 0;

    const extRel = sel && sel.extractor_script ? `${sel.paper}/${sel.extractor_script}` : null;
    const extSrc = extRel && st.data.extractor_scripts ? st.data.extractor_scripts[extRel] : null;

    root.innerHTML = `
      <div class="section-head" style="margin-bottom:8px">
        <h2>Digitized Plots &amp; Overlay Verification</h2>
        <span class="muted">Inspect extracted curves, scatter points, boxplots, and expression dotplots overlaid directly on original figure crops, re-plotted interactively with downloadable CSV/JSON and Python extractor code.</span>
      </div>
      <div class="toolbar">
        <select id="vt-paper" aria-label="Filter digitized plots by paper">
          <option value="ALL">All papers (${allPlots.length} digitized plots)</option>
          ${papers.map((pid) => `<option value="${LL.esc(pid)}" ${st.vaultPaper === pid ? "selected" : ""}>${LL.esc(pid)}</option>`).join("")}
        </select>
        <div style="display:flex;gap:5px;flex-wrap:wrap;flex:1;max-height:84px;overflow-y:auto;padding:2px 4px 2px 0" id="vt-pills">
          ${list.map((p) => `
            <button type="button" class="btn btn-sm ${p.id === st.selectedVaultId ? "primary" : ""}" data-vault-id="${LL.esc(p.id)}">
              ${LL.esc(p.paper.split("_")[1])} ${LL.esc(p.figure_id)}/${LL.esc(p.panel_label)}
            </button>`).join("")}
        </div>
      </div>
      ${sel ? `
        <div class="card" style="margin-bottom:14px">
          <div class="card-title">
            <div>
              <span class="mono">${LL.esc(sel.id)}</span>
              <span class="muted" style="margin-left:8px">${LL.esc(sel.title)}</span>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button type="button" class="btn btn-sm ${st.vaultOverlayOn ? "active" : ""}" id="vt-toggle-ov">${st.vaultOverlayOn ? "✓ " : ""}Overlay check</button>
              ${extSrc ? `<button type="button" class="btn btn-sm ${st.vaultShowCode ? "active" : ""}" id="vt-toggle-code">${LL.esc(sel.extractor_script.split("/").pop())}</button>` : ""}
              <button type="button" class="btn btn-sm" id="vt-dl-csv">CSV</button>
              <button type="button" class="btn btn-sm" id="vt-dl-json">JSON</button>
            </div>
          </div>

          <div class="vault-pair">
            <div>
              <div class="muted" style="margin-bottom:5px;font-weight:600">Source Figure Crop + Live Digitized Geometry Overlay</div>
              <div class="stage-wrap"><canvas id="vt-source-canvas"></canvas></div>
            </div>
            <div>
              <div class="muted" style="margin-bottom:5px;font-weight:600">Interactive Re-Plotted Data (${selDotCells ? `${selDotCells} dotplot cells` : `${sel.n_digitized_points} pts`})</div>
              <div class="chart-canvas-box"><canvas id="vt-chart-canvas"></canvas></div>
            </div>
          </div>

          ${st.vaultShowCode && extSrc ? `
            <div style="margin-top:12px">
              <div class="mono" style="font-size:11.5px;font-weight:600;margin-bottom:4px">Auditable extractor: records/${LL.esc(extRel)}</div>
              <pre class="code-viewer">${LL.esc(extSrc)}</pre>
            </div>` : ""}
        </div>
      ` : `<div class="card muted">No digitized plots match the filter.</div>`}
    `;

    if (sel) {
      const drawBoth = () => {
        const sc = document.getElementById("vt-source-canvas");
        const cc = document.getElementById("vt-chart-canvas");
        if (sc) LL.renderPanelCanvas(sc, sel, { overlayOn: st.vaultOverlayOn, maxW: 660, maxH: 400 });
        if (cc) LL.renderDigitizedChart(cc, sel);
      };
      drawBoth();
      const bOv = document.getElementById("vt-toggle-ov");
      if (bOv) bOv.onclick = () => { st.vaultOverlayOn = !st.vaultOverlayOn; LL.renderVaultView(root); };
      const bCode = document.getElementById("vt-toggle-code");
      if (bCode) bCode.onclick = () => { st.vaultShowCode = !st.vaultShowCode; LL.renderVaultView(root); };
      document.getElementById("vt-dl-csv").onclick = () => LL.downloadText(`${sel.id.replace(/\//g, "_")}.csv`, panelToCsv(sel), "text/csv");
      document.getElementById("vt-dl-json").onclick = () => LL.downloadText(`${sel.id.replace(/\//g, "_")}.json`, JSON.stringify(sel.data, null, 2), "application/json");
    }

    document.getElementById("vt-paper").onchange = (e) => { st.vaultPaper = e.target.value; LL.renderVaultView(root); };
    document.getElementById("vt-pills").onclick = (e) => {
      const b = e.target.closest("[data-vault-id]");
      if (!b) return;
      st.selectedVaultId = b.getAttribute("data-vault-id");
      LL.renderVaultView(root);
    };
  };
})(window.LL);
