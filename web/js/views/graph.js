/* Interactive GRN Workbench, Genomic Tables Explorer & Corpus Knowledge Graph (Zero-Dependency) */
window.LL = window.LL || {};

(function (LL) {
  // =========================================================================
  // 1. Directed Gene Regulatory Network (GRN) Workbench
  // =========================================================================
  const TIER_META = {
    direct_binding_and_perturbation: {
      label: "Direct binding + perturbation",
      short: "Binding + KO",
      dash: "",
      width: 2.8,
      pill: "ok",
      desc: "Supported by both physical chromatin occupancy (ChIP-seq / CUT&Tag) and functional perturbation (CRISPR / RNAi).",
    },
    perturbation_only: {
      label: "Functional perturbation",
      short: "Perturbation",
      dash: "8 4",
      width: 2.35,
      pill: "accent",
      desc: "Supported by CRISPR knockout or RNAi knockdown phenotyping without direct cis-regulatory binding proof.",
    },
    chromatin_or_binding_only: {
      label: "Chromatin binding + DE",
      short: "ChIP / Binding",
      dash: "9 3 2 3",
      width: 2.25,
      pill: "info",
      desc: "Supported by transcription factor ChIP-seq / CUT&Tag occupancy paired with expression profiling, awaiting functional CRE validation.",
    },
    correlative: {
      label: "Correlative / marker",
      short: "Correlative",
      dash: "3 4",
      width: 2.0,
      pill: "warn",
      desc: "Co-expression, single-nucleus cluster enrichment, or association mapping without direct perturbation or binding.",
    },
  };

  function relStyle(rel, dark) {
    const r = String(rel || "");
    if (r.includes("repress")) {
      return { color: dark ? "#fb7185" : "#be123c", verb: "represses", marker: "tbar", pill: "bad" };
    }
    if (r.includes("activate") || r.includes("required")) {
      return { color: dark ? "#4ade80" : "#15803d", verb: r.includes("required") ? "specifies" : "activates", marker: "arrow", pill: "ok" };
    }
    if (r.includes("binds")) {
      return { color: dark ? "#4ab3c9" : "#0f5f73", verb: "binds CRE", marker: "diamond", pill: "info" };
    }
    return { color: dark ? "#fbbf24" : "#b45309", verb: "marks / assoc.", marker: "arrow", pill: "warn" };
  }

  function grnNodeKey(termId, label, isSource) {
    const lbl = String(label || "");
    if (isSource && termId === "target_gene:doublesex") {
      if (lbl.startsWith("DsxF")) return "target_gene:doublesex::DsxF";
      if (lbl.startsWith("DsxM")) return "target_gene:doublesex::DsxM";
    }
    return termId;
  }

  const GRN_LABEL_MAP = {
    "target_gene:doublesex::DsxF": "DsxF (female)",
    "target_gene:doublesex::DsxM": "DsxM (male)",
    "target_gene:bric_a_brac": "Bric-a-brac (Bab)",
    "target_gene:doublesex": "Doublesex (Dsx)",
    "target_gene:eip75b": "Eip75B (54 pks)",
    "target_gene:multiple_wing_hairs": "Mwh (52 pks)",
    "target_gene:drak": "Drak (7 pks)",
    "target_gene:obstructor_family": "Obstructor B/C/D",
    "target_gene:ivory_lncrna": "ivory (lncRNA)",
    "target_gene:armadillo_beta_catenin": "Armadillo / β-cat",
    "target_gene:wnta": "WntA",
    "target_gene:wingless_wnt1": "Wnt1 / Wingless",
    "target_gene:wnt6": "Wnt6",
    "target_gene:wnt10": "Wnt10",
    "target_gene:frizzled4": "frizzled4 (fz4)",
    "target_gene:frizzled2": "frizzled2 (fz2)",
    "target_gene:optix": "Optix",
    "target_gene:cortex": "cortex (null test)",
    "target_gene:arp2_3_complex": "Arp2/3 complex",
    "target_gene:f_actin_cytoskeleton": "F-actin meshwork",
    "chemical_agent:ck_666": "CK-666 (inhibitor)",
    "scale_type:uvi_cover_scale": "UVI cover scale",
    "scale_type:spatulate_scale": "Spatulate scale",
    "scale_type:spatulate_cover_scale": "Spatulate scale",
    "scale_type:wing_scale": "Scale PCP orient.",
    "pattern_element:eyespot_focus": "Eyespot focus",
    "pattern_element:marginal_band": "Wing margin",
    "pattern_element:central_symmetry_band": "CSS / BSS bands",
    "functional_architecture:ridge_lamellar_multilayer": "Obstructor B/C/D",
    "functional_architecture:melanin_pigmentary": "Melanic scales",
    "functional_architecture:ommochrome": "3-OHK / Ommochrome",
    "functional_architecture:interridge_honeycomb_lattice": "Honeycomb lattice",
    "measure:honeycomb_lattice_height": "Honeycomb height",
    "genetic_element_type:promoter": "ivory 5′ promoter",
  };

  function grnShortLabel(termId, rawLabel, nodeKey) {
    if (GRN_LABEL_MAP[nodeKey]) return GRN_LABEL_MAP[nodeKey];
    if (GRN_LABEL_MAP[termId]) return GRN_LABEL_MAP[termId];
    const lbl = String(rawLabel || termId || "");
    return lbl.length > 22 ? lbl.slice(0, 20) + "…" : lbl;
  }

  function isGrnPhenotypeNode(n) {
    const t = String(n.termId || "");
    return (
      ["scale_type", "phenotype", "pattern_element", "architecture", "measure", "cre"].includes(n.nodeType) ||
      t.startsWith("scale_type:") ||
      t.startsWith("pattern_element:") ||
      t.startsWith("functional_architecture:") ||
      t.startsWith("measure:") ||
      t.startsWith("genetic_element_type:")
    );
  }

  function buildGrnLayout(relations) {
    const nodeMap = new Map();
    const edges = [];

    const ensureNode = (key, termId, rawLabel, ntype, paper) => {
      if (!nodeMap.has(key)) {
        nodeMap.set(key, {
          key,
          termId,
          label: grnShortLabel(termId, rawLabel, key),
          fullLabel: rawLabel || termId,
          nodeType: ntype || "gene",
          inDeg: 0,
          outDeg: 0,
          papers: new Set(),
        });
      }
      const nd = nodeMap.get(key);
      if (paper) nd.papers.add(paper);
      return nd;
    };

    // Pass 1: register all source nodes first so isoform splits exist
    relations.forEach((r) => {
      const sk = grnNodeKey(r.source, r.source_label, true);
      ensureNode(sk, r.source, r.source_label, r.source_type, r.paper);
    });

    // Pass 2: link targets (route Bab -> Dsx locus feedback to DsxF if DsxF exists)
    relations.forEach((r) => {
      const sk = grnNodeKey(r.source, r.source_label, true);
      let tk = grnNodeKey(r.target, r.target_label, false);
      if (tk === "target_gene:doublesex" && nodeMap.has("target_gene:doublesex::DsxF")) {
        tk = "target_gene:doublesex::DsxF";
      }
      const sn = ensureNode(sk, r.source, r.source_label, r.source_type, r.paper);
      const tn = ensureNode(tk, r.target, r.target_label, r.target_type, r.paper);
      if (sk !== tk) {
        sn.outDeg++;
        tn.inDeg++;
      }
      edges.push({ rel: r, srcKey: sk, tgtKey: tk, selfLoop: sk === tk });
    });

    // Assign columns: 0 = upstream regulators, 1 = central integrator hubs, 2 = downstream targets & phenotypes
    const cols = [[], [], []];
    nodeMap.forEach((n) => {
      const isMorph = isGrnPhenotypeNode(n);
      if (isMorph || (n.outDeg === 0 && n.inDeg > 0)) {
        n.col = 2;
      } else if (n.inDeg > 0 && n.outDeg > 0 && !String(n.key).includes("::Dsx")) {
        n.col = 1;
      } else {
        n.col = 0;
      }
      cols[n.col].push(n);
    });

    // Sort integrator hub column deterministically by pathway order (Bab -> ivory -> Armadillo)
    const paperRank = (n) => {
      const ps = Array.from(n.papers).sort();
      const p0 = ps[0] || "";
      if (ps.includes("2025_Loh") && ps.includes("2024_Livraghi")) return 1.5;
      if (p0 === "2025_Loh") return 1.0;
      if (p0 === "2024_Livraghi") return 2.0;
      if (p0 === "2023_Banerjee") return 3.0;
      if (p0 === "2023_Seah") return 4.0;
      return 5.0;
    };

    cols[1].sort((a, b) => paperRank(a) - paperRank(b) || a.label.localeCompare(b.label));

    const maxColNodes = Math.max(1, cols[0].length, cols[1].length, cols[2].length);
    const W = 860;
    const H = Math.max(520, maxColNodes * 60 + 115);
    const colXs = [138, 430, 722];

    const placeCol = (list, ci) => {
      const n = list.length;
      if (!n) return;
      const topPad = ci === 1 && n <= 3 ? Math.max(120, H * 0.22) : 76;
      const botPad = ci === 1 && n <= 3 ? Math.max(95, H * 0.16) : 54;
      const span = Math.max(0, H - topPad - botPad);
      list.forEach((node, idx) => {
        node.x = colXs[ci];
        node.y = n === 1 ? (ci === 1 && H <= 560 ? 248 : H * 0.48) : topPad + (span * idx) / (n - 1);
        node.w = ci === 2 ? 194 : 174;
        node.h = 44;
      });
    };

    // Place hub column first, then order col 0 and col 2 by pathway + connected hub barycenter to minimize crossings
    placeCol(cols[1], 1);

    const baryScore = (node) => {
      const hubYs = [];
      edges.forEach((e) => {
        if (e.srcKey === node.key) {
          const t = nodeMap.get(e.tgtKey);
          if (t && t.col === 1 && t.y != null) hubYs.push(t.y);
        } else if (e.tgtKey === node.key) {
          const s = nodeMap.get(e.srcKey);
          if (s && s.col === 1 && s.y != null) hubYs.push(s.y);
        }
      });
      const pr = paperRank(node);
      if (hubYs.length) return pr * 1000 + hubYs.reduce((a, b) => a + b, 0) / hubYs.length;
      return pr * 1000 + 500;
    };

    cols[0].sort((a, b) => baryScore(a) - baryScore(b) || a.label.localeCompare(b.label));
    cols[2].sort((a, b) => {
      const ba = baryScore(a), bb = baryScore(b);
      if (Math.abs(ba - bb) > 1) return ba - bb;
      const aM = isGrnPhenotypeNode(a) ? 1 : 0;
      const bM = isGrnPhenotypeNode(b) ? 1 : 0;
      if (aM !== bM) return aM - bM;
      return a.label.localeCompare(b.label);
    });

    placeCol(cols[0], 0);
    placeCol(cols[2], 2);

    return { nodes: Array.from(nodeMap.values()), nodeMap, edges, W, H };
  }

  function renderGrnSvg(relations, selectedRelId, dark) {
    const { nodes, nodeMap, edges, W, H } = buildGrnLayout(relations);
    const bg = dark ? "#141b24" : "#ffffff";
    const laneBg = dark ? "rgba(148,163,184,0.05)" : "rgba(15,95,115,0.035)";
    const laneTxt = dark ? "#64748b" : "#94a3b8";
    const nodeFillGene = dark ? "#1c2633" : "#f8fafc";
    const nodeFillHub = dark ? "#12323d" : "#e6f4f7";
    const nodeFillCross = dark ? "#2a1b3d" : "#f3e8ff";
    const nodeFillMorph = dark ? "#2d1f16" : "#fff7ed";
    const nodeStrokeGene = dark ? "#3b5169" : "#94a3b8";
    const nodeStrokeHub = dark ? "#4ab3c9" : "#0f5f73";
    const nodeStrokeCross = dark ? "#c084fc" : "#7e22ce";
    const nodeStrokeMorph = dark ? "#f59e0b" : "#d97706";
    const ink = dark ? "#e2e8f0" : "#0f172a";
    const subInk = dark ? "#94a3b8" : "#64748b";

    // Unique colors for SVG markers
    const markerColors = Array.from(new Set(edges.map((e) => relStyle(e.rel.relation, dark).color)));
    const colorKey = (c) => c.replace(/[^a-zA-Z0-9]/g, "");

    const defs = markerColors.map((col) => {
      const ck = colorKey(col);
      return `
        <marker id="grn-arrow-${ck}" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M 1 1.5 L 9 5 L 1 8.5 z" fill="${col}" />
        </marker>
        <marker id="grn-tbar-${ck}" viewBox="0 0 10 12" refX="7" refY="6" markerWidth="7" markerHeight="9" orient="auto-start-reverse">
          <path d="M 7 1 L 7 11" stroke="${col}" stroke-width="2.6" stroke-linecap="round" />
        </marker>
        <marker id="grn-diamond-${ck}" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
          <path d="M 1 6 L 6 2 L 11 6 L 6 10 z" fill="${col}" />
        </marker>`;
    }).join("");

    // Count parallel edges between same (src, tgt) pair to fan curves symmetrically
    const pairCount = new Map();
    edges.forEach((e) => {
      const pk = `${e.srcKey}|${e.tgtKey}`;
      e.pairIdx = pairCount.get(pk) || 0;
      pairCount.set(pk, e.pairIdx + 1);
    });
    edges.forEach((e) => {
      e.pairTotal = pairCount.get(`${e.srcKey}|${e.tgtKey}`) || 1;
    });

    const edgePaths = edges.map((e) => {
      const r = e.rel;
      const s = nodeMap.get(e.srcKey);
      const t = nodeMap.get(e.tgtKey);
      if (!s || !t) return "";
      const st = relStyle(r.relation, dark);
      const tm = TIER_META[r.evidence_tier] || TIER_META.correlative;
      const sel = r.id === selectedRelId;
      const ck = colorKey(st.color);
      const markerEnd = `url(#grn-${st.marker}-${ck})`;
      const spread = (e.pairIdx - (e.pairTotal - 1) / 2);

      let d = "";
      let lx = 0, ly = 0;
      if (e.selfLoop) {
        const x0 = s.x - 28, y0 = s.y - s.h / 2;
        const x1 = s.x + 28, y1 = s.y - s.h / 2;
        d = `M ${x0} ${y0} C ${x0 - 38} ${y0 - 72}, ${x1 + 38} ${y1 - 72}, ${x1} ${y1 - 3}`;
        lx = s.x;
        ly = y0 - 58;
      } else if (s.col > t.col) {
        const x0 = s.x - s.w / 2 + 12, y0 = s.y - s.h / 2;
        const x1 = t.x + t.w / 2 - 12, y1 = t.y - t.h / 2;
        const cy = Math.min(y0, y1) - 52;
        d = `M ${x0} ${y0} Q ${(x0 + x1) / 2} ${cy}, ${x1} ${y1 - 3}`;
        lx = (x0 + x1) / 2;
        ly = cy + 18;
      } else if (s.col === t.col) {
        const x0 = s.x + s.w / 2, y0 = s.y;
        const x1 = t.x + t.w / 2, y1 = t.y;
        const cx = x0 + 58 + spread * 14;
        d = `M ${x0} ${y0} C ${cx} ${y0}, ${cx} ${y1}, ${x1 + 4} ${y1}`;
        lx = cx - 12;
        ly = (y0 + y1) / 2;
      } else {
        const yOff = spread * (e.pairTotal > 3 ? 7 : 10);
        const x0 = s.x + s.w / 2;
        const y0 = s.y + yOff;
        const x1 = t.x - t.w / 2 - 4;
        const y1 = t.y + yOff;
        const dx = x1 - x0;
        if (t.col - s.col >= 2) {
          // Long-range bypass arc passing gently around middle hubs
          const midY = (y0 + y1) / 2;
          const bendDir = midY > H * 0.55 ? 36 : -36;
          const bendY = midY + bendDir + spread * 28;
          d = `M ${x0} ${y0} C ${x0 + dx * 0.34} ${bendY}, ${x0 + dx * 0.66} ${bendY}, ${x1} ${y1}`;
          lx = (x0 + x1) / 2;
          ly = 0.25 * y0 + 0.5 * bendY + 0.25 * y1;
        } else {
          const cx1 = x0 + dx * 0.44;
          const cx2 = x1 - dx * 0.44;
          const bow = spread * 28;
          d = `M ${x0} ${y0} C ${cx1} ${y0 + bow}, ${cx2} ${y1 + bow}, ${x1} ${y1}`;
          lx = (x0 + x1) / 2;
          ly = (y0 + y1) / 2 + bow * 0.72 - 6;
        }
      }

      const strokeW = sel ? tm.width + 1.5 : tm.width;
      const op = selectedRelId && !sel ? 0.38 : 0.92;
      const badgeTxt = e.selfLoop
        ? "auto-binds"
        : (s.col > t.col ? "feedback ChIP" : (r.context && r.context.taxon && e.pairTotal > 1 ? `${st.verb} (${String(r.context.taxon).split(" ").slice(0, 2).map((w, i) => (i === 0 ? w[0] + "." : w)).join(" ")})` : st.verb));
      const bw = Math.max(84, badgeTxt.length * 6.0 + 14);
      const hitW = e.pairTotal > 2 ? 7 : 12;
      return `
        <g class="grn-edge ${sel ? "selected" : ""}" data-select-rel="${LL.esc(r.id)}" style="cursor:pointer">
          <path d="${d}" fill="none" stroke="transparent" stroke-width="${hitW}" />
          ${sel ? `<path d="${d}" fill="none" stroke="${st.color}" stroke-width="${strokeW + 4.5}" opacity="0.22" />` : ""}
          <path d="${d}" fill="none" stroke="${st.color}" stroke-width="${strokeW}" ${tm.dash ? `stroke-dasharray="${tm.dash}"` : ""} opacity="${op}" marker-end="${markerEnd}" />
          ${sel || e.selfLoop || s.col > t.col ? `
            <rect x="${lx - bw / 2}" y="${ly - 10}" width="${bw}" height="17" rx="8" fill="${bg}" stroke="${st.color}" stroke-width="${sel ? 1.4 : 0.8}" opacity="0.97" />
            <text x="${lx}" y="${ly + 2}" text-anchor="middle" font-size="9.5" font-weight="700" fill="${st.color}">${LL.esc(badgeTxt)}</text>
          ` : ""}
          <title>${LL.esc(`[${r.paper}] ${r.source_label} ${st.verb} ${r.target_label} [${tm.label}]`)}</title>
        </g>`;
    }).join("");

    const nodeBoxes = nodes.map((n) => {
      const isCrossPaper = n.papers && n.papers.size >= 2;
      const isHub = n.col === 1;
      const isMorph = isGrnPhenotypeNode(n);
      const fill = isCrossPaper ? nodeFillCross : (isHub ? nodeFillHub : (isMorph ? nodeFillMorph : nodeFillGene));
      const stroke = isCrossPaper ? nodeStrokeCross : (isHub ? nodeStrokeHub : (isMorph ? nodeStrokeMorph : nodeStrokeGene));
      const rx = isMorph ? 20 : 8;
      const roleTag = isCrossPaper
        ? `★ CROSS-PAPER HUB (${n.papers.size}p)`
        : (isMorph
          ? (n.nodeType === "cre" ? "CIS-REGULATORY CRE" : "PHENOTYPE / TRAIT")
          : (isHub ? "INTEGRATOR HUB" : (n.nodeType === "chemical" ? "SMALL MOLECULE" : (n.nodeType === "noncoding_rna" ? "lncRNA REGULATOR" : (n.col === 0 ? "UPSTREAM REGULATOR" : "TARGET LOCUS")))));
      return `
        <g class="grn-node" data-jump-term="${LL.esc(n.termId)}" style="cursor:pointer">
          ${isCrossPaper ? `<rect x="${n.x - n.w / 2 - 3}" y="${n.y - n.h / 2 - 3}" width="${n.w + 6}" height="${n.h + 6}" rx="${rx + 2}" fill="none" stroke="${nodeStrokeCross}" stroke-width="1.3" stroke-dasharray="4 3" opacity="0.85" />` : ""}
          <rect x="${n.x - n.w / 2}" y="${n.y - n.h / 2}" width="${n.w}" height="${n.h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${isHub || isCrossPaper ? 2.2 : 1.4}" />
          <text x="${n.x}" y="${n.y - 4}" text-anchor="middle" font-size="11.5" font-weight="700" fill="${ink}">${LL.esc(n.label)}</text>
          <text x="${n.x}" y="${n.y + 12}" text-anchor="middle" font-size="8.6" font-weight="700" letter-spacing="0.04em" fill="${isCrossPaper ? nodeStrokeCross : subInk}">${LL.esc(roleTag)}</text>
          <title>Click to open ${LL.esc(n.termId)} in Controlled Vocabulary (${LL.esc(Array.from(n.papers || []).join(", "))})</title>
        </g>`;
    }).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" class="grn-svg" role="img" aria-label="Directed Gene Regulatory Network">
        <defs>${defs}</defs>
        <rect x="0" y="0" width="${W}" height="${H}" fill="${bg}" />
        <rect x="16" y="14" width="244" height="${H - 28}" rx="10" fill="${laneBg}" />
        <rect x="296" y="14" width="268" height="${H - 28}" rx="10" fill="${laneBg}" />
        <rect x="600" y="14" width="244" height="${H - 28}" rx="10" fill="${laneBg}" />
        <text x="138" y="34" text-anchor="middle" font-size="10.5" font-weight="700" letter-spacing="0.06em" fill="${laneTxt}">UPSTREAM REGULATORS</text>
        <text x="430" y="34" text-anchor="middle" font-size="10.5" font-weight="700" letter-spacing="0.06em" fill="${laneTxt}">INTEGRATOR HUBS</text>
        <text x="722" y="34" text-anchor="middle" font-size="10.5" font-weight="700" letter-spacing="0.06em" fill="${laneTxt}">TARGETS &amp; PHENOTYPES</text>
        ${edgePaths}
        ${nodeBoxes}
      </svg>`;
  }

  function renderGrnInspector(rel, dark) {
    if (!rel) {
      return `<div class="card muted" style="padding:20px">Click any edge in the regulatory network (or row below) to inspect its verbatim anchor quote, assays, evidence tier, and linked figures.</div>`;
    }
    const st = relStyle(rel.relation, dark);
    const tm = TIER_META[rel.evidence_tier] || TIER_META.correlative;
    const ctxEntries = Object.entries(rel.context || {}).filter(([, v]) => v != null && String(v).trim() !== "");
    const thumbs = (rel.linked_panels || []).slice(0, 3).map((pid) => ({ pid, src: LL.getThumb(pid) })).filter((x) => x.src);

    return `
      <div class="card" style="display:flex;flex-direction:column;gap:11px">
        <div class="card-title" style="margin:0;align-items:flex-start">
          <div>
            <div style="font-size:14.5px;font-weight:800;line-height:1.3">
              ${LL.esc(rel.source_label)}
              <span class="pill ${st.pill}" style="margin:0 4px">${LL.esc(rel.relation.replace(/_/g, " "))}</span>
              ${LL.esc(rel.target_label)}
            </div>
            <div class="mono muted" style="font-size:11px;margin-top:3px">${LL.esc(rel.paper)} · ${LL.esc(rel.id)}</div>
          </div>
        </div>

        <div class="chip-row">
          <span class="pill ${tm.pill}" title="${LL.esc(tm.desc)}">Tier: ${LL.esc(tm.label)}</span>
          ${rel.effect_direction && rel.effect_direction !== "none" ? `<span class="pill">Effect: ${LL.esc(rel.effect_direction)}</span>` : ""}
          ${(rel.assays || []).map((a) => `<span class="pill">${LL.esc(a.replace(/_/g, " "))}</span>`).join("")}
        </div>

        <div class="muted" style="font-size:11.5px;line-height:1.45">${LL.esc(tm.desc)}</div>

        ${rel.anchor && rel.anchor.quote ? `
          <div>
            <div class="kv-k" style="margin-bottom:4px">Verbatim Paper Anchor (${LL.esc(rel.anchor.where || "Results")})</div>
            <blockquote class="quote-block">“${LL.esc(rel.anchor.quote)}”</blockquote>
          </div>` : ""}

        ${rel.note ? `<div class="muted" style="font-size:12px"><strong>Curation note:</strong> ${LL.esc(rel.note)}</div>` : ""}

        ${ctxEntries.length ? `
          <div>
            <div class="kv-k" style="margin-bottom:5px">Experimental Context (field_set 4)</div>
            <div class="kv-grid">
              ${ctxEntries.map(([k, v]) => `
                <div class="kv-item">
                  <div class="kv-k">${LL.esc(k.replace(/_/g, " "))}</div>
                  <div class="kv-v">${LL.esc(v)}</div>
                </div>`).join("")}
            </div>
          </div>` : ""}

        <div style="display:flex;flex-wrap:wrap;gap:6px;padding-top:6px;border-top:1px solid var(--border)">
          <button type="button" class="btn btn-sm" data-jump-term="${LL.esc(rel.source)}">Source in Vocab ↗</button>
          <button type="button" class="btn btn-sm" data-jump-term="${LL.esc(rel.target)}">Target in Vocab ↗</button>
          ${(rel.linked_items || []).map((it) => `<button type="button" class="btn btn-sm primary mono" data-open-item="${LL.esc(rel.paper)}/${LL.esc(it)}">Audit ${LL.esc(it)} ↗</button>`).join("")}
        </div>

        ${(rel.linked_panels || []).length ? `
          <div>
            <div class="kv-k" style="margin-bottom:5px">Supporting Figure Panels (${rel.linked_panels.length})</div>
            <div class="chip-row" style="margin-bottom:${thumbs.length ? 8 : 0}px">
              ${rel.linked_panels.map((pid) => `<button type="button" class="pill pill-btn mono" data-jump-panel="${LL.esc(pid)}">${LL.esc(pid)} ↗</button>`).join("")}
            </div>
            ${thumbs.length ? `
              <div class="grn-thumb-strip">
                ${thumbs.map((t) => `
                  <button type="button" class="grn-mini-thumb" data-jump-panel="${LL.esc(t.pid)}" title="Open ${LL.esc(t.pid)} in Atlas">
                    <img src="${t.src}" alt="${LL.esc(t.pid)}" />
                    <span class="mono">${LL.esc(t.pid.split("/").slice(1).join("/"))}</span>
                  </button>`).join("")}
              </div>` : ""}
          </div>` : ""}
      </div>`;
  }

  function renderGrnMode(body, data) {
    const st = LL.state;
    const allRels = data.genetic_relations || [];
    if (!allRels.length) {
      body.innerHTML = `<div class="card muted" style="padding:24px">No directed genetic relations (` + "`genetics.yaml`" + `) have been ingested in this release yet.</div>`;
      return;
    }

    const paperCounts = {};
    allRels.forEach((r) => { paperCounts[r.paper] = (paperCounts[r.paper] || 0) + 1; });
    const paperList = Object.keys(paperCounts).sort();
    if (st.grnPaper !== "ALL" && !paperCounts[st.grnPaper]) st.grnPaper = "ALL";
    const paperFiltered = st.grnPaper === "ALL" ? allRels : allRels.filter((r) => r.paper === st.grnPaper);

    const tierCounts = {};
    paperFiltered.forEach((r) => { tierCounts[r.evidence_tier] = (tierCounts[r.evidence_tier] || 0) + 1; });
    const filtered = st.grnTier === "ALL" ? paperFiltered : paperFiltered.filter((r) => r.evidence_tier === st.grnTier);
    if (!st.grnSelectedRel || !filtered.some((r) => r.id === st.grnSelectedRel)) {
      st.grnSelectedRel = filtered[0] ? filtered[0].id : null;
    }
    const selRel = filtered.find((r) => r.id === st.grnSelectedRel) || null;
    const dark = LL.isDark();

    body.innerHTML = `
      <div class="toolbar" style="margin-bottom:6px">
        <span style="font-weight:700;font-size:12px">Paper:</span>
        <button type="button" class="btn btn-sm ${st.grnPaper === "ALL" ? "active" : ""}" data-grn-paper="ALL">All papers (${allRels.length})</button>
        ${paperList.map((p) => `<button type="button" class="btn btn-sm ${st.grnPaper === p ? "active" : ""}" data-grn-paper="${LL.esc(p)}">${LL.esc(p)} (${paperCounts[p]})</button>`).join("")}
        <button type="button" class="btn btn-sm" id="grn-export-json" style="margin-left:auto">Export GRN JSON</button>
      </div>

      <div class="toolbar">
        <span style="font-weight:700;font-size:12px">Evidence Tier:</span>
        <button type="button" class="btn btn-sm ${st.grnTier === "ALL" ? "active" : ""}" data-grn-tier="ALL">All (${paperFiltered.length})</button>
        ${Object.entries(TIER_META).map(([k, m]) => {
          const cnt = tierCounts[k] || 0;
          return `<button type="button" class="btn btn-sm ${st.grnTier === k ? "active" : ""}" data-grn-tier="${k}" title="${LL.esc(m.desc)}">${LL.esc(m.short)} (${cnt})</button>`;
        }).join("")}
      </div>

      <div class="grn-legend">
        <span><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5" stroke="${dark ? "#4ade80" : "#15803d"}" stroke-width="2.4" /></svg> Activates / specifies</span>
        <span><svg width="26" height="10"><line x1="1" y1="5" x2="22" y2="5" stroke="${dark ? "#fb7185" : "#be123c"}" stroke-width="2.4" /><line x1="22" y1="1" x2="22" y2="9" stroke="${dark ? "#fb7185" : "#be123c"}" stroke-width="2.4" /></svg> Represses</span>
        <span><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5" stroke="${dark ? "#4ab3c9" : "#0f5f73"}" stroke-width="2.2" stroke-dasharray="9 3 2 3" /></svg> ChIP binding (dash-dot)</span>
        <span><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5" stroke="currentColor" stroke-width="2.2" stroke-dasharray="7 4" /></svg> Perturbation (dashed)</span>
        <span><svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5" stroke="${dark ? "#fbbf24" : "#b45309"}" stroke-width="2" stroke-dasharray="3 4" /></svg> Correlative (dotted)</span>
        <span style="color:${dark ? "#c084fc" : "#7e22ce"};font-weight:700">★ Cross-paper hub</span>
        <span class="muted" style="margin-left:auto">Click any edge to inspect anchor · Click any node to open in Vocab</span>
      </div>

      <div class="grn-layout">
        <div style="display:flex;flex-direction:column;gap:12px">
          <div class="card" style="padding:10px;overflow:hidden" id="grn-svg-wrap">
            ${filtered.length ? renderGrnSvg(filtered, st.grnSelectedRel, dark) : `<div class="muted" style="padding:24px;text-align:center">No edges match this Paper + Evidence Tier combination.</div>`}
          </div>

          <div class="card" style="padding:12px">
            <div class="card-title" style="font-size:13px;margin-bottom:8px">
              <span>Curated Regulatory Edges (${filtered.length})</span>
              <span class="muted">Every edge verified against verbatim paper text &amp; assay tier rules</span>
            </div>
            <div style="overflow-x:auto">
              <table class="data-table" style="font-size:12px">
                <thead>
                  <tr><th>Paper</th><th>Source</th><th>Relation</th><th>Target</th><th>Evidence Tier</th><th>Assays</th></tr>
                </thead>
                <tbody>
                  ${filtered.map((r) => {
                    const rs = relStyle(r.relation, dark);
                    const tm = TIER_META[r.evidence_tier] || TIER_META.correlative;
                    const active = r.id === st.grnSelectedRel;
                    return `
                      <tr class="grn-row ${active ? "selected" : ""}" data-select-rel="${LL.esc(r.id)}" style="cursor:pointer">
                        <td class="mono muted" style="font-size:11px;white-space:nowrap">${LL.esc(r.paper)}</td>
                        <td><strong>${LL.esc(r.source_label)}</strong></td>
                        <td><span class="pill ${rs.pill}">${LL.esc(rs.verb)}</span></td>
                        <td>${LL.esc(r.target_label)}</td>
                        <td><span class="pill ${tm.pill}">${LL.esc(tm.short)}</span></td>
                        <td class="mono muted" style="font-size:11px">${LL.esc((r.assays || []).join(", "))}</td>
                      </tr>`;
                  }).join("")}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div class="inspector-sticky" id="grn-inspector">
          ${renderGrnInspector(selRel, dark)}
        </div>
      </div>
    `;

    body.querySelector("#grn-export-json").onclick = () => {
      LL.downloadText("livinglit_lepidoptera_grn.json", JSON.stringify(filtered, null, 2), "application/json");
    };

    body.onclick = (ev) => {
      const pBtn = ev.target.closest("[data-grn-paper]");
      if (pBtn) {
        st.grnPaper = pBtn.getAttribute("data-grn-paper");
        st.grnTier = "ALL";
        renderGrnMode(body, data);
        return;
      }
      const tBtn = ev.target.closest("[data-grn-tier]");
      if (tBtn) {
        st.grnTier = tBtn.getAttribute("data-grn-tier");
        renderGrnMode(body, data);
        return;
      }
      // Let global delegation handle [data-jump-term], [data-jump-panel], [data-open-item]
      if (ev.target.closest("[data-jump-term], [data-jump-panel], [data-open-item]")) return;
      const relEl = ev.target.closest("[data-select-rel]");
      if (relEl) {
        st.grnSelectedRel = relEl.getAttribute("data-select-rel");
        const chosen = filtered.find((r) => r.id === st.grnSelectedRel) || null;
        body.querySelector("#grn-svg-wrap").innerHTML = renderGrnSvg(filtered, st.grnSelectedRel, LL.isDark());
        body.querySelector("#grn-inspector").innerHTML = renderGrnInspector(chosen, LL.isDark());
        body.querySelectorAll(".grn-row").forEach((tr) => {
          tr.classList.toggle("selected", tr.getAttribute("data-select-rel") === st.grnSelectedRel);
        });
      }
    };
  }

  // =========================================================================
  // 2. Interactive Genomic & Supplemental Tables (Volcano + Searchable Data)
  // =========================================================================
  function peakColor(peaks, dark) {
    const p = Number(peaks) || 0;
    if (p >= 30) return dark ? "#facc15" : "#d97706";
    if (p >= 15) return dark ? "#4ade80" : "#15803d";
    if (p >= 6) return dark ? "#38bdf8" : "#0284c7";
    return dark ? "#a78bfa" : "#6d28d9";
  }

  function fmtSci(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v == null ? "—" : v);
    if (n === 0) return "<1e-300";
    if (n < 1e-3) return n.toExponential(2);
    return n.toFixed(4);
  }

  function renderVolcanoSvg(allRows, filteredSet, selectedGeneId, dark) {
    const W = 740, H = 310;
    const padL = 58, padR = 24, padT = 20, padB = 42;
    const pw = W - padL - padR, ph = H - padT - padB;
    const bg = dark ? "#141b24" : "#ffffff";
    const grid = dark ? "rgba(148,163,184,0.14)" : "rgba(15,23,42,0.09)";
    const axis = dark ? "#475569" : "#94a3b8";
    const ink = dark ? "#e2e8f0" : "#0f172a";
    const muted = dark ? "#94a3b8" : "#64748b";

    const pts = allRows.map((r) => {
      const fc = Number(r.log2fc);
      const pa = Number(r.p_adj);
      const negLog = !Number.isFinite(pa) ? 0 : (pa <= 0 ? 310 : Math.min(310, -Math.log10(pa)));
      return { row: r, x: Number.isFinite(fc) ? fc : 0, y: negLog, capped: pa <= 0 };
    });

    const xMin = Math.min(-4.8, ...pts.map((p) => p.x - 0.4));
    const xMax = Math.max(4.5, ...pts.map((p) => p.x + 0.4));
    const yMax = Math.max(160, ...pts.map((p) => p.y + 15));
    const sx = (v) => padL + ((v - xMin) / (xMax - xMin)) * pw;
    const sy = (v) => padT + ph - (v / yMax) * ph;

    const xTicks = [-4, -2, 0, 2, 4].filter((t) => t >= xMin && t <= xMax);
    const yTicks = [0, 50, 100, 150, 200, 250, 300].filter((t) => t <= yMax);
    const landmarks = new Set(["Bab", "Eip75B", "Mwh", "Drak", "CAP", "Cpr92F", "B-H1", "Cad96Cb", "Steppke", "Skel"]);
    const labelOffsets = {
      Eip75B: [-38, -9],
      Mwh: [7, -9],
      Drak: [8, 12],
      CAP: [7, 4],
      Cpr92F: [7, -5],
      Bab: [7, 4],
      "B-H1": [7, 4],
      Cad96Cb: [7, 4],
      Steppke: [-46, -6],
      Skel: [7, 4],
    };

    const dots = pts.map((p) => {
      const r = p.row;
      const inFilt = filteredSet.has(r.gene_id);
      const sel = r.gene_id === selectedGeneId;
      const cx = sx(p.x), cy = sy(p.y);
      const col = peakColor(r.chip_peaks, dark);
      const rad = sel ? 7.5 : (Number(r.chip_peaks) >= 20 ? 5.8 : (Number(r.chip_peaks) >= 10 ? 4.8 : 4.0));
      const op = sel ? 1 : (inFilt ? 0.88 : 0.16);
      const sym = (r.symbol && r.symbol !== "NA") ? r.symbol : r.gene_id;
      const showLbl = sel || (inFilt && landmarks.has(r.symbol));
      const [dx, dy] = labelOffsets[r.symbol] || [7, 3];
      return `
        <g data-volcano-gene="${LL.esc(r.gene_id)}" style="cursor:pointer">
          ${sel ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad + 4}" fill="none" stroke="${col}" stroke-width="2" opacity="0.55" />` : ""}
          <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${rad}" fill="${col}" fill-opacity="${op}" stroke="${sel ? ink : bg}" stroke-width="${sel ? 1.8 : 0.7}" />
          ${showLbl ? `<text x="${(cx + dx).toFixed(1)}" y="${(cy + dy).toFixed(1)}" font-size="10.5" font-weight="${sel || Number(r.chip_peaks) >= 24 ? 800 : 600}" fill="${ink}">${LL.esc(sym)}</text>` : ""}
          <title>${LL.esc(`${sym} (${r.gene_id})\nlog2FC: ${LL.fmtNum(r.log2fc, 3)} | p_adj: ${fmtSci(r.p_adj)} | Bab ChIP peaks: ${r.chip_peaks}\n${r.product || ""}`)}</title>
        </g>`;
    }).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" class="volcano-svg" role="img" aria-label="Interactive Volcano Plot">
        <rect x="0" y="0" width="${W}" height="${H}" fill="${bg}" />
        ${xTicks.map((t) => `<line x1="${sx(t).toFixed(1)}" y1="${padT}" x2="${sx(t).toFixed(1)}" y2="${padT + ph}" stroke="${t === 0 ? axis : grid}" stroke-dasharray="${t === 0 ? "4 3" : ""}" />`).join("")}
        ${yTicks.map((t) => `<line x1="${padL}" y1="${sy(t).toFixed(1)}" x2="${padL + pw}" y2="${sy(t).toFixed(1)}" stroke="${grid}" />`).join("")}
        <line x1="${padL}" y1="${padT + ph}" x2="${padL + pw}" y2="${padT + ph}" stroke="${axis}" />
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + ph}" stroke="${axis}" />
        ${xTicks.map((t) => `<text x="${sx(t).toFixed(1)}" y="${padT + ph + 16}" text-anchor="middle" font-size="10.5" fill="${muted}">${t}</text>`).join("")}
        ${yTicks.map((t) => `<text x="${padL - 8}" y="${(sy(t) + 3.5).toFixed(1)}" text-anchor="end" font-size="10.5" fill="${muted}">${t === 300 ? "300+" : t}</text>`).join("")}
        <text x="${padL + pw / 2}" y="${H - 7}" text-anchor="middle" font-size="11" font-weight="700" fill="${ink}">log₂ Fold Change (Scale3 UVI vs other scale clusters)</text>
        <text x="15" y="${padT + ph / 2}" text-anchor="middle" font-size="11" font-weight="700" fill="${ink}" transform="rotate(-90 15 ${padT + ph / 2})">−log₁₀(p_adj)</text>
        ${dots}
      </svg>`;
  }

  function detectMorphMeta(tbl) {
    const sample = (tbl.rows && tbl.rows[0]) || {};
    const hasSpacing = Object.prototype.hasOwnProperty.call(sample, "spacing_um");
    const numKey = hasSpacing ? "spacing_um" : (Object.prototype.hasOwnProperty.call(sample, "value") ? "value" : Object.keys(sample).find((k) => typeof sample[k] === "number") || "value");
    const titleLow = `${tbl.title || ""} ${tbl.note || ""}`.toLowerCase();
    const unit = hasSpacing ? "µm" : ((/\bnm\b|\(in nm\)/.test(titleLow) || titleLow.includes("honeycomb")) ? "nm" : (/\bµm\b|\bum\b/.test(titleLow) ? "µm" : ""));
    const measureLabel = hasSpacing ? "Fourier Inter-Ridge Spacing" : (titleLow.includes("honeycomb") ? "Honeycomb Lattice Height" : "Measured Value");
    const cleanSheet = (s) => {
      const m = String(s || "").match(/\(([^)]+)\)/);
      return m ? m[1].trim() : String(s || "").trim();
    };
    const groupOf = (r) => {
      if (r.sex_genotype != null || r.scale_type != null) {
        return `${r.sex_genotype || ""} | ${r.scale_type || ""}`;
      }
      if (r.sheet != null && r.group != null) {
        return `${cleanSheet(r.sheet)} | ${r.group}`;
      }
      if (r.group != null) return String(r.group);
      return Object.entries(r).filter(([k]) => k !== numKey).map(([, v]) => String(v)).join(" | ") || "all";
    };
    return { numKey, unit, measureLabel, hasSpacing, cleanSheet, groupOf };
  }

  function renderMorphStripSvg(rows, tbl, dark) {
    const meta = detectMorphMeta(tbl);
    const groups = new Map();
    rows.forEach((r) => {
      const k = meta.groupOf(r);
      if (!groups.has(k)) groups.set(k, []);
      const v = Number(r[meta.numKey]);
      if (Number.isFinite(v)) groups.get(k).push(v);
    });
    const entries = Array.from(groups.entries()).map(([k, vals]) => {
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
      const sd = vals.length > 1 ? Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / (vals.length - 1)) : 0;
      return { k, vals, mean, sd };
    }).sort((a, b) => a.mean - b.mean);

    if (!entries.length) {
      return `<div class="muted" style="padding:18px;text-align:center">No numeric rows match the current filter.</div>`;
    }

    const W = 780, rowH = 34, padL = 248, padR = 128, padT = 18, padB = 34;
    const H = padT + padB + entries.length * rowH;
    const pw = W - padL - padR;
    const bg = dark ? "#141b24" : "#ffffff";
    const grid = dark ? "rgba(148,163,184,0.14)" : "rgba(15,23,42,0.09)";
    const ink = dark ? "#e2e8f0" : "#0f172a";
    const muted = dark ? "#94a3b8" : "#64748b";
    const rawMax = Math.max(1e-6, ...entries.flatMap((e) => e.vals));
    const stepBase = Math.pow(10, Math.floor(Math.log10(rawMax / 4.5)));
    const niceMult = [1, 2, 2.5, 5, 10].find((m) => rawMax / (stepBase * m) <= 6) || 10;
    const tickStep = stepBase * niceMult;
    const maxV = Math.ceil((rawMax * 1.05) / tickStep) * tickStep;
    const ticks = [];
    for (let t = 0; t <= maxV + 1e-9; t += tickStep) ticks.push(Number(t.toFixed(6)));
    const sx = (v) => padL + (v / maxV) * pw;
    const dec = maxV >= 100 ? 1 : 2;

    return `
      <svg viewBox="0 0 ${W} ${H}" class="volcano-svg" role="img" aria-label="${LL.esc(meta.measureLabel)} distribution">
        <rect x="0" y="0" width="${W}" height="${H}" fill="${bg}" />
        ${ticks.map((t) => `<line x1="${sx(t).toFixed(1)}" y1="${padT}" x2="${sx(t).toFixed(1)}" y2="${H - padB}" stroke="${grid}" />`).join("")}
        ${entries.map((g, gi) => {
          const cy = padT + gi * rowH + rowH / 2;
          const low = g.k.toLowerCase();
          const col = (low.includes("uvi") || low.includes("treatment") || low.includes("ck666"))
            ? (dark ? "#c084fc" : "#7e22ce")
            : (low.includes("spatulate") ? (dark ? "#fbbf24" : "#b45309") : (dark ? "#4ab3c9" : "#0f5f73"));
          const dispLbl = g.k.replace(/_/g, " ");
          const truncLbl = dispLbl.length > 36 ? dispLbl.slice(0, 34) + "…" : dispLbl;
          return `
            <text x="${padL - 10}" y="${cy + 3.5}" text-anchor="end" font-size="10.2" font-weight="600" fill="${ink}">${LL.esc(truncLbl)}</text>
            <line x1="${sx(Math.max(0, g.mean - g.sd)).toFixed(1)}" y1="${cy}" x2="${sx(Math.min(maxV, g.mean + g.sd)).toFixed(1)}" y2="${cy}" stroke="${col}" stroke-width="2.5" opacity="0.65" />
            ${g.vals.map((v, vi) => `<circle cx="${sx(v).toFixed(1)}" cy="${(cy + ((vi % 5) - 2) * 2.2).toFixed(1)}" r="2.6" fill="${col}" fill-opacity="0.68" />`).join("")}
            <circle cx="${sx(g.mean).toFixed(1)}" cy="${cy}" r="4.6" fill="${bg}" stroke="${col}" stroke-width="2.4" />
            <text x="${(padL + pw + 8).toFixed(1)}" y="${cy + 3.5}" font-size="9.8" font-family="monospace" fill="${muted}">${g.mean.toFixed(dec)}±${g.sd.toFixed(dec)} (n=${g.vals.length})</text>`;
        }).join("")}
        ${ticks.map((t) => `<text x="${sx(t).toFixed(1)}" y="${H - 14}" text-anchor="middle" font-size="10.5" fill="${muted}">${t}${meta.unit ? " " + meta.unit : ""}</text>`).join("")}
      </svg>`;
  }

  function renderTablesMode(body, data) {
    const st = LL.state;
    const tables = data.genomic_tables || [];
    if (!tables.length) {
      body.innerHTML = `<div class="card muted" style="padding:24px">No supplemental genomic tables have been ingested in this release yet.</div>`;
      return;
    }
    if (!st.genomicTableId || !tables.some((t) => `${t.paper}/${t.id}` === st.genomicTableId)) {
      st.genomicTableId = `${tables[0].paper}/${tables[0].id}`;
    }
    const tbl = tables.find((t) => `${t.paper}/${t.id}` === st.genomicTableId) || tables[0];
    const isDe = tbl.kind === "de_genes";
    const morphMeta = isDe ? null : detectMorphMeta(tbl);
    let sortKey = isDe ? "chip_peaks_desc" : "val_asc";
    let selGene = null;

    body.innerHTML = `
      <div class="toolbar">
        <span style="font-weight:700;font-size:12px">Supplemental Dataset:</span>
        ${tables.map((t) => {
          const tid = `${t.paper}/${t.id}`;
          return `<button type="button" class="btn btn-sm ${tid === st.genomicTableId ? "active" : ""}" data-select-table="${LL.esc(tid)}">${LL.esc(t.paper)} · ${LL.esc(t.id)} <span class="pill">${t.n_rows}</span></button>`;
        }).join("")}
      </div>

      <div class="card" style="margin-bottom:12px">
        <div class="card-title">
          <span>${LL.esc(tbl.title)}</span>
          <div style="display:flex;gap:6px;flex-wrap:wrap">
            <button type="button" class="btn btn-sm" id="gt-export-csv">Export CSV</button>
            <button type="button" class="btn btn-sm" id="gt-export-json">Export JSON</button>
          </div>
        </div>
        <div class="chip-row" style="margin-bottom:8px">
          <span class="pill accent">${LL.esc(tbl.kind.replace(/_/g, " "))}</span>
          ${tbl.assay ? `<span class="pill">${LL.esc(tbl.assay)}</span>` : ""}
          ${tbl.taxon ? `<span class="pill">${LL.esc(tbl.taxon)}</span>` : ""}
          ${tbl.stage ? `<span class="pill">${LL.esc(tbl.stage)}</span>` : ""}
          <span class="pill ok">${tbl.n_rows} rows parsed from ${LL.esc(tbl.file.split("/").pop())}</span>
        </div>
        ${tbl.contrast ? `<div class="muted" style="margin-bottom:6px"><strong>Contrast:</strong> ${LL.esc(tbl.contrast)}</div>` : ""}
        <div class="chip-row">
          ${(tbl.linked_items || []).map((it) => `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(tbl.paper)}/${LL.esc(it)}">Audit ${LL.esc(it)} ↗</button>`).join("")}
          ${(tbl.linked_panels || []).map((pid) => `<button type="button" class="pill pill-btn mono" data-jump-panel="${LL.esc(pid)}">Panel ${LL.esc(pid)} ↗</button>`).join("")}
        </div>
      </div>

      ${isDe ? `
        <div class="card" style="margin-bottom:12px;padding:12px">
          <div class="card-title" style="font-size:13px;margin-bottom:6px">
            <span>Interactive Volcano Plot (colored by Bab ChIP-seq peak count)</span>
            <div class="chip-row" style="font-size:11px">
              <span class="pill" style="color:${peakColor(35, LL.isDark())}">● ≥30 peaks</span>
              <span class="pill" style="color:${peakColor(18, LL.isDark())}">● 15–29</span>
              <span class="pill" style="color:${peakColor(8, LL.isDark())}">● 6–14</span>
              <span class="pill" style="color:${peakColor(3, LL.isDark())}">● 3–5</span>
            </div>
          </div>
          <div id="gt-plot-wrap"></div>
        </div>
      ` : `
        <div class="card" style="margin-bottom:12px;padding:12px">
          <div class="card-title" style="font-size:13px;margin-bottom:6px">
            <span>${LL.esc(morphMeta.measureLabel)} Distribution (Mean ± SD &amp; Individual Measurements)</span>
            <span class="muted">Direct from ${LL.esc(tbl.paper)} · ${LL.esc(tbl.file.split("/").pop())}</span>
          </div>
          <div id="gt-plot-wrap"></div>
        </div>
      `}

      <div class="toolbar">
        <input type="search" id="gt-search" placeholder="${isDe ? "Search gene symbol, LOC ID, or product (e.g. Mwh, Eip75B, chitin, kinase)…" : "Filter species, treatment, genotype, or scale class…"}" value="${LL.esc(st.genomicTableQuery)}" style="max-width:380px" />
        ${isDe ? `
          <label class="chk">Min Bab ChIP peaks:
            <select id="gt-min-peaks">
              ${[0, 5, 10, 20, 40].map((v) => `<option value="${v}" ${Number(st.genomicMinPeaks) === v ? "selected" : ""}>≥ ${v}</option>`).join("")}
            </select>
          </label>
          <select id="gt-sort">
            <option value="chip_peaks_desc">Sort: ChIP Peaks ↓</option>
            <option value="abs_fc_desc">Sort: |log2FC| ↓</option>
            <option value="fc_desc">Sort: log2FC ↓ (UVI up)</option>
            <option value="fc_asc">Sort: log2FC ↑ (UVI down)</option>
            <option value="padj_asc">Sort: p_adj ↑</option>
            <option value="sym_asc">Sort: Symbol A→Z</option>
          </select>
        ` : `
          <select id="gt-sort">
            <option value="val_asc">Sort: Value ↑</option>
            <option value="val_desc">Sort: Value ↓</option>
            <option value="group_asc">Sort: Group A→Z</option>
          </select>
        `}
        <span class="muted mono" id="gt-row-count" style="margin-left:auto"></span>
      </div>

      <div class="card" style="padding:0;overflow:hidden">
        <div style="max-height:460px;overflow:auto" id="gt-table-wrap"></div>
      </div>
    `;

    function getFilteredRows() {
      const q = (st.genomicTableQuery || "").trim().toLowerCase();
      const minP = Number(st.genomicMinPeaks) || 0;
      let rows = (tbl.rows || []).filter((r) => {
        if (isDe && Number(r.chip_peaks || 0) < minP) return false;
        if (!q) return true;
        return Object.values(r).join(" ").toLowerCase().includes(q);
      });
      rows = rows.slice();
      if (isDe) {
        if (sortKey === "chip_peaks_desc") rows.sort((a, b) => (Number(b.chip_peaks) || 0) - (Number(a.chip_peaks) || 0));
        else if (sortKey === "abs_fc_desc") rows.sort((a, b) => Math.abs(Number(b.log2fc) || 0) - Math.abs(Number(a.log2fc) || 0));
        else if (sortKey === "fc_desc") rows.sort((a, b) => (Number(b.log2fc) || 0) - (Number(a.log2fc) || 0));
        else if (sortKey === "fc_asc") rows.sort((a, b) => (Number(a.log2fc) || 0) - (Number(b.log2fc) || 0));
        else if (sortKey === "padj_asc") rows.sort((a, b) => (Number(a.p_adj) || 1) - (Number(b.p_adj) || 1));
        else if (sortKey === "sym_asc") rows.sort((a, b) => String(a.symbol || a.gene_id).localeCompare(String(b.symbol || b.gene_id)));
      } else {
        const nk = morphMeta.numKey;
        if (sortKey === "val_asc") rows.sort((a, b) => (Number(a[nk]) || 0) - (Number(b[nk]) || 0));
        else if (sortKey === "val_desc") rows.sort((a, b) => (Number(b[nk]) || 0) - (Number(a[nk]) || 0));
        else rows.sort((a, b) => morphMeta.groupOf(a).localeCompare(morphMeta.groupOf(b)));
      }
      return rows;
    }

    function updateTableAndPlot() {
      const rows = getFilteredRows();
      const cntEl = body.querySelector("#gt-row-count");
      if (cntEl) cntEl.textContent = `Showing ${rows.length} of ${tbl.n_rows} rows`;

      const plotEl = body.querySelector("#gt-plot-wrap");
      if (isDe) {
        const filtSet = new Set(rows.map((r) => r.gene_id));
        if (plotEl) plotEl.innerHTML = renderVolcanoSvg(tbl.rows || [], filtSet, selGene, LL.isDark());
      } else if (plotEl) {
        plotEl.innerHTML = renderMorphStripSvg(rows, tbl, LL.isDark());
      }

      const wrap = body.querySelector("#gt-table-wrap");
      if (!wrap) return;
      if (isDe) {
        const maxPks = Math.max(1, ...(tbl.rows || []).map((r) => Number(r.chip_peaks) || 0));
        wrap.innerHTML = `
          <table class="data-table" style="font-size:12px">
            <thead>
              <tr><th>Symbol</th><th>Gene ID</th><th>log₂FC</th><th>Linear FC</th><th>p_adj</th><th>Bab ChIP Peaks</th><th>pct.1 / pct.2</th><th>Annotated Product</th></tr>
            </thead>
            <tbody>
              ${rows.map((r) => {
                const fc = Number(r.log2fc);
                const lin = Number.isFinite(fc) ? Math.pow(2, fc) : NaN;
                const pks = Number(r.chip_peaks) || 0;
                const pctW = Math.round((pks / maxPks) * 100);
                const isSel = r.gene_id === selGene;
                return `
                  <tr class="grn-row ${isSel ? "selected" : ""}" data-volcano-gene="${LL.esc(r.gene_id)}" style="cursor:pointer">
                    <td><strong>${LL.esc(r.symbol || "—")}</strong></td>
                    <td class="mono muted" style="font-size:11px">${LL.esc(r.gene_id)}</td>
                    <td><span class="pill ${fc >= 0 ? "ok" : "bad"} mono">${fc >= 0 ? "+" : ""}${LL.fmtNum(fc, 3)}</span></td>
                    <td class="mono">${Number.isFinite(lin) ? `${LL.fmtNum(lin, 2)}×` : "—"}</td>
                    <td class="mono">${LL.esc(fmtSci(r.p_adj))}</td>
                    <td>
                      <div style="display:flex;align-items:center;gap:6px">
                        <span class="mono" style="min-width:24px;font-weight:700">${pks}</span>
                        <div class="peak-bar-bg"><div class="peak-bar-fill" style="width:${pctW}%;background:${peakColor(pks, LL.isDark())}"></div></div>
                      </div>
                    </td>
                    <td class="mono muted">${LL.fmtNum(r.pct_1, 2)} / ${LL.fmtNum(r.pct_2, 2)}</td>
                    <td>${LL.esc(r.product || "—")}</td>
                  </tr>`;
              }).join("")}
            </tbody>
          </table>`;
      } else if (morphMeta.hasSpacing) {
        wrap.innerHTML = `
          <table class="data-table" style="font-size:12px">
            <thead>
              <tr><th>#</th><th>Sex / Genotype</th><th>Scale Type</th><th>Fourier Inter-Ridge Spacing (µm)</th></tr>
            </thead>
            <tbody>
              ${rows.map((r, i) => `
                <tr>
                  <td class="mono muted">${i + 1}</td>
                  <td>${LL.esc(String(r.sex_genotype || "").replace(/_/g, " "))}</td>
                  <td><span class="pill">${LL.esc(String(r.scale_type || "").replace(/_/g, " "))}</span></td>
                  <td class="mono" style="font-weight:700">${LL.fmtNum(r.spacing_um, 4)} µm</td>
                </tr>`).join("")}
            </tbody>
          </table>`;
      } else {
        const hasSheet = rows.some((r) => r.sheet != null);
        const nk = morphMeta.numKey;
        const unitSfx = morphMeta.unit ? ` ${morphMeta.unit}` : "";
        wrap.innerHTML = `
          <table class="data-table" style="font-size:12px">
            <thead>
              <tr><th>#</th>${hasSheet ? "<th>Species / Sheet</th>" : ""}<th>Treatment / Group</th><th>${LL.esc(morphMeta.measureLabel)}${morphMeta.unit ? ` (${LL.esc(morphMeta.unit)})` : ""}</th></tr>
            </thead>
            <tbody>
              ${rows.map((r, i) => `
                <tr>
                  <td class="mono muted">${i + 1}</td>
                  ${hasSheet ? `<td><strong>${LL.esc(morphMeta.cleanSheet(r.sheet))}</strong></td>` : ""}
                  <td><span class="pill">${LL.esc(String(r.group || "").replace(/_/g, " "))}</span></td>
                  <td class="mono" style="font-weight:700">${LL.fmtNum(r[nk], morphMeta.unit === "nm" ? 2 : 4)}${LL.esc(unitSfx)}</td>
                </tr>`).join("")}
            </tbody>
          </table>`;
      }
    }

    updateTableAndPlot();

    body.querySelector("#gt-search").oninput = (e) => {
      st.genomicTableQuery = e.target.value;
      updateTableAndPlot();
    };
    const minSel = body.querySelector("#gt-min-peaks");
    if (minSel) minSel.onchange = (e) => { st.genomicMinPeaks = Number(e.target.value); updateTableAndPlot(); };
    body.querySelector("#gt-sort").onchange = (e) => { sortKey = e.target.value; updateTableAndPlot(); };

    body.querySelector("#gt-export-json").onclick = () => {
      LL.downloadText(`${tbl.paper}_${tbl.id}.json`, JSON.stringify(getFilteredRows(), null, 2), "application/json");
    };
    body.querySelector("#gt-export-csv").onclick = () => {
      const rows = getFilteredRows();
      if (!rows.length) return;
      const cols = Object.keys(rows[0]);
      const q = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
      const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => q(r[c])).join(","))].join("\n");
      LL.downloadText(`${tbl.paper}_${tbl.id}.csv`, csv, "text/csv");
    };

    body.onclick = (ev) => {
      const tBtn = ev.target.closest("[data-select-table]");
      if (tBtn) {
        st.genomicTableId = tBtn.getAttribute("data-select-table");
        st.genomicTableQuery = "";
        st.genomicMinPeaks = 0;
        renderTablesMode(body, data);
        return;
      }
      const gEl = ev.target.closest("[data-volcano-gene]");
      if (gEl && isDe) {
        const gid = gEl.getAttribute("data-volcano-gene");
        selGene = selGene === gid ? null : gid;
        updateTableAndPlot();
      }
    };
  }

  // =========================================================================
  // 3. Corpus Knowledge Graph (Papers <-> Measures <-> Genes <-> Taxa <-> Arch)
  // =========================================================================
  const TYPE_STYLE = {
    paper: { color: "#0f5f73", darkColor: "#4ab3c9", r: 17 },
    measure: { color: "#15803d", darkColor: "#4ade80", r: 12 },
    gene: { color: "#7c3aed", darkColor: "#a78bfa", r: 12 },
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
      const addCtxType = (key, ntype, relName) => {
        if ((filterType === "ALL" || filterType === ntype) && ctx[key] && !ctx[key].includes("not stated") && !ctx[key].includes("not applicable")) {
          ctx[key].split("|").forEach((t) => {
            if (!t || !t.includes(":")) return;
            const n = addNode(t, termLabels[t] || t.split(":").pop(), ntype, { items: [] });
            n.meta.items = n.meta.items || [];
            const ik = `${v.paper}/${v.item}`;
            if (!n.meta.items.includes(ik)) n.meta.items.push(ik);
            link(pid, t, relName);
          });
        }
      };
      addCtxType("taxon", "taxon", "studies");
      addCtxType("functional_architecture", "arch", "architecture");
      addCtxType("target_gene", "gene", "perturbs_or_profiles");
    });

    // Also attach target genes referenced in genetics.yaml relations
    if (filterType === "ALL" || filterType === "gene") {
      (data.genetic_relations || []).forEach((r) => {
        const pid = `paper:${r.paper}`;
        [r.source, r.target].forEach((tid) => {
          if (String(tid || "").startsWith("target_gene:")) {
            const n = addNode(tid, termLabels[tid] || tid.split(":").pop(), "gene", { items: [], rels: [] });
            n.meta.rels = n.meta.rels || [];
            if (!n.meta.rels.includes(r.id)) n.meta.rels.push(r.id);
            link(pid, tid, "regulates");
          }
        });
      });
    }

    return { nodes: Array.from(nodesMap.values()), edges };
  }

  function renderCorpusGraphMode(body, data) {
    const st = LL.state;
    const { nodes, edges } = buildGraphData(data, st.graphFilter);

    body.innerHTML = `
      <div class="toolbar">
        <span style="font-weight:700;font-size:12px">Entity Filter:</span>
        ${[
          ["ALL", "All entities"],
          ["measure", "Papers ↔ Measures"],
          ["gene", "Papers ↔ Target Genes"],
          ["taxon", "Papers ↔ Taxa"],
          ["arch", "Papers ↔ Architectures"],
        ].map(([k, lbl]) =>
          `<button type="button" class="btn btn-sm ${st.graphFilter === k ? "primary" : ""}" data-gf="${k}">${lbl}</button>`
        ).join("")}
        <span class="muted mono" style="margin-left:auto">${nodes.length} nodes · ${edges.length} links · drag any node</span>
      </div>
      <div class="graph-layout">
        <canvas class="graph-canvas" id="kg-canvas"></canvas>
        <div class="card" id="kg-detail">
          <div class="card-title">Node Inspector</div>
          <div class="muted">Click any node in the knowledge graph to inspect shared papers, target genes, taxa, architectures, and linked empirical evidence items.</div>
          <div style="margin-top:12px;display:flex;flex-direction:column;gap:6px">
            <div class="muted"><span style="color:#0f5f73;font-weight:800">●</span> Paper</div>
            <div class="muted"><span style="color:#15803d;font-weight:800">●</span> Measure (shared nodes bridge papers)</div>
            <div class="muted"><span style="color:#7c3aed;font-weight:800">●</span> Target Gene / Regulator</div>
            <div class="muted"><span style="color:#b45309;font-weight:800">●</span> Lepidoptera Taxon</div>
            <div class="muted"><span style="color:#be185d;font-weight:800">●</span> Functional Architecture</div>
          </div>
        </div>
      </div>
    `;

    body.querySelectorAll("[data-gf]").forEach((b) => {
      b.onclick = () => { st.graphFilter = b.getAttribute("data-gf"); renderCorpusGraphMode(body, data); };
    });

    const canvas = body.querySelector("#kg-canvas");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const W = Math.max(500, Math.round(canvas.getBoundingClientRect().width || 880));
    const H = 560;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext("2d");

    const papers = nodes.filter((n) => n.type === "paper");
    const shared = nodes.filter((n) => n.type !== "paper" && n.deg >= 2);
    const leaves = nodes.filter((n) => n.type !== "paper" && n.deg < 2);
    papers.forEach((n, i) => {
      const ang = (i / Math.max(papers.length, 1)) * Math.PI * 2 - Math.PI / 2;
      const rad = papers.length <= 2 ? W * 0.25 : Math.min(W, H) * 0.25;
      n.x = papers.length === 1 ? W * 0.5 : (papers.length === 2 ? W * (0.28 + 0.44 * i) : W * 0.5 + Math.cos(ang) * rad);
      n.y = papers.length <= 2 ? H * 0.5 : H * 0.5 + Math.sin(ang) * rad;
      n.vx = 0; n.vy = 0;
    });
    shared.forEach((n, i) => {
      n.x = W * 0.5;
      n.y = H * (shared.length === 1 ? 0.5 : (0.24 + 0.52 * (i / (shared.length - 1))));
      n.vx = 0; n.vy = 0;
    });
    leaves.forEach((n, i) => {
      const ang = (i / Math.max(leaves.length, 1)) * Math.PI * 2;
      const rad = Math.min(W, H) * 0.42;
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
          const f = 5800 / d2;
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
        const target = b.deg >= 2 ? 155 : 150;
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
      const box = body.querySelector("#kg-detail");
      if (!box || !n) return;
      const neigh = edges.filter((e) => e.a === n.id || e.b === n.id)
        .map((e) => byId.get(e.a === n.id ? e.b : e.a)).filter(Boolean);
      const items = (n.meta && n.meta.items) || [];
      const rels = (n.meta && n.meta.rels) || [];
      box.innerHTML = `
        <div class="card-title">
          <span>${LL.esc(n.label)}</span>
          <span class="pill accent">${LL.esc(n.type)}</span>
        </div>
        <div class="mono muted" style="font-size:11px;margin-bottom:8px">${LL.esc(n.id)}</div>
        ${n.meta && n.meta.title ? `<div style="margin-bottom:8px">${LL.esc(n.meta.title)}</div>` : ""}
        ${n.type !== "paper" ? `<div style="margin-bottom:8px"><button type="button" class="btn btn-sm" data-jump-term="${LL.esc(n.id)}">Open Term in Vocab ↗</button></div>` : ""}
        <div style="font-weight:700;font-size:12px;margin:8px 0 4px">Connected Nodes (${neigh.length})</div>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:10px">
          ${neigh.map((x) => `<span class="pill">${LL.esc(x.label)}</span>`).join("")}
        </div>
        ${rels.length ? `
          <div style="font-weight:700;font-size:12px;margin:8px 0 4px">GRN Regulatory Edges (${rels.length})</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">
            ${rels.map((rid) => `<button type="button" class="pill info pill-btn mono" data-jump-grn="${LL.esc(rid)}">${LL.esc(rid)} ↗</button>`).join("")}
          </div>` : ""}
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
  }

  // =========================================================================
  // 4. Top-Level Entry Point: 3-Mode GRN & Graph Workbench
  // =========================================================================
  LL.renderGraphView = function (root) {
    const st = LL.state;
    const data = st.data;
    const nGrn = (data.genetic_relations || []).length;
    const nTables = (data.genomic_tables || []).length;
    const nPapers = (data.papers || []).length;

    // Default cleanly to corpus if no GRN edges exist in a release
    if (st.graphTab === "grn" && nGrn === 0) st.graphTab = "corpus";

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Gene Regulatory Networks, Genomic Tables &amp; Corpus Graph</h2>
          <div class="muted" style="margin-top:2px">Inspect anchor-backed developmental GRN edges with evidence-tier provenance, explore supplemental ChIP/DE tables, or browse the entity knowledge graph.</div>
        </div>
        <div class="seg-switch" role="tablist" aria-label="GRN and Graph modes">
          <button type="button" class="seg-btn ${st.graphTab === "grn" ? "active" : ""}" data-graph-tab="grn" role="tab">Regulatory Network (GRN) <span class="pill">${nGrn}</span></button>
          <button type="button" class="seg-btn ${st.graphTab === "tables" ? "active" : ""}" data-graph-tab="tables" role="tab">Genomic Tables <span class="pill">${nTables}</span></button>
          <button type="button" class="seg-btn ${st.graphTab === "corpus" ? "active" : ""}" data-graph-tab="corpus" role="tab">Corpus Knowledge Graph <span class="pill">${nPapers}p</span></button>
        </div>
      </div>
      <div id="grn-graph-body"></div>
    `;

    root.querySelectorAll("[data-graph-tab]").forEach((btn) => {
      btn.onclick = () => {
        st.graphTab = btn.getAttribute("data-graph-tab");
        LL.renderGraphView(root);
      };
    });

    const body = root.querySelector("#grn-graph-body");
    if (st.graphTab === "tables") renderTablesMode(body, data);
    else if (st.graphTab === "corpus") renderCorpusGraphMode(body, data);
    else renderGrnMode(body, data);
  };
})(window.LL);
