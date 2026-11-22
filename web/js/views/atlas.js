/* Panel Atlas + Sticky Inspector + Live Plot/Microscopy FFT Overlay + Browser Drag-ROI + Inline .py Code */
window.LL = window.LL || {};

(function (LL) {
  function filteredPanels() {
    const st = LL.state;
    const panels = (st.data && st.data.panels) || [];
    const q = (st.atlasQuery || "").trim().toLowerCase();
    return panels.filter((p) => {
      if (st.atlasPaper !== "ALL" && p.paper !== st.atlasPaper) return false;
      if (st.atlasArch !== "ALL" && p.archetype !== st.atlasArch) return false;
      if (st.atlasOnlyFft && !LL.panelHasFft(p)) return false;
      if (st.atlasOnlyExt && !p.extractor_script) return false;
      if (q) {
        const hay = `${p.id} ${p.title} ${p.archetype} ${JSON.stringify(p.context || {})}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }

  function qaBadgeHtml(p) {
    const q = LL.panelQaInfo(p);
    if (!q) return "";
    const c = q.confidence || "verified";
    const cls = c === "flagged" ? "bad" : (c === "low_snr_verify" ? "warn" : "ok");
    const lbl = c === "flagged" ? "QA Flagged" : (c === "low_snr_verify" ? "QA Low-SNR" : "QA Verified");
    return `<span class="pill ${cls}" title="From committed qa/report.json">${lbl}</span>`;
  }

  function renderInspector(container, panel) {
    if (!panel) {
      container.innerHTML = `<div class="card muted">Select any atomic panel on the left to inspect its calibrated overlay, metrology, and code provenance.</div>`;
      return;
    }
    const d = panel.data || {};
    const st = LL.state;
    const om = d.overlay_meta || null;
    const hasOverlay = !!om;
    const isMicro = om && (om.kind === "microscopy_fft" || om.kind === "microscopy_scale");
    const extRel = panel.extractor_script ? `${panel.paper}/${panel.extractor_script}` : null;
    const extSrc = extRel && st.data.extractor_scripts ? st.data.extractor_scripts[extRel] : null;
    const qa = LL.panelQaInfo(panel);
    const hg = d.harmonic_guard || null;

    const badges = [
      `<span class="pill accent">${LL.esc(panel.archetype)}</span>`,
      qaBadgeHtml(panel),
      d.periodic_fft_um != null ? `<span class="pill ok">FFT ${LL.fmtNum(d.periodic_fft_um, 3)} µm</span>` : "",
      d.crossrib_fft_um != null ? `<span class="pill info">Crossrib ${LL.fmtNum(d.crossrib_fft_um, 3)} µm</span>` : "",
      d.um_per_px != null ? `<span class="pill">${(d.um_per_px * 1000).toFixed(1)} nm/px</span>` : "",
      panel.n_digitized_points > 0 ? `<span class="pill info">${panel.n_digitized_points} digitized pts</span>` : "",
    ].filter(Boolean).join(" ");

    const ctxRows = Object.entries(panel.context || {})
      .filter(([, v]) => v && v !== "not stated")
      .map(([k, v]) => `<div class="kv-item"><div class="kv-k">${LL.esc(k.replace(/_/g, " "))}</div><div class="kv-v">${LL.esc(v)}</div></div>`)
      .join("");

    let metricsHtml = "";
    if (d.periodic_fft_um != null) {
      metricsHtml = `
        <div class="kv-grid">
          <div class="kv-item"><div class="kv-k">2D-FFT Period</div><div class="kv-v mono">${LL.fmtNum(d.periodic_fft_um, 4)} µm</div></div>
          <div class="kv-item"><div class="kv-k">10-Transect Mean</div><div class="kv-v mono">${d.periodic_transect_um != null ? `${LL.fmtNum(d.periodic_transect_um, 4)} ± ${LL.fmtNum(d.periodic_transect_sd_um, 4)} µm` : "—"}</div></div>
          <div class="kv-item"><div class="kv-k">FFT SNR / Angle</div><div class="kv-v mono">${LL.fmtNum(d.periodic_snr, 1)} · ${LL.fmtNum(d.wavevector_deg, 1)}°</div></div>
          <div class="kv-item"><div class="kv-k">Harmonic Guard</div><div class="kv-v mono">${hg ? `${LL.esc(hg.status)} (Δ=${hg.fft_transect_delta_pct ?? "—"}%, 2f=${hg.harmonic_ratio_2f ?? "—"})` : "pass"}</div></div>
        </div>`;
    } else if (d.um_per_px != null) {
      metricsHtml = `
        <div class="kv-grid">
          <div class="kv-item"><div class="kv-k">Scale Bar</div><div class="kv-v mono">${panel.scale_bar_um} µm (${d.scale_bar_px} px)</div></div>
          <div class="kv-item"><div class="kv-k">Pixel Size</div><div class="kv-v mono">${(d.um_per_px * 1000).toFixed(2)} nm/px</div></div>
          <div class="kv-item"><div class="kv-k">Field of View</div><div class="kv-v mono">${d.fov_um ? `${d.fov_um[0]} × ${d.fov_um[1]} µm` : "—"}</div></div>
        </div>`;
    }

    const linkedItems = (panel.linked_items || []).map((iid) =>
      `<button type="button" class="pill accent pill-btn" data-open-item="${LL.esc(panel.paper)}/${LL.esc(iid)}">Evidence: ${LL.esc(iid)}</button>`
    ).join(" ");

    container.innerHTML = `
      <div class="card">
        <div class="card-title">
          <span class="mono">${LL.esc(panel.id)}</span>
          <div style="display:flex;gap:5px;flex-wrap:wrap">${badges}</div>
        </div>
        <div style="font-weight:600;margin-bottom:8px">${LL.esc(panel.title)}</div>

        <div class="stage-controls" style="margin-bottom:8px">
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            ${hasOverlay ? `<button type="button" class="btn btn-sm ${st.atlasOverlayOn ? "active" : ""}" id="atlas-toggle-overlay">${st.atlasOverlayOn ? "✓ " : ""}Overlay check (${isMicro ? "FFT + Scale Bar" : "Plot geometry"})</button>` : ""}
            ${d.um_per_px != null ? `<button type="button" class="btn btn-sm ${st.atlasRoiMode ? "active" : ""}" id="atlas-toggle-roi">${st.atlasRoiMode ? "✓ " : ""}Drag-ROI Periodicity</button>` : ""}
            ${extSrc ? `<button type="button" class="btn btn-sm ${st.atlasShowCode ? "active" : ""}" id="atlas-toggle-code">${LL.esc(panel.extractor_script.split("/").pop())} (${extSrc.split("\n").length} ln)</button>` : ""}
          </div>
          <div class="muted mono" id="atlas-roi-readout">${st.atlasRoiMode ? "Drag box on image to measure…" : `${panel.pixel_size[0]}×${panel.pixel_size[1]} px`}</div>
        </div>

        <div class="stage-wrap">
          <canvas id="atlas-stage-canvas"></canvas>
        </div>

        ${isMicro && st.atlasOverlayOn ? `<div class="muted" style="margin-top:6px;font-size:11.5px">Legend: <span style="color:#eab308;font-weight:600">■ Scale bar</span> · <span style="color:#06b6d4;font-weight:600">□ FFT ROI</span> · <span style="color:#16a34a;font-weight:600">▬ Phase-aligned 1× ridges</span>${om.crossrib_grating ? ` · <span style="color:#db2777;font-weight:600">┄ Crossribs</span>` : ""} · <span style="color:#ca8a04;font-weight:600">● Transect peaks</span></div>` : ""}

        ${st.atlasShowCode && extSrc ? `
          <div style="margin-top:10px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span class="mono" style="font-size:11.5px;font-weight:600">records/${LL.esc(extRel)}</span>
              <button type="button" class="btn btn-sm" id="atlas-dl-py">Download .py</button>
            </div>
            <pre class="code-viewer">${LL.esc(extSrc)}</pre>
          </div>` : ""}
      </div>

      ${metricsHtml ? `<div class="card"><div class="card-title">Calibrated Metrology &amp; QA</div>${metricsHtml}</div>` : ""}

      <div class="card">
        <div class="card-title">Resolved Context &amp; Provenance</div>
        <div class="kv-grid">${ctxRows || '<div class="muted">No context fields recorded.</div>'}</div>
        ${linkedItems ? `<div style="margin-top:10px;display:flex;gap:6px;flex-wrap:wrap">${linkedItems}</div>` : ""}
        ${panel.caption_quote ? `<blockquote class="quote-block" style="margin-top:10px">“${LL.esc(panel.caption_quote)}”</blockquote>` : ""}
        ${qa && qa.issues && qa.issues.length ? `<div class="pill bad" style="margin-top:8px">QA note: ${LL.esc(qa.issues.join("; "))}</div>` : ""}
      </div>
    `;

    // Draw stage canvas + wire live drag-to-measure ROI
    const canvas = document.getElementById("atlas-stage-canvas");
    let meta = null;
    let dragStart = null;
    let userRoi = null;
    const redraw = () => {
      LL.renderPanelCanvas(canvas, panel, {
        overlayOn: st.atlasOverlayOn,
        userRoi,
        maxW: 720,
        maxH: 480,
        onReady: (m) => { meta = m; },
      });
    };
    redraw();

    if (st.atlasRoiMode && d.um_per_px != null) {
      canvas.style.cursor = "crosshair";
      const pt = (ev) => {
        const r = canvas.getBoundingClientRect();
        return [(ev.clientX - r.left) * (canvas.width / r.width), (ev.clientY - r.top) * (canvas.height / r.height)];
      };
      canvas.onmousedown = (ev) => { dragStart = pt(ev); userRoi = null; };
      canvas.onmousemove = (ev) => {
        if (!dragStart) return;
        const p2 = pt(ev);
        userRoi = [dragStart[0], dragStart[1], p2[0], p2[1]];
        redraw();
      };
      canvas.onmouseup = (ev) => {
        if (!dragStart || !meta) return;
        const p2 = pt(ev);
        userRoi = [dragStart[0], dragStart[1], p2[0], p2[1]];
        dragStart = null;
        // Render clean image without overlay first to sample raw image pixels cleanly
        LL.renderPanelCanvas(canvas, panel, {
          overlayOn: false,
          maxW: 720,
          maxH: 480,
          onReady: (m) => {
            const res = LL.measureBrowserRoiPeriod(canvas, userRoi, d.um_per_px, m.origW, m.origH);
            const ro = document.getElementById("atlas-roi-readout");
            if (ro) {
              ro.textContent = res
                ? `Live ROI: ${res.periodUm.toFixed(3)} µm (θ=${res.angleDeg}°, r=${res.score.toFixed(2)})`
                : "Drag a larger periodic region…";
            }
            redraw();
          },
        });
      };
    }

    const bOv = document.getElementById("atlas-toggle-overlay");
    if (bOv) bOv.onclick = () => { st.atlasOverlayOn = !st.atlasOverlayOn; renderInspector(container, panel); };
    const bRoi = document.getElementById("atlas-toggle-roi");
    if (bRoi) bRoi.onclick = () => { st.atlasRoiMode = !st.atlasRoiMode; renderInspector(container, panel); };
    const bCode = document.getElementById("atlas-toggle-code");
    if (bCode) bCode.onclick = () => { st.atlasShowCode = !st.atlasShowCode; renderInspector(container, panel); };
    const bDl = document.getElementById("atlas-dl-py");
    if (bDl && extSrc) bDl.onclick = () => LL.downloadText(panel.extractor_script.split("/").pop(), extSrc, "text/x-python");
  }

  LL.renderAtlasView = function (root) {
    const st = LL.state;
    const papers = (st.data.papers || []).map((p) => p.paper);
    const list = filteredPanels();
    if (!st.selectedPanelId || !list.some((p) => p.id === st.selectedPanelId)) {
      // Default to an iconic microscopy FFT panel so the live grating overlay shines immediately!
      const preferred = list.find((p) => p.id === "2024_Lloyd/F1/E") || list.find(LL.panelHasFft) || list[0];
      st.selectedPanelId = preferred ? preferred.id : null;
    }
    const sel = list.find((p) => p.id === st.selectedPanelId) || null;
    const arches = ["planar_microscopy", "cross_section", "quantitative_plot", "spectral_or_profile", "macro_morphology", "phylogeny_or_schematic"];

    root.innerHTML = `
      <div class="toolbar">
        <select id="at-paper" aria-label="Filter by paper">
          <option value="ALL">All papers (${papers.length})</option>
          ${papers.map((pid) => `<option value="${LL.esc(pid)}" ${st.atlasPaper === pid ? "selected" : ""}>${LL.esc(pid)}</option>`).join("")}
        </select>
        <select id="at-arch" aria-label="Filter by archetype">
          <option value="ALL">All panel types</option>
          ${arches.map((a) => `<option value="${a}" ${st.atlasArch === a ? "selected" : ""}>${a.replace(/_/g, " ")}</option>`).join("")}
        </select>
        <label class="chk"><input type="checkbox" id="at-fft" ${st.atlasOnlyFft ? "checked" : ""} /> Calibrated FFT (${(st.data.panels || []).filter(LL.panelHasFft).length})</label>
        <label class="chk"><input type="checkbox" id="at-ext" ${st.atlasOnlyExt ? "checked" : ""} /> Custom .py Extractor (${(st.data.panels || []).filter((p) => p.extractor_script).length})</label>
        <input type="search" id="at-q" placeholder="Search panel, species, modality…" value="${LL.esc(st.atlasQuery)}" />
        <span class="muted mono" style="margin-left:auto">${list.length} atomic panels</span>
      </div>
      <div class="split-atlas">
        <div class="panel-grid" id="atlas-grid">
          ${list.map((p) => {
            const thumb = LL.getThumb(p.id);
            const d = p.data || {};
            return `
              <button type="button" class="panel-tile ${p.id === st.selectedPanelId ? "selected" : ""}" data-panel-id="${LL.esc(p.id)}">
                <div class="panel-thumb-wrap">
                  ${thumb ? `<img src="${thumb}" alt="${LL.esc(p.id)}" loading="lazy" />` : `<span class="muted mono">${LL.esc(p.panel_label)}</span>`}
                </div>
                <div class="panel-tile-meta">
                  <div class="panel-tile-id">${LL.esc(p.paper.split("_")[1])} · ${LL.esc(p.figure_id)}/${LL.esc(p.panel_label)}</div>
                  <div class="panel-tile-title">${LL.esc(p.title)}</div>
                  <div class="panel-tile-badges">
                    ${d.periodic_fft_um != null ? `<span class="pill ok">FFT ${d.periodic_fft_um.toFixed(2)} µm</span>` : ""}
                    ${p.extractor_script ? `<span class="pill accent">.py</span>` : ""}
                    ${d.um_per_px != null && d.periodic_fft_um == null ? `<span class="pill">${p.scale_bar_um} µm</span>` : ""}
                  </div>
                </div>
              </button>`;
          }).join("")}
        </div>
        <div class="inspector-sticky" id="atlas-inspector"></div>
      </div>
    `;

    renderInspector(document.getElementById("atlas-inspector"), sel);

    document.getElementById("at-paper").onchange = (e) => { st.atlasPaper = e.target.value; LL.renderAtlasView(root); };
    document.getElementById("at-arch").onchange = (e) => { st.atlasArch = e.target.value; LL.renderAtlasView(root); };
    document.getElementById("at-fft").onchange = (e) => { st.atlasOnlyFft = e.target.checked; LL.renderAtlasView(root); };
    document.getElementById("at-ext").onchange = (e) => { st.atlasOnlyExt = e.target.checked; LL.renderAtlasView(root); };
    document.getElementById("at-q").oninput = (e) => { st.atlasQuery = e.target.value; LL.renderAtlasView(root); };
    document.getElementById("atlas-grid").onclick = (e) => {
      const btn = e.target.closest("[data-panel-id]");
      if (!btn) return;
      st.selectedPanelId = btn.getAttribute("data-panel-id");
      document.querySelectorAll("#atlas-grid .panel-tile").forEach((el) => el.classList.toggle("selected", el === btn));
      const p = list.find((x) => x.id === st.selectedPanelId);
      renderInspector(document.getElementById("atlas-inspector"), p);
    };
  };
})(window.LL);
