/* Unified Plot + Microscopy FFT Grating + Scale-Bar Overlay Renderer + Browser ROI Periodicity */
window.LL = window.LL || {};

(function (LL) {
  const PALETTE = ["#16a34a", "#db2777", "#0284c7", "#ea580c", "#7c3aed", "#0d9488", "#ca8a04"];

  function drawMicroscopyOverlay(ctx, p, sx, sy, cw, ch) {
    const d = p.data || {};
    const om = d.overlay_meta || {};
    const lw = Math.max(1.4, Math.min(cw, ch) / 260);

    // 1. FFT ROI + Phase-aligned Grating Lines + Optional Crossrib Grating + Transects
    if (om.roi_px && om.roi_px.length === 4) {
      const [rx0, ry0, rx1, ry1] = om.roi_px;
      const x0 = rx0 * sx, y0 = ry0 * sy, rw = (rx1 - rx0) * sx, rh = (ry1 - ry0) * sy;

      const drawGrating = function (g, color, lineW, dash) {
        if (!g || !g.period_px || g.period_px <= 1.0) return;
        const rad = (g.wavevector_deg * Math.PI) / 180.0;
        const ux = Math.cos(rad), uy = Math.sin(rad); // wavevector normal
        const tx = -uy, ty = ux;                       // ridge direction tangent
        const cx = (rx0 + rx1) * 0.5, cy = (ry0 + ry1) * 0.5;
        const diag = Math.hypot(rx1 - rx0, ry1 - ry0);
        const period = g.period_px;
        const phase = g.phase_shift_px || 0;
        const nMax = Math.ceil(diag / period) + 2;

        ctx.save();
        ctx.beginPath();
        ctx.rect(x0, y0, rw, rh);
        ctx.clip();
        ctx.strokeStyle = color;
        ctx.lineWidth = lineW;
        if (dash) ctx.setLineDash(dash);
        for (let k = -nMax; k <= nMax; k++) {
          const s = k * period + phase;
          const px = cx + s * ux, py = cy + s * uy;
          ctx.beginPath();
          ctx.moveTo((px - diag * tx) * sx, (py - diag * ty) * sy);
          ctx.lineTo((px + diag * tx) * sx, (py + diag * ty) * sy);
          ctx.stroke();
        }
        ctx.restore();
      };

      if (om.crossrib_grating) {
        drawGrating(om.crossrib_grating, "rgba(244, 114, 182, 0.72)", Math.max(1.1, lw * 0.8), [4, 3]);
      }
      if (om.grating) {
        drawGrating(om.grating, "rgba(52, 238, 126, 0.92)", Math.max(1.5, lw * 1.05), null);
      }

      // Draw 3 representative transect lines + peak dots (keep visually crisp)
      if (Array.isArray(om.transects) && om.transects.length) {
        const idxs = [1, Math.floor(om.transects.length / 2), om.transects.length - 2].filter(
          (v, i, a) => v >= 0 && v < om.transects.length && a.indexOf(v) === i
        );
        ctx.save();
        ctx.strokeStyle = "rgba(250, 204, 21, 0.85)";
        ctx.fillStyle = "#facc15";
        ctx.lineWidth = Math.max(1.1, lw * 0.85);
        idxs.forEach((ti) => {
          const tr = om.transects[ti];
          if (!tr || !tr.p0 || !tr.p1) return;
          ctx.beginPath();
          ctx.moveTo(tr.p0[0] * sx, tr.p0[1] * sy);
          ctx.lineTo(tr.p1[0] * sx, tr.p1[1] * sy);
          ctx.stroke();
          (tr.peaks_px || []).forEach((pk) => {
            ctx.beginPath();
            ctx.arc(pk[0] * sx, pk[1] * sy, Math.max(2.2, lw * 1.4), 0, Math.PI * 2);
            ctx.fill();
          });
        });
        ctx.restore();
      }

      // Cyan FFT ROI border
      ctx.save();
      ctx.strokeStyle = "#22d3ee";
      ctx.lineWidth = Math.max(1.8, lw * 1.2);
      ctx.strokeRect(x0, y0, rw, rh);
      ctx.restore();
    }

    // 2. Yellow Scale-Bar Bracket + Label
    if (om.scale_bar_px) {
      const sb = om.scale_bar_px;
      const bx0 = sb.x0 * sx, by0 = sb.y0 * sy, bw = (sb.x1 - sb.x0) * sx, bh = (sb.y1 - sb.y0) * sy;
      ctx.save();
      ctx.strokeStyle = "#facc15";
      ctx.lineWidth = Math.max(2, lw * 1.3);
      ctx.strokeRect(bx0 - 2, by0 - 2, bw + 4, bh + 4);
      const lbl = `${sb.um} µm (${(sb.um_per_px * 1000).toFixed(1)} nm/px)`;
      ctx.font = "600 11px ui-monospace, Menlo, monospace";
      const tw = ctx.measureText(lbl).width + 8;
      const lx = Math.max(4, Math.min(cw - tw - 4, bx0 - 12));
      const ly = Math.max(18, by0 - 7);
      ctx.fillStyle = "rgba(12, 16, 22, 0.82)";
      ctx.fillRect(lx - 4, ly - 12, tw, 15);
      ctx.fillStyle = "#fde047";
      ctx.fillText(lbl, lx, ly - 1);
      ctx.restore();
    }
  }

  function drawPlotOverlay(ctx, p, sx, sy, cw, ch) {
    const d = p.data || {};
    const om = d.overlay_meta || {};
    if (!om.plot_box || om.plot_box.length !== 4) return;
    const [px0, py0, px1, py1] = om.plot_box;
    const pw = Math.max(px1 - px0, 1);
    const ph = Math.max(py1 - py0, 1);
    const xr = om.x_range;
    const yr = om.y_range;

    const x2c = (xv) => (px0 + ((xv - xr[0]) / Math.max(xr[1] - xr[0], 1e-9)) * pw) * sx;
    const y2c = (yv) => (py0 + ((yr[1] - yv) / Math.max(yr[1] - yr[0], 1e-9)) * ph) * sy;

    // Cyan calibrated plot box
    ctx.save();
    ctx.strokeStyle = "#06b6d4";
    ctx.lineWidth = 1.6;
    ctx.strokeRect(px0 * sx, py0 * sy, pw * sx, ph * sy);
    ctx.restore();

    // Curves + ±SD / 95% CI Ribbons
    if (d.curves && xr && yr) {
      Object.entries(d.curves).forEach(([cname, c], idx) => {
        const col = PALETTE[idx % PALETTE.length];
        const xs = c.x || [], ys = c.y || [], lo = c.lo || [], hi = c.hi || [];
        if (xs.length < 2) return;
        ctx.save();
        if (lo.length === xs.length && hi.length === xs.length) {
          ctx.beginPath();
          for (let i = 0; i < xs.length; i++) {
            const x = x2c(xs[i]), y = y2c(hi[i]);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          for (let i = xs.length - 1; i >= 0; i--) {
            ctx.lineTo(x2c(xs[i]), y2c(lo[i]));
          }
          ctx.closePath();
          ctx.fillStyle = col + "29";
          ctx.fill();
          ctx.strokeStyle = col;
          ctx.lineWidth = 1.1;
          ctx.setLineDash([4, 3]);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        // Core line (dark halo + vibrant stroke)
        ctx.beginPath();
        for (let i = 0; i < xs.length; i++) {
          const x = x2c(xs[i]), y = y2c(ys[i]);
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = "rgba(0,0,0,0.75)";
        ctx.lineWidth = 3.2;
        ctx.stroke();
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.8;
        ctx.stroke();
        ctx.restore();
      });
    }

    // Scatter + x/y error bars + beeswarm y_interval
    if (d.digitized_scatter && yr) {
      const isBee = om.mode === "beeswarm_1d";
      const gmap = {};
      if (Array.isArray(om.groups)) om.groups.forEach((g) => { gmap[g.name] = g; });
      Object.entries(d.digitized_scatter).forEach(([gn, g], idx) => {
        const col = PALETTE[idx % PALETTE.length];
        const xs = g.x || [], ys = g.y || [];
        const xlo = g.x_lo || [], xhi = g.x_hi || [], ylo = g.y_lo || [], yhi = g.y_hi || [];
        const mg = gmap[gn];
        ctx.save();
        ctx.strokeStyle = col;
        ctx.fillStyle = col;
        ctx.lineWidth = 1.4;
        for (let i = 0; i < xs.length; i++) {
          let cx;
          if (isBee && mg && mg.x_frac) {
            const xf = (xs[i] - mg.x_val) / 0.36 + 0.5;
            cx = (px0 + (mg.x_frac[0] + xf * (mg.x_frac[1] - mg.x_frac[0])) * pw) * sx;
          } else if (xr) {
            cx = x2c(xs[i]);
          } else continue;
          const cy = y2c(ys[i]);
          if (i < xlo.length && xlo[i] != null && xhi[i] != null && xr) {
            ctx.beginPath(); ctx.moveTo(x2c(xlo[i]), cy); ctx.lineTo(x2c(xhi[i]), cy); ctx.stroke();
          }
          if (i < ylo.length && ylo[i] != null && yhi[i] != null) {
            ctx.beginPath(); ctx.moveTo(cx, y2c(ylo[i])); ctx.lineTo(cx, y2c(yhi[i])); ctx.stroke();
          }
          ctx.beginPath(); ctx.arc(cx, cy, 4.6, 0, Math.PI * 2); ctx.strokeStyle = "#000"; ctx.lineWidth = 2.6; ctx.stroke();
          ctx.beginPath(); ctx.arc(cx, cy, 4.2, 0, Math.PI * 2); ctx.strokeStyle = col; ctx.lineWidth = 1.6; ctx.stroke();
        }
        if (g.y_interval && g.y_interval.length === 2 && xs.length && xr) {
          const sortedX = xs.slice().sort((a, b) => a - b);
          const mx = x2c(sortedX[Math.floor(sortedX.length / 2)]);
          ctx.strokeStyle = "#facc15";
          ctx.lineWidth = 2.6;
          ctx.beginPath();
          ctx.moveTo(mx, y2c(g.y_interval[0]));
          ctx.lineTo(mx, y2c(g.y_interval[1]));
          ctx.stroke();
        }
        ctx.restore();
      });
    }

    // Boxplots (supports dict{name: {x_center, half_width}} and list[{name, x_frac}])
    if (d.digitized_boxplots && yr && om.groups) {
      let grpItems = [];
      if (Array.isArray(om.groups)) {
        grpItems = om.groups.map((gm) => [
          gm.name,
          (px0 + 0.5 * (gm.x_frac[0] + gm.x_frac[1]) * pw) * sx,
          Math.max(12, (gm.x_frac[1] - gm.x_frac[0]) * pw * 0.42 * sx),
        ]);
      } else {
        grpItems = Object.entries(om.groups).map(([gn, gm]) => [
          gn,
          (px0 + gm.x_center) * sx,
          Math.max(12, (gm.half_width || 14) * 2 * sx),
        ]);
      }
      grpItems.forEach(([gn, cx, bw], idx) => {
        const b = d.digitized_boxplots[gn];
        if (!b) return;
        const col = PALETTE[idx % PALETTE.length];
        ctx.save();
        ctx.strokeStyle = col;
        ctx.lineWidth = 2.0;
        if (b.whisker_lo != null && b.whisker_hi != null) {
          ctx.beginPath();
          ctx.moveTo(cx, y2c(b.whisker_lo));
          ctx.lineTo(cx, y2c(b.whisker_hi));
          ctx.stroke();
        }
        if (b.q1 != null && b.q3 != null) {
          const top = y2c(b.q3), bot = y2c(b.q1);
          ctx.strokeRect(cx - bw / 2, top, bw, Math.max(2, bot - top));
        }
        if (b.median != null) {
          ctx.strokeStyle = "#ef4444";
          ctx.lineWidth = 2.6;
          ctx.beginPath();
          ctx.moveTo(cx - bw / 2 - 3, y2c(b.median));
          ctx.lineTo(cx + bw / 2 + 3, y2c(b.median));
          ctx.stroke();
        }
        ctx.restore();
      });
    }
  }

  function drawDotplotOverlay(ctx, d, sx, sy) {
    if (!d.dotplot_matrix || !d.dotplot_matrix.cells) return;
    ctx.save();
    d.dotplot_matrix.cells.forEach((c) => {
      if (c.px == null || c.py == null) return;
      const cx = c.px * sx, cy = c.py * sy;
      const r = Math.max(2.2, (c.r_px || 4) * sx);
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.strokeStyle = c.pct > 0 ? "#06b6d4" : "rgba(148,163,184,0.45)";
      ctx.lineWidth = c.pct > 0 ? 1.3 : 0.8;
      ctx.stroke();
    });
    ctx.restore();
  }

  LL.renderPanelCanvas = function (canvas, panel, opts) {
    const options = opts || {};
    const thumb = LL.getThumb(panel.id);
    const ctx = canvas.getContext("2d");
    if (!thumb) {
      canvas.width = 480; canvas.height = 280;
      ctx.fillStyle = "#161b22"; ctx.fillRect(0, 0, 480, 280);
      ctx.fillStyle = "#94a3b8"; ctx.font = "13px sans-serif";
      ctx.fillText("Source thumbnail unavailable (metadata-only mode)", 60, 145);
      return;
    }
    const img = new Image();
    img.onload = function () {
      const maxW = options.maxW || 680;
      const maxH = options.maxH || 490;
      const scale = Math.min(maxW / img.naturalWidth, maxH / img.naturalHeight, 1.5);
      const cw = Math.max(120, Math.round(img.naturalWidth * scale));
      const ch = Math.max(100, Math.round(img.naturalHeight * scale));
      canvas.width = cw;
      canvas.height = ch;
      ctx.clearRect(0, 0, cw, ch);
      ctx.drawImage(img, 0, 0, cw, ch);

      const origW = (panel.pixel_size && panel.pixel_size[0]) || img.naturalWidth;
      const origH = (panel.pixel_size && panel.pixel_size[1]) || img.naturalHeight;
      const sx = cw / origW;
      const sy = ch / origH;

      if (options.overlayOn) {
        const om = (panel.data && panel.data.overlay_meta) || {};
        if (om.kind === "microscopy_fft" || om.kind === "microscopy_scale") {
          drawMicroscopyOverlay(ctx, panel, sx, sy, cw, ch);
        } else {
          drawPlotOverlay(ctx, panel, sx, sy, cw, ch);
          if (panel.data && panel.data.dotplot_matrix) {
            drawDotplotOverlay(ctx, panel.data, sx, sy);
          }
        }
      }

      // Draw optional user drag ROI box for live browser periodicity measurement
      if (options.userRoi) {
        const [rx0, ry0, rx1, ry1] = options.userRoi;
        ctx.save();
        ctx.strokeStyle = "#f97316";
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 3]);
        ctx.strokeRect(rx0, ry0, rx1 - rx0, ry1 - ry0);
        ctx.restore();
      }
      if (typeof options.onReady === "function") options.onReady({ img, cw, ch, sx, sy, origW, origH });
    };
    img.src = thumb;
  };

  /* Live browser 1D autocorrelation / FFT spacing estimator inside a dragged ROI */
  LL.measureBrowserRoiPeriod = function (canvas, roi, umPerPx, origW, origH) {
    const [x0, y0, x1, y1] = [
      Math.max(0, Math.round(Math.min(roi[0], roi[2]))),
      Math.max(0, Math.round(Math.min(roi[1], roi[3]))),
      Math.min(canvas.width, Math.round(Math.max(roi[0], roi[2]))),
      Math.min(canvas.height, Math.round(Math.max(roi[1], roi[3]))),
    ];
    const rw = x1 - x0, rh = y1 - y0;
    if (rw < 18 || rh < 18 || !umPerPx) return null;
    const ctx = canvas.getContext("2d");
    const idata = ctx.getImageData(x0, y0, rw, rh).data;
    // Try projections across 18 angles (0..170 deg in 10 deg steps) and pick strongest periodic autocorr peak!
    const effUmPerPx = umPerPx * (origW / canvas.width);
    let best = null;
    for (let deg = 0; deg < 180; deg += 10) {
      const rad = (deg * Math.PI) / 180;
      const ux = Math.cos(rad), uy = Math.sin(rad);
      const len = Math.floor(Math.min(rw, rh));
      if (len < 16) continue;
      const prof = new Float64Array(len);
      const cnt = new Float64Array(len);
      const cx = rw * 0.5, cy = rh * 0.5;
      for (let py = 0; py < rh; py += 2) {
        for (let px = 0; px < rw; px += 2) {
          const s = (px - cx) * ux + (py - cy) * uy + len * 0.5;
          const b = Math.floor(s);
          if (b >= 0 && b < len) {
            const o = (py * rw + px) * 4;
            prof[b] += 0.299 * idata[o] + 0.587 * idata[o + 1] + 0.114 * idata[o + 2];
            cnt[b] += 1;
          }
        }
      }
      let mean = 0, nValid = 0;
      for (let i = 0; i < len; i++) {
        if (cnt[i] > 0) { prof[i] /= cnt[i]; mean += prof[i]; nValid++; }
      }
      if (nValid < 14) continue;
      mean /= nValid;
      let varSum = 0;
      for (let i = 0; i < len; i++) { prof[i] = cnt[i] > 0 ? prof[i] - mean : 0; varSum += prof[i] * prof[i]; }
      if (varSum < 1e-6) continue;
      const minLag = Math.max(4, Math.floor(0.35 / effUmPerPx));
      const maxLag = Math.min(Math.floor(len * 0.48), Math.ceil(4.0 / effUmPerPx));
      for (let lag = minLag; lag <= maxLag; lag++) {
        let acc = 0, n2 = 0;
        for (let i = 0; i + lag < len; i++) { acc += prof[i] * prof[i + lag]; n2++; }
        const score = (acc / Math.max(n2, 1)) / (varSum / nValid);
        if (!best || score > best.score) {
          best = { score, lagPx: lag, periodUm: lag * effUmPerPx, angleDeg: deg };
        }
      }
    }
    return best;
  };
})(window.LL);
