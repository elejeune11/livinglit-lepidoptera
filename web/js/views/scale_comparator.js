/* True-Scale (µm/px) Synchronized Side-by-Side Micrograph Comparator */
window.LL = window.LL || {};

(function (LL) {
  function drawTrueScaleTile(canvas, panel, pxPerUm, overlayOn) {
    const thumb = LL.getThumb(panel.id);
    const d = panel.data || {};
    const ctx = canvas.getContext("2d");
    const cw = Math.max(280, Math.round(canvas.getBoundingClientRect().width || 360));
    const ch = 300;
    canvas.width = cw;
    canvas.height = ch;
    ctx.fillStyle = "#0b0f14";
    ctx.fillRect(0, 0, cw, ch);
    if (!thumb || !d.um_per_px) return;

    const img = new Image();
    img.onload = function () {
      const origW = (panel.pixel_size && panel.pixel_size[0]) || img.naturalWidth;
      const origH = (panel.pixel_size && panel.pixel_size[1]) || img.naturalHeight;
      // Physical width of full crop in µm = origW * um_per_px
      const drawW = origW * d.um_per_px * pxPerUm;
      const drawH = origH * d.um_per_px * pxPerUm;
      const roi = d.overlay_meta && d.overlay_meta.roi_px;
      const fx = roi ? ((roi[0] + roi[2]) * 0.5) / origW : 0.5;
      const fy = roi ? ((roi[1] + roi[3]) * 0.5) / origH : 0.5;
      let ox = cw * 0.5 - fx * drawW;
      let oy = ch * 0.5 - fy * drawH;
      if (drawW > cw) ox = Math.min(0, Math.max(cw - drawW, ox));
      if (drawH > ch) oy = Math.min(0, Math.max(ch - drawH, oy));
      ctx.drawImage(img, ox, oy, drawW, drawH);

      // Draw synchronized physical 2 µm ruler bar at bottom-left of EVERY comparator tile!
      const rulerUm = pxPerUm >= 110 ? 1 : (pxPerUm >= 55 ? 2 : 5);
      const rulerPx = rulerUm * pxPerUm;
      ctx.fillStyle = "rgba(10,14,20,0.78)";
      ctx.fillRect(10, ch - 34, rulerPx + 58, 24);
      ctx.fillStyle = "#facc15";
      ctx.fillRect(16, ch - 20, rulerPx, 4);
      ctx.font = "600 11px ui-monospace, monospace";
      ctx.fillText(`${rulerUm} µm`, 22 + rulerPx, ch - 15);

      if (overlayOn && d.periodic_fft_um) {
        ctx.fillStyle = "rgba(10,14,20,0.78)";
        ctx.fillRect(10, 10, 165, 22);
        ctx.fillStyle = "#4ade80";
        ctx.fillText(`FFT pitch: ${d.periodic_fft_um.toFixed(3)} µm`, 16, 25);
      }
    };
    img.src = thumb;
  }

  LL.renderScaleView = function (root) {
    const st = LL.state;
    const calPanels = (st.data.panels || []).filter((p) => (p.data || {}).um_per_px != null && (p.data || {}).um_per_px < 0.5);
    if (!st.scaleSelected.length) {
      const defaults = ["2024_Lloyd/F1/E", "2026_Finet/F5/C", "2024_Lloyd/F6/G", "2026_Finet/F2/A"];
      st.scaleSelected = defaults.filter((id) => calPanels.some((p) => p.id === id));
      if (st.scaleSelected.length < 2) st.scaleSelected = calPanels.slice(0, 4).map((p) => p.id);
    }

    const chosen = st.scaleSelected.map((id) => calPanels.find((p) => p.id === id)).filter(Boolean);

    root.innerHTML = `
      <div class="toolbar">
        <span style="font-weight:700">Synchronized Scale:</span>
        <input type="range" id="sc-zoom" min="30" max="220" step="5" value="${st.scalePxPerUm}" />
        <span class="mono" id="sc-zoom-lbl">${st.scalePxPerUm} px / µm</span>
        <button type="button" class="btn btn-sm ${st.scaleOverlayOn ? "active" : ""}" id="sc-ov">${st.scaleOverlayOn ? "✓ " : ""}Show FFT pitch</button>
        <select id="sc-add" aria-label="Add calibrated micrograph">
          <option value="">+ Add calibrated micrograph…</option>
          ${calPanels.map((p) => `<option value="${LL.esc(p.id)}">${LL.esc(p.id)} (${((p.data.um_per_px || 0) * 1000).toFixed(1)} nm/px${p.data.periodic_fft_um ? `, FFT ${p.data.periodic_fft_um.toFixed(2)} µm` : ""})</option>`).join("")}
        </select>
      </div>
      <div class="muted" style="margin-bottom:10px">All micrographs below are rescaled to the <strong>exact same physical magnification (${st.scalePxPerUm} px per µm)</strong> using their verified scale bars, letting you visually compare ridge spacing across species and papers at true physical size.</div>
      <div class="scale-grid">
        ${chosen.map((p) => `
          <div class="card">
            <div class="card-title">
              <span class="mono" style="font-size:12px">${LL.esc(p.id)}</span>
              <button type="button" class="btn btn-sm" data-sc-rm="${LL.esc(p.id)}">Remove</button>
            </div>
            <div class="muted" style="margin-bottom:8px">${LL.esc((p.context && p.context.taxon) || p.paper)} · ${LL.esc((p.context && p.context.imaging_modality) || "")} · ${(p.data.um_per_px * 1000).toFixed(1)} nm/px</div>
            <canvas class="scale-card-canvas" data-sc-canvas="${LL.esc(p.id)}"></canvas>
          </div>`).join("")}
      </div>
    `;

    const drawAll = () => {
      chosen.forEach((p) => {
        const c = root.querySelector(`canvas[data-sc-canvas="${CSS.escape(p.id)}"]`);
        if (c) drawTrueScaleTile(c, p, st.scalePxPerUm, st.scaleOverlayOn);
      });
    };
    drawAll();

    document.getElementById("sc-zoom").oninput = (e) => {
      st.scalePxPerUm = Number(e.target.value);
      document.getElementById("sc-zoom-lbl").textContent = `${st.scalePxPerUm} px / µm`;
      drawAll();
    };
    document.getElementById("sc-ov").onclick = () => { st.scaleOverlayOn = !st.scaleOverlayOn; LL.renderScaleView(root); };
    document.getElementById("sc-add").onchange = (e) => {
      const id = e.target.value;
      if (id && !st.scaleSelected.includes(id)) {
        st.scaleSelected.push(id);
        LL.renderScaleView(root);
      }
    };
    root.querySelectorAll("[data-sc-rm]").forEach((b) => {
      b.onclick = () => {
        st.scaleSelected = st.scaleSelected.filter((x) => x !== b.getAttribute("data-sc-rm"));
        LL.renderScaleView(root);
      };
    });
  };
})(window.LL);
