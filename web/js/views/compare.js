/* Shift #2 Relaxed User-Discretion Cross-Paper Comparison + Interactive Context-Diff Controls + One-Axis Strip */
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

    const measures = [...new Set(comps.map((c) => c.measure))];
    if (st.compareMeasure !== "ALL" && !measures.includes(st.compareMeasure)) st.compareMeasure = "ALL";

    const activeComps = comps.filter((c) => st.compareMeasure === "ALL" || c.measure === st.compareMeasure);

    // Evaluate each comparison pair under current user-chosen strictDims toggles
    const evaluated = activeComps.map((c) => {
      const diff = c.context_diff || { matched: [], differing: {}, confounders: [] };
      const userBlocked = [];
      Object.entries(st.strictDims).forEach(([dim, req]) => {
        if (req && diff.differing && diff.differing[dim]) {
          userBlocked.push(`${dim}: ${diff.differing[dim][0]} ≠ ${diff.differing[dim][1]}`);
        }
      });
      return { comp: c, diff, userBlocked };
    });

    const nAllowed = evaluated.filter((e) => !e.userBlocked.length).length;
    const nBlocked = evaluated.length - nAllowed;

    // Build cross-paper one-axis empirical strip rows for selected (or first) shared measure
    const stripMeasure = st.compareMeasure !== "ALL" ? st.compareMeasure : (measures[0] || null);
    const stripRows = [];
    if (stripMeasure) {
      const seen = new Set();
      values.forEach((v) => {
        if (!v.measure_terms || !v.measure_terms.split("|").includes(stripMeasure)) return;
        if (!["mean", "median", "value"].includes(v.kind)) return;
        const nv = normVal(v);
        if (!nv) return;
        const k = `${v.paper}/${v.item}/${v.group}`;
        if (seen.has(k)) return;
        seen.add(k);
        stripRows.push({
          paper: v.paper,
          item: v.item,
          group: v.group,
          group_label: v.group_label || v.group,
          val: nv.val,
          unit: nv.unit,
          origin: v.origin,
          spreadVal: null,
        });
      });
    }

    const strictFields = [
      ["taxon", "Taxon (species)"],
      ["scale_type", "Scale type (cover/ground)"],
      ["functional_architecture", "Architecture"],
      ["life_stage", "Life stage (adult/pupa)"],
      ["perturbation_modality", "Perturbation"],
      ["imaging_modality", "Imaging modality"],
      ["view_orientation", "View orientation (tilt)"],
      ["hydration_and_prep", "Hydration & prep"],
    ];

    root.innerHTML = `
      <div class="epistemic-banner">
        <strong>Epistemic Firewall (Shift #2 · Relaxed User-Discretion Comparison):</strong>
        Cross-paper comparisons pair <strong>empirical evidence items &amp; values only</strong> (within-paper claims stay strictly inside the <strong>Audit</strong> tab). Physical unit compatibility is enforced automatically; toggle any biological or methodological dimension below between <em>Relaxed</em> and <em>Require match</em>.
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">
          <span>Interactive Researcher Matching Policy</span>
          <div style="display:flex;gap:6px;align-items:center">
            <select id="cmp-measure" aria-label="Filter by shared measure">
              <option value="ALL">All shared measures (${measures.length})</option>
              ${measures.map((m) => `<option value="${LL.esc(m)}" ${st.compareMeasure === m ? "selected" : ""}>${LL.esc(termLabels[m] || m)}</option>`).join("")}
            </select>
            <button type="button" class="btn btn-sm" id="cmp-reset-policy">Relax all</button>
          </div>
        </div>
        <div class="policy-grid">
          ${strictFields.map(([k, lbl]) => {
            const on = !!st.strictDims[k];
            return `
              <label class="policy-chip ${on ? "strict" : ""}" style="cursor:pointer">
                <span>${LL.esc(lbl)}</span>
                <span style="display:inline-flex;align-items:center;gap:5px;font-weight:700;font-size:11px">
                  <input type="checkbox" data-strict-dim="${k}" ${on ? "checked" : ""} />
                  ${on ? "Require match" : "Relaxed"}
                </span>
              </label>`;
          }).join("")}
        </div>
        <div class="muted">Active cross-paper pairs: <strong style="color:var(--ok)">${nAllowed} comparable</strong> · <strong style="color:var(--warn)">${nBlocked} filtered out by your toggles</strong></div>
      </div>

      ${stripRows.length ? `
        <div class="card" style="margin-bottom:14px">
          <div class="card-title">
            <span>Cross-Paper Empirical Value Axis — ${LL.esc(termLabels[stripMeasure] || stripMeasure)} (${stripRows[0].unit})</span>
            <span class="muted">Click any row to open the Result Audit Drawer</span>
          </div>
          <canvas id="cmp-strip-canvas" style="width:100%;display:block"></canvas>
        </div>` : ""}

      <div class="section-head">
        <h2>Pairwise Cross-Paper Comparisons (${evaluated.length})</h2>
        <span class="muted">Green = matched · Amber = differing context · Red = physical confounder warning</span>
      </div>

      ${evaluated.map(({ comp, diff, userBlocked }) => {
        const mLabel = termLabels[comp.measure] || comp.measure;
        const vCls = userBlocked.length ? "warn" : (comp.verdict.startsWith("agree") ? "ok" : (comp.verdict.startsWith("differ") ? "bad" : "info"));
        const matchedPills = (diff.matched || []).map((f) => `<span class="pill ok">✓ ${LL.esc(f.replace(/_/g, " "))}</span>`).join(" ");
        const diffPills = Object.entries(diff.differing || {}).map(([f, pair]) =>
          `<span class="pill warn">≠ ${LL.esc(f.replace(/_/g, " "))}: ${LL.esc(pair[0])} vs ${LL.esc(pair[1])}</span>`
        ).join(" ");
        const confPills = (diff.confounders || []).map((cf) =>
          `<span class="pill bad">⚠ Confounder · ${LL.esc(cf)}</span>`
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
                  ? `<span class="pill warn">Filtered by user policy (${userBlocked.length})</span>`
                  : `<span class="pill ${vCls}">Verdict: ${LL.esc(comp.verdict)}</span>`}
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
      }).join("") || `<div class="card muted">No cross-paper comparisons for this measure filter.</div>`}
    `;

    if (stripRows.length) {
      const c = document.getElementById("cmp-strip-canvas");
      LL.renderCompareStrip(c, stripRows, (row) => LL.openItemDrawer(`${row.paper}/${row.item}`));
    }

    document.getElementById("cmp-measure").onchange = (e) => { st.compareMeasure = e.target.value; LL.renderCompareView(root); };
    document.getElementById("cmp-reset-policy").onclick = () => {
      Object.keys(st.strictDims).forEach((k) => { st.strictDims[k] = false; });
      LL.renderCompareView(root);
    };
    root.querySelectorAll("[data-strict-dim]").forEach((cb) => {
      cb.onchange = () => {
        st.strictDims[cb.getAttribute("data-strict-dim")] = cb.checked;
        LL.renderCompareView(root);
      };
    });
  };
})(window.LL);
