/* Digitized Plots Workspace: Master-Detail Plot List + Source Crop Overlay + Interactive Re-Plot + Inline .py + CSV/JSON */
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

  function plotKindTag(p) {
    const d = p.data || {};
    if (d.dotplot_matrix && d.dotplot_matrix.cells) return `${d.dotplot_matrix.cells.length} cells`;
    if (d.digitized_boxplots && Object.keys(d.digitized_boxplots).length) return `${p.n_digitized_points || Object.keys(d.digitized_boxplots).length} box`;
    if (d.curves && Object.keys(d.curves).length) return `${p.n_digitized_points} pts`;
    if (d.digitized_scatter && Object.keys(d.digitized_scatter).length) return `${p.n_digitized_points} pts`;
    return `${p.n_digitized_points || 0} pts`;
  }

  LL.renderVaultView = function (root) {
    const st = LL.state;
    const allPlots = (st.data.panels || []).filter(LL.panelHasPlot);
    const papers = [...new Set(allPlots.map((p) => p.paper))];
    const q = (st.vaultQuery || "").trim().toLowerCase();
    const list = allPlots.filter((p) => {
      if (st.vaultPaper !== "ALL" && p.paper !== st.vaultPaper) return false;
      if (q) {
        const hay = `${p.id} ${p.title} ${p.paper} ${JSON.stringify(p.context || {})}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    if (!st.selectedVaultId || !list.some((p) => p.id === st.selectedVaultId)) {
      const pref = list.find((p) => p.id === "2020_Stavenga/F5/A")
        || list.find((p) => p.id === "2025_Loh/F10/B")
        || list.find((p) => p.id === "2026_Finet/F5/D_prime")
        || list[0];
      st.selectedVaultId = pref ? pref.id : null;
    }
    const sel = list.find((p) => p.id === st.selectedVaultId) || null;
    const selDotCells = sel && sel.data && sel.data.dotplot_matrix && sel.data.dotplot_matrix.cells ? sel.data.dotplot_matrix.cells.length : 0;

    const extRel = sel && sel.extractor_script ? `${sel.paper}/${sel.extractor_script}` : null;
    const extSrc = extRel && st.data.extractor_scripts ? st.data.extractor_scripts[extRel] : null;

    root.innerHTML = `
      <div class="plots-shell">
        <aside class="card plots-sidebar" aria-label="Digitized plot selector">
          <div style="display:flex;flex-direction:column;gap:7px;margin-bottom:9px">
            <select id="vt-paper" aria-label="Filter digitized plots by paper">
              <option value="ALL">All papers (${allPlots.length} plots)</option>
              ${papers.map((pid) => {
                const cnt = allPlots.filter((p) => p.paper === pid).length;
                return `<option value="${LL.esc(pid)}" ${st.vaultPaper === pid ? "selected" : ""}>${LL.esc(pid)} (${cnt})</option>`;
              }).join("")}
            </select>
            <input type="search" id="vt-q" placeholder="Filter plots by figure or topic…" value="${LL.esc(st.vaultQuery || "")}" />
            <div class="muted mono" style="font-size:11px">Showing ${list.length} of ${allPlots.length} digitized plots</div>
          </div>

          <div class="plots-list" id="vt-list">
            ${list.map((p) => `
              <button type="button" class="plot-row-btn ${p.id === st.selectedVaultId ? "selected" : ""}" data-vault-id="${LL.esc(p.id)}">
                <div class="plot-row-top">
                  <span class="mono" style="font-weight:700;font-size:11.5px">${LL.esc(p.paper.split("_")[1])} · ${LL.esc(p.figure_id)}/${LL.esc(p.panel_label)}</span>
                  <span class="pill" style="font-size:10px">${LL.esc(plotKindTag(p))}</span>
                </div>
                <div class="plot-row-title muted">${LL.esc(p.title)}</div>
              </button>`).join("") || `<div class="muted" style="padding:14px">No digitized plots match that filter.</div>`}
          </div>
        </aside>

        <div class="plots-stage">
          ${sel ? `
            <div class="card">
              <div class="card-title" style="align-items:flex-start">
                <div>
                  <div class="mono" style="font-weight:700;font-size:13.5px">${LL.esc(sel.id)}</div>
                  <div class="muted" style="margin-top:2px;font-weight:500">${LL.esc(sel.title)}</div>
                </div>
                <div style="display:flex;gap:6px;flex-wrap:wrap">
                  <button type="button" class="btn btn-sm ${st.vaultOverlayOn ? "active" : ""}" id="vt-toggle-ov">${st.vaultOverlayOn ? "✓ " : ""}Overlay check</button>
                  ${extSrc ? `<button type="button" class="btn btn-sm ${st.vaultShowCode ? "active" : ""}" id="vt-toggle-code">${LL.esc(sel.extractor_script.split("/").pop())}</button>` : ""}
                  <button type="button" class="btn btn-sm" id="vt-dl-csv">CSV</button>
                  <button type="button" class="btn btn-sm" id="vt-dl-json">JSON</button>
                  <button type="button" class="btn btn-sm" data-jump-panel="${LL.esc(sel.id)}">In Atlas ↗</button>
                </div>
              </div>

              <div class="vault-pair">
                <div>
                  <div class="muted" style="margin-bottom:5px;font-weight:600;font-size:12px">Source Figure Crop + Live Digitized Overlay</div>
                  <div class="stage-wrap"><canvas id="vt-source-canvas"></canvas></div>
                </div>
                <div>
                  <div class="muted" style="margin-bottom:5px;font-weight:600;font-size:12px">Interactive Re-Plotted Data (${selDotCells ? `${selDotCells} dotplot cells` : `${sel.n_digitized_points} pts`})</div>
                  <div class="chart-canvas-box"><canvas id="vt-chart-canvas"></canvas></div>
                </div>
              </div>

              ${(sel.linked_items || []).length ? `
                <div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                  <span class="muted" style="font-size:11.5px;font-weight:600">Linked evidence:</span>
                  ${sel.linked_items.map((iid) => `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(sel.paper)}/${LL.esc(iid)}">${LL.esc(iid)} ↗</button>`).join("")}
                </div>` : ""}

              ${st.vaultShowCode && extSrc ? `
                <div style="margin-top:12px">
                  <div class="mono" style="font-size:11.5px;font-weight:600;margin-bottom:4px">Auditable extractor: records/${LL.esc(extRel)}</div>
                  <pre class="code-viewer">${LL.esc(extSrc)}</pre>
                </div>` : ""}
            </div>
          ` : `<div class="card muted">Select a digitized plot on the left to inspect its source overlay and extracted values.</div>`}
        </div>
      </div>
    `;

    const activeRow = root.querySelector(".plot-row-btn.selected");
    if (activeRow && activeRow.scrollIntoView) {
      activeRow.scrollIntoView({ block: "nearest" });
    }

    if (sel) {
      const drawBoth = () => {
        const sc = document.getElementById("vt-source-canvas");
        const cc = document.getElementById("vt-chart-canvas");
        if (sc) LL.renderPanelCanvas(sc, sel, { overlayOn: st.vaultOverlayOn, maxW: 620, maxH: 410 });
        if (cc) LL.renderDigitizedChart(cc, sel);
      };
      drawBoth();

      document.getElementById("vt-toggle-ov").onclick = () => { st.vaultOverlayOn = !st.vaultOverlayOn; LL.renderVaultView(root); };
      const cBtn = document.getElementById("vt-toggle-code");
      if (cBtn) cBtn.onclick = () => { st.vaultShowCode = !st.vaultShowCode; LL.renderVaultView(root); };
      document.getElementById("vt-dl-csv").onclick = () => LL.downloadText(`${sel.id.replace(/\//g, "_")}.csv`, panelToCsv(sel), "text/csv");
      document.getElementById("vt-dl-json").onclick = () => LL.downloadText(`${sel.id.replace(/\//g, "_")}.json`, JSON.stringify(sel, null, 2), "application/json");
    }

    document.getElementById("vt-paper").onchange = (e) => { st.vaultPaper = e.target.value; LL.renderVaultView(root); };
    document.getElementById("vt-q").oninput = (e) => { st.vaultQuery = e.target.value; LL.renderVaultView(root); };
    document.getElementById("vt-list").onclick = (e) => {
      const btn = e.target.closest("[data-vault-id]");
      if (!btn) return;
      st.selectedVaultId = btn.getAttribute("data-vault-id");
      LL.renderVaultView(root);
    };
  };
})(window.LL);
