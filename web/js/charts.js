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
    const { ctx, w, h } = setupHiDPI(canvas, Math.max(150, rows.length * 34 + 62));
    const tc = themeColors();
    ctx.fillStyle = tc.bg; ctx.fillRect(0, 0, w, h);
    if (!rows.length) return;

    const pad = { l: 210, r: 28, t: 22, b: 34 };
    const pw = w - pad.l - pad.r;
    const vals = rows.map((r) => r.val);
    let xmin = Math.min(...vals), xmax = Math.max(...vals);
    const sp = Math.max(xmax - xmin, xmin * 0.25, 0.1);
    xmin = Math.max(0, xmin - sp * 0.15);
    xmax = xmax + sp * 0.15;
    const x2p = (v) => pad.l + ((v - xmin) / (xmax - xmin)) * pw;

    ctx.strokeStyle = tc.grid; ctx.lineWidth = 1;
    ctx.fillStyle = tc.muted; ctx.font = "10.5px ui-monospace, monospace";
    for (let i = 0; i <= 5; i++) {
      const v = xmin + (i / 5) * (xmax - xmin), px = x2p(v);
      ctx.beginPath(); ctx.moveTo(px, pad.t); ctx.lineTo(px, h - pad.b); ctx.stroke();
      ctx.textAlign = "center"; ctx.fillText(LL.fmtNum(v, 2), px, h - pad.b + 15);
    }

    const paperColors = {};
    let ci = 0;
    const hitBoxes = [];
    rows.forEach((r, idx) => {
      if (!paperColors[r.paper]) paperColors[r.paper] = SERIES_COLORS[ci++ % SERIES_COLORS.length];
      const col = paperColors[r.paper];
      const cy = pad.t + 18 + idx * 34;

      ctx.fillStyle = tc.ink; ctx.font = "600 11px sans-serif"; ctx.textAlign = "right";
      const lbl = `${r.paper.split("_")[1]} · ${r.group_label.slice(0, 26)}`;
      ctx.fillText(lbl, pad.l - 10, cy + 4);

      const px = x2p(r.val);
      if (r.spreadVal != null && r.spreadVal > 0) {
        ctx.strokeStyle = col; ctx.lineWidth = 2.2;
        ctx.beginPath();
        ctx.moveTo(x2p(r.val - r.spreadVal), cy);
        ctx.lineTo(x2p(r.val + r.spreadVal), cy);
        ctx.stroke();
      }
      ctx.beginPath(); ctx.arc(px, cy, 6, 0, Math.PI * 2);
      ctx.fillStyle = col; ctx.fill();
      ctx.strokeStyle = tc.bg; ctx.lineWidth = 1.5; ctx.stroke();

      ctx.fillStyle = tc.muted; ctx.font = "10.5px ui-monospace, monospace"; ctx.textAlign = "left";
      ctx.fillText(`${LL.fmtNum(r.val, 3)} ${r.unit}`, px + 10, cy + 4);
      hitBoxes.push({ y0: cy - 15, y1: cy + 15, row: r });
    });

    canvas.onclick = function (ev) {
      const rect = canvas.getBoundingClientRect();
      const my = ev.clientY - rect.top;
      const hit = hitBoxes.find((hb) => my >= hb.y0 && my <= hb.y1);
      if (hit && onClickRow) onClickRow(hit.row);
    };
  };
})(window.LL);
