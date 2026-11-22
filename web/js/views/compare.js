/* Streamlined Cross-Paper Empirical Comparison: Measure-First, Clean Context Toggles, Deduplicated Strip & Pagination */
window.LL = window.LL || {};

(function (LL) {
  const UNIT_SCALE = {
    "nm": ["µm", 1e-3], "µm": ["µm", 1], "μm": ["µm", 1], "um": ["µm", 1],
    "µm²": ["µm²", 1], "μm²": ["µm²", 1], "µm2": ["µm²", 1],
    "1/µm": ["1/µm", 1], "µm⁻¹": ["1/µm", 1],
  };

  function normVal(v) {
    const raw = parseFloat(v.value);
    if (Number.isNaN(raw)) return null;
    const u = (v.unit_of_value || "").trim();
    const sc = UNIT_SCALE[u] || [u, 1];
    return { val: raw * sc[1], unit: sc[0] };
  }

  LL.renderCompareView = function (root) {
    const st = LL.state;
    const data = st.data;
    const comps = data.comparisons || [];
    const values = data.values || [];
    const termLabels = data.term_labels || {};

    // Sort measures by number of cross-paper pairs descending so the richest shared measure comes first
    const mCounts = {};
    comps.forEach((c) => { mCounts[c.measure] = (mCounts[c.measure] || 0) + 1; });
    const measures = Object.keys(mCounts).sort((a, b) => mCounts[b] - mCounts[a]);

    // Default to ridge_spacing (or top shared measure) rather than dumping 1,000+ mixed cards at once
    if (!st.compareMeasure || (st.compareMeasure !== "ALL" && !measures.includes(st.compareMeasure))) {
      st.compareMeasure = measures.includes("measure:ridge_spacing") ? "measure:ridge_spacing" : (measures[0] || "ALL");
    }

    const activeComps = comps.filter((c) => st.compareMeasure === "ALL" || c.measure === st.compareMeasure);
    const q = (st.compareQuery || "").trim().toLowerCase();

    const evaluatedAll = activeComps.map((c) => {
      const diff = c.context_diff || { matched: [], differing: {}, confounders: [] };
      const userBlocked = [];
      Object.entries(st.strictDims).forEach(([dim, req]) => {
        if (req && diff.differing && diff.differing[dim]) {
          userBlocked.push(`${dim}: ${diff.differing[dim][0]} ≠ ${diff.differing[dim][1]}`);
        }
      });
      return { comp: c, diff, userBlocked };
    });

    const nAllowed = evaluatedAll.filter((e) => !e.userBlocked.length).length;
    const nBlocked = evaluatedAll.length - nAllowed;

    const evaluated = evaluatedAll.filter(({ comp, diff, userBlocked }) => {
      if (st.compareHideBlocked && userBlocked.length) return false;
      if (st.compareOnlyConf && !(diff.confounders && diff.confounders.length)) return false;
      if (q) {
        const hay = `${comp.a} ${comp.b} ${comp.a_unit} ${comp.b_unit} ${comp.verdict} ${JSON.stringify(diff.differing || {})}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const limit = st.compareLimit || 20;
    const shown = evaluated.slice(0, limit);

    // Build deduplicated, sorted one-axis empirical value strip
    const stripMeasure = st.compareMeasure !== "ALL" ? st.compareMeasure : (measures[0] || null);
    const stripRows = [];
    if (stripMeasure) {
      const seen = new Set();
      values.forEach((v) => {
        if (!v.measure_terms || !v.measure_terms.split("|").includes(stripMeasure)) return;
        if (!["mean", "median", "value"].includes(v.kind)) return;
        const nv = normVal(v);
        if (!nv) return;
        const gl = v.group_label || v.group;
        const dedupKey = `${v.paper}|${gl}|${nv.val.toFixed(4)}|${nv.unit}`;
        if (seen.has(dedupKey)) return;
        seen.add(dedupKey);
        stripRows.push({
          paper: v.paper,
          item: v.item,
          group: v.group,
          group_label: gl,
          val: nv.val,
          unit: nv.unit,
          origin: v.origin,
          spreadVal: null,
        });
      });
      stripRows.sort((a, b) => a.val - b.val);
    }

    const strictFields = [
      ["taxon", "Taxon (species)"],
      ["scale_type", "Scale type"],
      ["functional_architecture", "Architecture"],
      ["life_stage", "Life stage"],
      ["perturbation_modality", "Perturbation"],
      ["imaging_modality", "Imaging modality"],
      ["view_orientation", "View tilt"],
      ["hydration_and_prep", "Hydration & prep"],
    ];

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Cross-Paper Empirical Comparison</h2>
          <div class="muted" style="margin-top:2px">Pairs empirical measurements only (author claims remain in <strong>Audit</strong>). Unit compatibility is enforced automatically; require exact context matches below as needed.</div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
          <select id="cmp-measure" aria-label="Filter by shared measure">
            ${measures.map((m) => `<option value="${LL.esc(m)}" ${st.compareMeasure === m ? "selected" : ""}>${LL.esc(termLabels[m] || m)} (${mCounts[m]} pairs)</option>`).join("")}
            <option value="ALL" ${st.compareMeasure === "ALL" ? "selected" : ""}>All shared measures (${comps.length} pairs)</option>
          </select>
          <button type="button" class="btn btn-sm" id="cmp-reset-policy">Relax all</button>
        </div>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px">
          <span style="font-weight:700;font-size:12.5px">Matching Policy (check any dimension to require an exact match)</span>
          <span class="muted" style="font-size:12px"><strong style="color:var(--ok)">${nAllowed} comparable</strong> · <strong style="color:var(--warn)">${nBlocked} filtered out</strong></span>
        </div>
        <div class="policy-grid" style="margin-bottom:0">
          ${strictFields.map(([k, lbl]) => {
            const on = !!st.strictDims[k];
            return `
              <label class="policy-chip ${on ? "strict" : ""}" style="cursor:pointer">
                <span>${LL.esc(lbl)}</span>
                <span style="display:inline-flex;align-items:center;gap:5px;font-weight:700;font-size:11px">
                  <input type="checkbox" data-strict-dim="${k}" ${on ? "checked" : ""} />
                  ${on ? "Match" : "Relaxed"}
                </span>
              </label>`;
          }).join("")}
        </div>
      </div>

      ${stripRows.length ? `
        <div class="card" style="margin-bottom:14px">
          <div class="card-title">
            <span>Empirical Value Axis — ${LL.esc(termLabels[stripMeasure] || stripMeasure)} (${LL.esc(stripRows[0].unit)} · ${stripRows.length} unique readings, sorted low → high)</span>
            <span class="muted">Click any dot/row to open Result Audit Drawer</span>
          </div>
          <div style="max-height:360px;overflow-y:auto;border:1px solid var(--border);border-radius:var(--radius-sm)">
            <canvas id="cmp-strip-canvas" style="width:100%;display:block"></canvas>
          </div>
        </div>` : ""}

      <div class="toolbar">
        <span style="font-weight:700;font-size:12.5px">Pairwise Comparisons (${evaluated.length})</span>
        <input type="search" id="cmp-q" placeholder="Filter by paper, species, or item…" value="${LL.esc(st.compareQuery || "")}" style="max-width:260px" />
        <label class="chk"><input type="checkbox" id="cmp-hide-blk" ${st.compareHideBlocked ? "checked" : ""} /> Hide filtered-out</label>
        <label class="chk"><input type="checkbox" id="cmp-only-conf" ${st.compareOnlyConf ? "checked" : ""} /> Confounder warnings only</label>
        <span class="muted" style="margin-left:auto;font-size:11.5px">Green = matched · Amber = differing · Red = confounder</span>
      </div>

      ${shown.map(({ comp, diff, userBlocked }) => {
        const mLabel = termLabels[comp.measure] || comp.measure;
        const vCls = userBlocked.length ? "warn" : (comp.verdict.startsWith("agree") ? "ok" : (comp.verdict.startsWith("differ") ? "bad" : "info"));
        const matchedPills = (diff.matched || []).map((f) => `<span class="pill ok">✓ ${LL.esc(f.replace(/_/g, " "))}</span>`).join(" ");
        const diffPills = Object.entries(diff.differing || {}).map(([f, pair]) =>
          `<span class="pill warn">≠ ${LL.esc(f.replace(/_/g, " "))}: ${LL.esc(pair[0])} vs ${LL.esc(pair[1])}</span>`
        ).join(" ");
        const confPills = (diff.confounders || []).map((cf) =>
          `<span class="pill bad">⚠ ${LL.esc(cf)}</span>`
        ).join(" ");

        return `
          <div class="comp-card ${userBlocked.length ? "blocked" : ""}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
              <div>
                <span class="pill accent">${LL.esc(mLabel)}</span>
                <span class="pill">${LL.esc(comp.part)}</span>
              </div>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                ${userBlocked.length
                  ? `<span class="pill warn">Filtered by policy (${userBlocked.length})</span>`
                  : `<span class="pill ${vCls}">${LL.esc(comp.verdict)}</span>`}
              </div>
            </div>

            <div class="comp-sides">
              <div class="side-box">
                <button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(comp.a)}">${LL.esc(comp.a)}</button>
                <div class="muted" style="margin-top:4px">${LL.esc(comp.a_unit)}</div>
              </div>
              <div class="mono muted" style="font-weight:700">vs</div>
              <div class="side-box">
                <button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(comp.b)}">${LL.esc(comp.b)}</button>
                <div class="muted" style="margin-top:4px">${LL.esc(comp.b_unit)}</div>
              </div>
            </div>

            ${userBlocked.length ? `<div class="muted" style="color:var(--warn);font-size:11.5px;margin-top:4px">Blocked by active toggle: ${LL.esc(userBlocked.join(" · "))}</div>` : ""}
            <div class="diff-row">${confPills} ${diffPills} ${matchedPills}</div>
          </div>`;
      }).join("") || `<div class="card muted">No cross-paper comparisons match these filters.</div>`}

      ${evaluated.length > shown.length ? `
        <div style="display:flex;justify-content:center;gap:8px;margin-top:12px">
          <button type="button" class="btn" id="cmp-more">Show 25 more (${shown.length} of ${evaluated.length} shown)</button>
          <button type="button" class="btn" id="cmp-all">Show all ${evaluated.length}</button>
        </div>` : ""}
    `;

    if (stripRows.length) {
      const c = document.getElementById("cmp-strip-canvas");
      LL.renderCompareStrip(c, stripRows, (row) => LL.openItemDrawer(`${row.paper}/${row.item}`));
    }

    document.getElementById("cmp-measure").onchange = (e) => { st.compareMeasure = e.target.value; st.compareLimit = 20; LL.renderCompareView(root); };
    document.getElementById("cmp-reset-policy").onclick = () => {
      Object.keys(st.strictDims).forEach((k) => { st.strictDims[k] = false; });
      LL.renderCompareView(root);
    };
    document.getElementById("cmp-q").oninput = (e) => { st.compareQuery = e.target.value; st.compareLimit = 20; LL.renderCompareView(root); };
    document.getElementById("cmp-hide-blk").onchange = (e) => { st.compareHideBlocked = e.target.checked; LL.renderCompareView(root); };
    document.getElementById("cmp-only-conf").onchange = (e) => { st.compareOnlyConf = e.target.checked; LL.renderCompareView(root); };
    const bMore = document.getElementById("cmp-more");
    if (bMore) bMore.onclick = () => { st.compareLimit = (st.compareLimit || 20) + 25; LL.renderCompareView(root); };
    const bAll = document.getElementById("cmp-all");
    if (bAll) bAll.onclick = () => { st.compareLimit = evaluated.length; LL.renderCompareView(root); };

    root.querySelectorAll("[data-strict-dim]").forEach((cb) => {
      cb.onchange = () => {
        st.strictDims[cb.getAttribute("data-strict-dim")] = cb.checked;
        LL.renderCompareView(root);
      };
    });
  };
})(window.LL);
