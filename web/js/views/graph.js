/* Dedicated Interactive Knowledge Graph (Papers <-> Measures <-> Taxa <-> Architectures) */
window.LL = window.LL || {};

(function (LL) {
  const TYPE_STYLE = {
    paper: { color: "#0f5f73", darkColor: "#4ab3c9", r: 17 },
    measure: { color: "#15803d", darkColor: "#4ade80", r: 12 },
    taxon: { color: "#b45309", darkColor: "#fbbf24", r: 11 },
    arch: { color: "#be185d", darkColor: "#f472b6", r: 10 },
  };

  function buildGraphData(data, filterType) {
    const nodesMap = new Map();
    const edges = [];
    const addNode = (id, label, type, meta) => {
      if (!nodesMap.has(id)) nodesMap.set(id, { id, label, type, meta: meta || {}, deg: 0 });
      return nodesMap.get(id);
    };

    (data.papers || []).forEach((p) => {
      addNode(`paper:${p.paper}`, p.paper, "paper", { title: p.title, year: p.year, doi: p.doi });
    });

    const termLabels = data.term_labels || {};
    const edgeSet = new Set();
    const link = (a, b, rel) => {
      const k = `${a}|${b}`;
      if (edgeSet.has(k)) return;
      edgeSet.add(k);
      edges.push({ a, b, rel });
      if (nodesMap.has(a)) nodesMap.get(a).deg++;
      if (nodesMap.has(b)) nodesMap.get(b).deg++;
    };

    (data.items || []).forEach((it) => {
      const pid = `paper:${it.paper}`;
      (it.measure_terms || []).forEach((mt) => {
        if (filterType !== "ALL" && filterType !== "measure") return;
        const n = addNode(mt, termLabels[mt] || mt.split(":").pop(), "measure", { items: [] });
        n.meta.items = n.meta.items || [];
        n.meta.items.push(`${it.paper}/${it.item}`);
        link(pid, mt, "measures");
      });
    });

    (data.values || []).forEach((v) => {
      const pid = `paper:${v.paper}`;
      const ctx = {};
      (v.context_terms || "").split("; ").forEach((p) => {
        const idx = p.indexOf("=");
        if (idx > 0) ctx[p.slice(0, idx)] = p.slice(idx + 1);
      });
      if ((filterType === "ALL" || filterType === "taxon") && ctx.taxon && !ctx.taxon.includes("not stated")) {
        ctx.taxon.split("|").forEach((t) => {
          const n = addNode(t, termLabels[t] || t.split(":").pop(), "taxon", { items: [] });
          n.meta.items = n.meta.items || [];
          const ik = `${v.paper}/${v.item}`;
          if (!n.meta.items.includes(ik)) n.meta.items.push(ik);
          link(pid, t, "studies");
        });
      }
      if ((filterType === "ALL" || filterType === "arch") && ctx.functional_architecture && !ctx.functional_architecture.includes("not stated")) {
        ctx.functional_architecture.split("|").forEach((t) => {
          const n = addNode(t, termLabels[t] || t.split(":").pop(), "arch", { items: [] });
          n.meta.items = n.meta.items || [];
          const ik = `${v.paper}/${v.item}`;
          if (!n.meta.items.includes(ik)) n.meta.items.push(ik);
          link(pid, t, "architecture");
        });
      }
    });

    return { nodes: Array.from(nodesMap.values()), edges };
  }

  LL.renderGraphView = function (root) {
    const st = LL.state;
    const { nodes, edges } = buildGraphData(st.data, st.graphFilter);

    root.innerHTML = `
      <div class="toolbar">
        <span style="font-weight:700">Entity Filter:</span>
        ${[["ALL", "All entities"], ["measure", "Papers ↔ Measures"], ["taxon", "Papers ↔ Taxa"], ["arch", "Papers ↔ Architectures"]].map(([k, lbl]) =>
          `<button type="button" class="btn btn-sm ${st.graphFilter === k ? "primary" : ""}" data-gf="${k}">${lbl}</button>`
        ).join("")}
        <span class="muted mono" style="margin-left:auto">${nodes.length} nodes · ${edges.length} links · drag any node</span>
      </div>
      <div class="graph-layout">
        <canvas class="graph-canvas" id="kg-canvas"></canvas>
        <div class="card" id="kg-detail">
          <div class="card-title">Node Inspector</div>
          <div class="muted">Click any node in the knowledge graph to inspect shared papers, taxa, architectures, and linked empirical evidence items.</div>
          <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">
            <div class="muted"><span style="color:#0f5f73;font-weight:800">●</span> Paper</div>
            <div class="muted"><span style="color:#15803d;font-weight:800">●</span> Measure (shared nodes bridge papers!)</div>
            <div class="muted"><span style="color:#b45309;font-weight:800">●</span> Lepidoptera Taxon</div>
            <div class="muted"><span style="color:#be185d;font-weight:800">●</span> Functional Architecture</div>
          </div>
        </div>
      </div>
    `;

    root.querySelectorAll("[data-gf]").forEach((b) => {
      b.onclick = () => { st.graphFilter = b.getAttribute("data-gf"); LL.renderGraphView(root); };
    });

    const canvas = document.getElementById("kg-canvas");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(500, Math.round(canvas.getBoundingClientRect().width || 880));
    const H = 560;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");

    // Deterministic layout: papers placed horizontally; shared bridge nodes staggered vertically down the center
    const papers = nodes.filter((n) => n.type === "paper");
    const shared = nodes.filter((n) => n.type !== "paper" && n.deg >= 2);
    const leaves = nodes.filter((n) => n.type !== "paper" && n.deg < 2);
    papers.forEach((n, i) => {
      n.x = W * (papers.length === 1 ? 0.5 : (0.24 + 0.52 * (i / (papers.length - 1))));
      n.y = H * 0.5;
      n.vx = 0; n.vy = 0;
    });
    shared.forEach((n, i) => {
      n.x = W * 0.5;
      n.y = H * (shared.length === 1 ? 0.5 : (0.24 + 0.52 * (i / (shared.length - 1))));
      n.vx = 0; n.vy = 0;
    });
    leaves.forEach((n, i) => {
      const ang = (i / Math.max(leaves.length, 1)) * Math.PI * 2;
      const rad = Math.min(W, H) * 0.40;
      n.x = W * 0.5 + Math.cos(ang) * rad;
      n.y = H * 0.5 + Math.sin(ang) * rad;
      n.vx = 0; n.vy = 0;
    });

    const byId = new Map(nodes.map((n) => [n.id, n]));
    for (let step = 0; step < 180; step++) {
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          const d2 = Math.max(dx * dx + dy * dy, 120);
          const f = 6200 / d2;
          const d = Math.sqrt(d2);
          dx /= d; dy /= d;
          a.vx -= dx * f; a.vy -= dy * f;
          b.vx += dx * f; b.vy += dy * f;
        }
      }
      edges.forEach((e) => {
        const a = byId.get(e.a), b = byId.get(e.b);
        if (!a || !b) return;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.max(Math.hypot(dx, dy), 1);
        const target = b.deg >= 2 ? 170 : 165;
        const f = (d - target) * 0.032;
        a.vx += (dx / d) * f; a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f; b.vy -= (dy / d) * f;
      });
      nodes.forEach((n) => {
        n.vx += (W * 0.5 - n.x) * 0.003;
        n.vy += (H * 0.5 - n.y) * 0.003;
        n.vx *= 0.82; n.vy *= 0.82;
        n.x = Math.max(72, Math.min(W - 72, n.x + n.vx));
        n.y = Math.max(38, Math.min(H - 42, n.y + n.vy));
      });
    }

    let selNode = null;
    let dragNode = null;

    function renderDetail(n) {
      const box = document.getElementById("kg-detail");
      if (!box || !n) return;
      const neigh = edges.filter((e) => e.a === n.id || e.b === n.id)
        .map((e) => byId.get(e.a === n.id ? e.b : e.a)).filter(Boolean);
      const items = (n.meta && n.meta.items) || [];
      box.innerHTML = `
        <div class="card-title">
          <span>${LL.esc(n.label)}</span>
          <span class="pill accent">${LL.esc(n.type)}</span>
        </div>
        <div class="mono muted" style="font-size:11px;margin-bottom:8px">${LL.esc(n.id)}</div>
        ${n.meta && n.meta.title ? `<div style="margin-bottom:8px">${LL.esc(n.meta.title)}</div>` : ""}
        <div style="font-weight:700;font-size:12px;margin:8px 0 4px">Connected Nodes (${neigh.length})</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">
          ${neigh.map((x) => `<span class="pill">${LL.esc(x.label)}</span>`).join("")}
        </div>
        ${items.length ? `
          <div style="font-weight:700;font-size:12px;margin:8px 0 4px">Linked Empirical Items (${items.length})</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            ${items.map((ik) => `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(ik)}">${LL.esc(ik)}</button>`).join("")}
          </div>` : ""}
      `;
    }

    function draw() {
      const dark = LL.isDark();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = dark ? "#141b24" : "#ffffff";
      ctx.fillRect(0, 0, W, H);

      edges.forEach((e) => {
        const a = byId.get(e.a), b = byId.get(e.b);
        if (!a || !b) return;
        const hi = selNode && (selNode.id === a.id || selNode.id === b.id);
        ctx.strokeStyle = hi ? (dark ? "#4ab3c9" : "#0f5f73") : (dark ? "rgba(148,163,184,0.22)" : "rgba(30,41,59,0.16)");
        ctx.lineWidth = hi ? 2.2 : 1.1;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      });

      nodes.forEach((n) => {
        const ts = TYPE_STYLE[n.type] || TYPE_STYLE.measure;
        const col = dark ? ts.darkColor : ts.color;
        const isShared = n.type !== "paper" && n.deg >= 2;
        const r = ts.r + (isShared ? 3 : 0);
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        if (isShared || selNode === n) {
          ctx.strokeStyle = dark ? "#f8fafc" : "#0f172a";
          ctx.lineWidth = 2.4;
          ctx.stroke();
        }
        ctx.fillStyle = dark ? "#e2e8f0" : "#1e293b";
        ctx.font = n.type === "paper" || isShared ? "700 11.5px sans-serif" : "500 10.5px sans-serif";
        ctx.textAlign = "center";
        const disp = n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label;
        ctx.fillText(disp, n.x, n.y + r + 13);
      });
    }

    draw();
    window.addEventListener("ll-theme-redraw", draw);

    const hit = (ev) => {
      const r = canvas.getBoundingClientRect();
      const x = (ev.clientX - r.left) * (W / r.width);
      const y = (ev.clientY - r.top) * (H / r.height);
      return nodes.find((n) => Math.hypot(n.x - x, n.y - y) <= 20);
    };
    canvas.onmousedown = (ev) => {
      const h = hit(ev);
      if (h) { dragNode = h; selNode = h; renderDetail(h); draw(); }
    };
    canvas.onmousemove = (ev) => {
      if (!dragNode) return;
      const r = canvas.getBoundingClientRect();
      dragNode.x = Math.max(36, Math.min(W - 36, (ev.clientX - r.left) * (W / r.width)));
      dragNode.y = Math.max(30, Math.min(H - 30, (ev.clientY - r.top) * (H / r.height)));
      draw();
    };
    window.addEventListener("mouseup", () => { dragNode = null; });
  };
})(window.LL);
