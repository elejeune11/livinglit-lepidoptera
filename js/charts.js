/* HiDPI Canvas Scientific Chart Renderers (curves+ribbons, scatter+errorbars, boxplots, one-axis compare) */
window.LL = window.LL || {};

(function (LL) {
  const SERIES_COLORS = ["#0f766e", "#be185d", "#1d4ed8", "#c2410c", "#6d28d9", "#047857", "#a16207"];

  function setupHiDPI(canvas, heightPx) {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(300, Math.round(rect.width || 560));
    const h = heightPx || Math.round(rect.height || 310);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  function themeColors() {
    const dark = LL.isDark();
    return {
      bg: dark ? "#141b24" : "#ffffff",
      grid: dark ? "rgba(148,163,184,0.14)" : "rgba(15,23,42,0.08)",
      axis: dark ? "#475569" : "#94a3b8",
      ink: dark ? "#e2e8f0" : "#1e293b",
      muted: dark ? "#94a3b8" : "#64748b",
    };
  }

  LL.renderDigitizedChart = function (canvas, panel) {
    const d = panel.data || {};
    const om = d.overlay_meta || {};
    const { ctx, w, h } = setupHiDPI(canvas, 320);
    const tc = themeColors();
    ctx.fillStyle = tc.bg;
    ctx.fillRect(0, 0, w, h);

    const pad = { l: 56, r: 18, t: 24, b: 42 };
    const pw = w - pad.l - pad.r;
    const ph = h - pad.t - pad.b;

    // 0. Expression Dotplot Matrix (genes x cell clusters: radius = % expressing, color = avg expression)
    if (d.dotplot_matrix && d.dotplot_matrix.cells && d.dotplot_matrix.clusters && d.dotplot_matrix.genes) {
      const dm = d.dotplot_matrix;
      const clusters = dm.clusters;
      const genes = dm.genes;
      const [emin, emax] = dm.expr_range || [-1.0, 2.5];
      const dp = { l: 96, r: 16, t: 28, b: 92 };
      const cw = (w - dp.l - dp.r) / Math.max(genes.length, 1);
      const ch = (h - dp.t - dp.b) / Math.max(clusters.length, 1);
      const maxR = Math.min(cw, ch) * 0.44;

      const exprColor = (val) => {
        const t = Math.max(0, Math.min(1, (val - emin) / Math.max(emax - emin, 1e-6)));
        // Warm rose -> amber-olive -> deep teal-navy perceptual ramp matching Loh Fig 10B
        const stops = [
          [246, 189, 185], [218, 174, 96], [85, 130, 82], [29, 78, 118], [18, 38, 86],
        ];
        const seg = t * (stops.length - 1);
        const i0 = Math.min(stops.length - 2, Math.floor(seg));
        const f = seg - i0;
        const c0 = stops[i0], c1 = stops[i0 + 1];
        const r = Math.round(c0[0] + (c1[0] - c0[0]) * f);
        const g = Math.round(c0[1] + (c1[1] - c0[1]) * f);
        const b = Math.round(c0[2] + (c1[2] - c0[2]) * f);
        return `rgb(${r},${g},${b})`;
      };

      // Subtle grid + row labels
      ctx.font = "600 10.5px sans-serif";
      clusters.forEach((cl, ri) => {
        const cy = dp.t + (ri + 0.5) * ch;
        ctx.strokeStyle = tc.grid; ctx.lineWidth = 0.8;
        ctx.beginPath(); ctx.moveTo(dp.l, cy); ctx.lineTo(w - dp.r, cy); ctx.stroke();
        ctx.fillStyle = cl.includes("UVI") ? "#a21caf" : (cl.includes("spatulate") ? "#0369a1" : tc.ink);
        ctx.textAlign = "right";
        ctx.fillText(cl, dp.l - 8, cy + 3.5);
      });

      // Rotated gene column labels
      genes.forEach((gn, ci) => {
        const cx = dp.l + (ci + 0.5) * cw;
        ctx.save();
        ctx.translate(cx, h - dp.b + 8);
        ctx.rotate(-Math.PI / 3);
        ctx.fillStyle = tc.ink;
        ctx.font = "600 10px ui-monospace, monospace";
        ctx.textAlign = "right";
        ctx.fillText(gn, 0, 3);
        ctx.restore();
      });

      // Draw circles
      const clIdx = new Map(clusters.map((c, i) => [c, i]));
      const gnIdx = new Map(genes.map((g, i) => [g, i]));
      dm.cells.forEach((cell) => {
        const ri = clIdx.get(cell.cluster), ci = gnIdx.get(cell.gene);
        if (ri == null || ci == null) return;
        const cx = dp.l + (ci + 0.5) * cw;
        const cy = dp.t + (ri + 0.5) * ch;
        const frac = Math.max(0, Math.min(1, (cell.pct || 0) / 100));
        const r = Math.max(1.2, Math.sqrt(frac) * maxR);
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = frac > 0.01 ? exprColor(cell.expr) : tc.grid;
        ctx.fill();
      });

      // Compact header legend
      ctx.fillStyle = tc.muted; ctx.font = "600 10px sans-serif"; ctx.textAlign = "left";
      ctx.fillText("Dot area = % expressing (0–100%) · Color = avg expression (-1 to +2.5)", dp.l, 15);
      return;
    }

    // 1. Boxplot panel (with optional overlaid individual jitter scatter points!)
    if (d.digitized_boxplots && !d.curves) {
      const entries = Object.entries(d.digitized_boxplots);
      const scMap = d.digitized_scatter || {};
      const vals = [];
      entries.forEach(([gn, b]) => {
        ["whisker_lo", "q1", "median", "q3", "whisker_hi"].forEach((k) => {
          if (b[k] != null) vals.push(b[k]);
        });
        const sc = scMap[gn];
        if (sc && sc.y) sc.y.forEach((v) => { if (v != null) vals.push(v); });
      });
      if (!vals.length) return;
      const ymin = Math.min(...vals), ymax = Math.max(...vals);
      const span = Math.max(ymax - ymin, 1e-6);
      const y0 = ymin - span * 0.12, y1 = ymax + span * 0.12;
      const y2p = (v) => pad.t + ((y1 - v) / (y1 - y0)) * ph;
      const yUnit = (entries[0][1] && entries[0][1].y_unit) || "";

      // Grid + y-ticks
      ctx.strokeStyle = tc.grid; ctx.lineWidth = 1;
      ctx.fillStyle = tc.muted; ctx.font = "11px ui-monospace, monospace";
      for (let i = 0; i <= 4; i++) {
        const v = y0 + (i / 4) * (y1 - y0);
        const py = y2p(v);
        ctx.beginPath(); ctx.moveTo(pad.l, py); ctx.lineTo(w - pad.r, py); ctx.stroke();
        ctx.textAlign = "right"; ctx.fillText(LL.fmtNum(v, 2), pad.l - 6, py + 4);
      }
      ctx.strokeStyle = tc.axis;
      ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, h - pad.b); ctx.lineTo(w - pad.r, h - pad.b); ctx.stroke();

      entries.forEach(([gn, b], idx) => {
        const col = SERIES_COLORS[idx % SERIES_COLORS.length];
        const cx = pad.l + ((idx + 0.5) / entries.length) * pw;
        const bw = Math.min(54, pw / (entries.length * 2.2));
        if (b.whisker_lo != null && b.whisker_hi != null) {
          ctx.strokeStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(cx, y2p(b.whisker_lo)); ctx.lineTo(cx, y2p(b.whisker_hi)); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(cx - bw * 0.3, y2p(b.whisker_hi)); ctx.lineTo(cx + bw * 0.3, y2p(b.whisker_hi)); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(cx - bw * 0.3, y2p(b.whisker_lo)); ctx.lineTo(cx + bw * 0.3, y2p(b.whisker_lo)); ctx.stroke();
        }
        if (b.q1 != null && b.q3 != null) {
          ctx.fillStyle = col + "28"; ctx.strokeStyle = col; ctx.lineWidth = 2;
          const top = y2p(b.q3), bot = y2p(b.q1);
          ctx.fillRect(cx - bw / 2, top, bw, Math.max(3, bot - top));
          ctx.strokeRect(cx - bw / 2, top, bw, Math.max(3, bot - top));
        }
        if (b.median != null) {
          ctx.strokeStyle = "#ef4444"; ctx.lineWidth = 2.6;
          ctx.beginPath(); ctx.moveTo(cx - bw / 2, y2p(b.median)); ctx.lineTo(cx + bw / 2, y2p(b.median)); ctx.stroke();
        }
        const sc = scMap[gn];
        if (sc && sc.y && sc.y.length) {
          const xs = sc.x || [];
          const mx = xs.length ? xs.reduce((a, c) => a + c, 0) / xs.length : 0.5;
          const xSpan = xs.length ? Math.max(0.05, Math.max(...xs) - Math.min(...xs)) : 0.2;
          ctx.fillStyle = col;
          ctx.globalAlpha = 0.72;
          sc.y.forEach((yv, i) => {
            if (yv == null) return;
            const dxNorm = xs.length === sc.y.length ? ((xs[i] - mx) / xSpan) : (((i * 37) % 100) / 100 - 0.5);
            const px = cx + dxNorm * bw * 0.82;
            ctx.beginPath();
            ctx.arc(px, y2p(yv), 3.1, 0, Math.PI * 2);
            ctx.fill();
          });
          ctx.globalAlpha = 1.0;
        }
        ctx.fillStyle = tc.ink; ctx.font = "600 11px sans-serif"; ctx.textAlign = "center";
        const nTag = sc && sc.n ? ` (n=${sc.n})` : "";
        ctx.fillText(gn + nTag, cx, h - pad.b + 16);
      });
      if (yUnit) {
        ctx.save(); ctx.translate(14, pad.t + ph / 2); ctx.rotate(-Math.PI / 2);
        ctx.fillStyle = tc.muted; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
        ctx.fillText(yUnit, 0, 0); ctx.restore();
      }
      return;
    }

    // 2. Curves and/or 2D Scatter / Beeswarm
    const xsAll = [], ysAll = [];
    let xUnit = "", yUnit = "";
    Object.values(d.curves || {}).forEach((c) => {
      (c.x || []).forEach((v) => xsAll.push(v));
      (c.y || []).forEach((v) => ysAll.push(v));
      (c.lo || []).forEach((v) => { if (v != null) ysAll.push(v); });
      (c.hi || []).forEach((v) => { if (v != null) ysAll.push(v); });
      if (!xUnit && c.x_unit) xUnit = c.x_unit;
      if (!yUnit && c.y_unit) yUnit = c.y_unit;
    });
    Object.values(d.digitized_scatter || {}).forEach((g) => {
      (g.x || []).forEach((v) => xsAll.push(v));
      (g.y || []).forEach((v) => ysAll.push(v));
      (g.x_lo || []).forEach((v) => { if (v != null) xsAll.push(v); });
      (g.x_hi || []).forEach((v) => { if (v != null) xsAll.push(v); });
      (g.y_lo || []).forEach((v) => { if (v != null) ysAll.push(v); });
      (g.y_hi || []).forEach((v) => { if (v != null) ysAll.push(v); });
      if (!xUnit && g.x_unit) xUnit = g.x_unit;
      if (!yUnit && g.y_unit) yUnit = g.y_unit;
    });
    if (!xsAll.length || !ysAll.length) return;

    let x0 = Math.min(...xsAll), x1 = Math.max(...xsAll);
    let y0 = Math.min(...ysAll), y1 = Math.max(...ysAll);
    const xPad = Math.max((x1 - x0) * 0.05, 1e-4);
    const yPad = Math.max((y1 - y0) * 0.08, 1e-4);
    x0 -= xPad; x1 += xPad; y0 -= yPad; y1 += yPad;
    const x2p = (v) => pad.l + ((v - x0) / (x1 - x0)) * pw;
    const y2p = (v) => pad.t + ((y1 - v) / (y1 - y0)) * ph;

    // Grid & ticks
    ctx.strokeStyle = tc.grid; ctx.lineWidth = 1;
    ctx.fillStyle = tc.muted; ctx.font = "10.5px ui-monospace, monospace";
    for (let i = 0; i <= 4; i++) {
      const yv = y0 + (i / 4) * (y1 - y0), py = y2p(yv);
      ctx.beginPath(); ctx.moveTo(pad.l, py); ctx.lineTo(w - pad.r, py); ctx.stroke();
      ctx.textAlign = "right"; ctx.fillText(LL.fmtNum(yv, 2), pad.l - 6, py + 4);
      const xv = x0 + (i / 4) * (x1 - x0), px = x2p(xv);
      ctx.beginPath(); ctx.moveTo(px, pad.t); ctx.lineTo(px, h - pad.b); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillText(LL.fmtNum(xv, 1), px, h - pad.b + 15);
    }
    ctx.strokeStyle = tc.axis;
    ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, h - pad.b); ctx.lineTo(w - pad.r, h - pad.b); ctx.stroke();

    // Draw curves + ribbons
    const legendItems = [];
    Object.entries(d.curves || {}).forEach(([cn, c], idx) => {
      const col = SERIES_COLORS[idx % SERIES_COLORS.length];
      legendItems.push([cn, col]);
      const xs = c.x || [], ys = c.y || [], lo = c.lo || [], hi = c.hi || [];
      if (lo.length === xs.length && hi.length === xs.length) {
        ctx.beginPath();
        for (let i = 0; i < xs.length; i++) {
          const px = x2p(xs[i]), py = y2p(hi[i]);
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        for (let i = xs.length - 1; i >= 0; i--) ctx.lineTo(x2p(xs[i]), y2p(lo[i]));
        ctx.closePath();
        ctx.fillStyle = col + "28";
        ctx.fill();
      }
      ctx.beginPath();
      for (let i = 0; i < xs.length; i++) {
        const px = x2p(xs[i]), py = y2p(ys[i]);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.strokeStyle = col; ctx.lineWidth = 2.1; ctx.stroke();
    });

    // Draw scatter + errorbars
    const scOffset = Object.keys(d.curves || {}).length;
    Object.entries(d.digitized_scatter || {}).forEach(([gn, g], idx) => {
      const col = SERIES_COLORS[(idx + scOffset) % SERIES_COLORS.length];
      legendItems.push([`${gn} (n=${g.n})`, col]);
      const xs = g.x || [], ys = g.y || [];
      const xlo = g.x_lo || [], xhi = g.x_hi || [], ylo = g.y_lo || [], yhi = g.y_hi || [];
      ctx.strokeStyle = col + "aa"; ctx.lineWidth = 1.2;
      for (let i = 0; i < xs.length; i++) {
        const px = x2p(xs[i]), py = y2p(ys[i]);
        if (i < xlo.length && xlo[i] != null && xhi[i] != null) {
          ctx.beginPath(); ctx.moveTo(x2p(xlo[i]), py); ctx.lineTo(x2p(xhi[i]), py); ctx.stroke();
        }
        if (i < ylo.length && ylo[i] != null && yhi[i] != null) {
          ctx.beginPath(); ctx.moveTo(px, y2p(ylo[i])); ctx.lineTo(px, y2p(yhi[i])); ctx.stroke();
        }
        ctx.beginPath(); ctx.arc(px, py, 3.2, 0, Math.PI * 2);
        ctx.fillStyle = col; ctx.fill();
      }
    });

    // Axis labels
    ctx.fillStyle = tc.muted; ctx.font = "11px sans-serif"; ctx.textAlign = "center";
    if (xUnit) ctx.fillText(xUnit, pad.l + pw / 2, h - 6);
    if (yUnit) {
      ctx.save(); ctx.translate(14, pad.t + ph / 2); ctx.rotate(-Math.PI / 2);
      ctx.fillText(yUnit, 0, 0); ctx.restore();
    }

    // Compact horizontal legend strip at top
    let lx = pad.l + 4;
    ctx.font = "600 10.5px sans-serif"; ctx.textAlign = "left";
    legendItems.slice(0, 6).forEach(([lbl, col]) => {
      ctx.fillStyle = col; ctx.fillRect(lx, 7, 10, 8);
      ctx.fillStyle = tc.ink; ctx.fillText(lbl, lx + 14, 15);
      lx += ctx.measureText(lbl).width + 26;
    });
  };

  /* One-Axis Cross-Paper Empirical Value Comparison Plot */
  LL.renderCompareStrip = function (canvas, rows, onClickRow) {
    const rowH = 26;
    const { ctx, w, h } = setupHiDPI(canvas, Math.max(120, rows.length * rowH + 54));
    const tc = themeColors();
    ctx.fillStyle = tc.bg; ctx.fillRect(0, 0, w, h);
    if (!rows.length) return;

    const pad = { l: Math.min(315, Math.round(w * 0.34)), r: 86, t: 16, b: 32 };
    const pw = Math.max(160, w - pad.l - pad.r);
    const vals = rows.map((r) => r.val);
    let xmin = Math.min(...vals), xmax = Math.max(...vals);
    const sp = Math.max(xmax - xmin, xmin * 0.25, 0.1);
    xmin = Math.max(0, xmin - sp * 0.1);
    xmax = xmax + sp * 0.12;
    const x2p = (v) => pad.l + ((v - xmin) / (xmax - xmin)) * pw;

    ctx.strokeStyle = tc.grid; ctx.lineWidth = 1;
    ctx.fillStyle = tc.muted; ctx.font = "10.5px ui-monospace, monospace";
    for (let i = 0; i <= 5; i++) {
      const v = xmin + (i / 5) * (xmax - xmin), px = x2p(v);
      ctx.beginPath(); ctx.moveTo(px, pad.t); ctx.lineTo(px, h - pad.b); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillText(LL.fmtNum(v, 2), px, h - pad.b + 16);
    }

    const paperColors = {};
    let ci = 0;
    const hitBoxes = [];
    rows.forEach((r, idx) => {
      if (!paperColors[r.paper]) paperColors[r.paper] = SERIES_COLORS[ci++ % SERIES_COLORS.length];
      const col = paperColors[r.paper];
      const cy = pad.t + 14 + idx * rowH;

      ctx.fillStyle = tc.ink; ctx.font = "600 11px sans-serif"; ctx.textAlign = "right";
      const rawLbl = `${r.paper.split("_")[1]} · ${r.group_label}`;
      const lbl = rawLbl.length > 42 ? rawLbl.slice(0, 40) + "…" : rawLbl;
      ctx.fillText(lbl, pad.l - 12, cy + 4);

      const px = x2p(r.val);
      if (r.spreadVal != null && r.spreadVal > 0) {
        ctx.strokeStyle = col; ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.moveTo(x2p(r.val - r.spreadVal), cy);
        ctx.lineTo(x2p(r.val + r.spreadVal), cy);
        ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(px, cy, 5, 0, Math.PI * 2);
      ctx.fillStyle = col; ctx.fill();
      ctx.strokeStyle = tc.bg; ctx.lineWidth = 1.4; ctx.stroke();

      ctx.fillStyle = tc.muted; ctx.font = "10.2px ui-monospace, monospace"; ctx.textAlign = "left";
      ctx.fillText(`${LL.fmtNum(r.val, 3)} ${r.unit}`, px + 9, cy + 3.5);
      hitBoxes.push({ y0: cy - rowH * 0.5, y1: cy + rowH * 0.5, row: r });
    });

    canvas.style.cursor = "pointer";
    canvas.onclick = function (ev) {
      const rect = canvas.getBoundingClientRect();
      const my = ev.clientY - rect.top;
      const hit = hitBoxes.find((hb) => my >= hb.y0 && my <= hb.y1);
      if (hit && onClickRow) onClickRow(hit.row);
    };
  };
})(window.LL);
