/* Streamlined Within-Paper Audit: Segmented Claims / SymPy & Findings / Data Gaps + Compact 7-Dim Matrix */
window.LL = window.LL || {};

(function (LL) {
  const DIMS = [
    ["direction", "DIR", "Effect direction matches evidence"],
    ["support", "SUP", "Supported by reported data"],
    ["comparison", "CMP", "Contrast matches what was tested"],
    ["scope", "SCP", "Generalization stays within sampled taxa/conditions"],
    ["replication", "REP", "Sample size & replication match claim strength"],
    ["strength", "STR", "Causal vs. correlative wording matches design"],
    ["presence", "PRS", "Cited figure/table data is actually present"],
  ];

  function verdictClass(v) {
    if (v === "follows") return "ok";
    if (v === "overstated" || v === "does not follow") return "bad";
    return "warn";
  }

  function renderClaimsPanel(body, data) {
    const st = LL.state;
    const claims = data.claims || [];
    const papers = (data.papers || []).map((p) => p.paper);

    const paperClaims = claims.filter((c) => st.auditPaper === "ALL" || c.paper === st.auditPaper);
    const vCounts = paperClaims.reduce((acc, c) => { acc[c.verdict] = (acc[c.verdict] || 0) + 1; return acc; }, {});
    const filtered = paperClaims.filter((c) => st.auditVerdict === "ALL" || c.verdict === st.auditVerdict);

    body.innerHTML = `
      <div class="toolbar">
        <select id="au-paper" aria-label="Filter claims by paper">
          <option value="ALL">All papers (${claims.length} claims)</option>
          ${papers.map((p) => `<option value="${LL.esc(p)}" ${st.auditPaper === p ? "selected" : ""}>${LL.esc(p)}</option>`).join("")}
        </select>
        <div style="display:flex;gap:5px;flex-wrap:wrap">
          <button type="button" class="btn btn-sm ${st.auditVerdict === "ALL" ? "active" : ""}" data-au-v="ALL">All (${paperClaims.length})</button>
          <button type="button" class="btn btn-sm ${st.auditVerdict === "overstated" ? "active" : ""}" data-au-v="overstated">Overstated (${vCounts.overstated || 0})</button>
          <button type="button" class="btn btn-sm ${st.auditVerdict === "follows" ? "active" : ""}" data-au-v="follows">Follows (${vCounts.follows || 0})</button>
          <button type="button" class="btn btn-sm ${st.auditVerdict === "cannot judge" ? "active" : ""}" data-au-v="cannot judge">Cannot judge (${vCounts["cannot judge"] || 0})</button>
        </div>
        <span class="muted" style="margin-left:auto;font-size:11.5px">Hover any matrix cell for dimension meaning · Click evidence pills to inspect</span>
      </div>

      <div class="card" style="padding:0;overflow-x:auto">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:160px">Paper &amp; Verdict</th>
              <th>Verbatim Claim Quote &amp; Scope</th>
              <th style="width:270px">7-Dimension Audit Matrix</th>
              <th style="width:205px">Rests On (Evidence)</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map((c) => {
              const j = c.judgement || {};
              const cells = DIMS.map(([key, abbr, desc]) => {
                const val = j[key] || "—";
                const cls = verdictClass(val);
                const sym = val === "follows" ? "✓" : (val === "overstated" || val === "does not follow" ? "!" : "?");
                return `<span class="dim-cell ${cls}" title="${LL.esc(`${key} (${desc}): ${val}`)}"><span class="dim-k">${abbr}</span><span class="dim-s">${sym}</span></span>`;
              }).join("");
              const nonFollow = DIMS.filter(([k]) => j[k] && j[k] !== "follows").map(([k]) => `${k}: ${j[k]}`);
              const rests = (c.rests_on || []).map((iid) =>
                `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(c.paper)}/${LL.esc(iid)}">${LL.esc(iid)}</button>`
              ).join(" ");
              return `
                <tr>
                  <td>
                    <div class="mono" style="font-weight:700;font-size:11.5px">${LL.esc(c.paper)}</div>
                    <div class="mono muted" style="font-size:10.8px;margin:2px 0 5px">${LL.esc(c.claim)}</div>
                    <span class="pill ${verdictClass(c.verdict)}">${LL.esc(c.verdict)}</span>
                  </td>
                  <td>
                    <div style="font-family:var(--font-serif);font-size:13px">“${LL.esc(c.quote)}”</div>
                    <div class="muted" style="margin-top:4px;font-size:12px"><strong>Scope:</strong> ${LL.esc(c.scope)}</div>
                  </td>
                  <td>
                    <div class="dim-matrix">${cells}</div>
                    ${nonFollow.length ? `<div class="muted" style="font-size:11px;margin-top:5px">${LL.esc(nonFollow.join(" · "))}</div>` : `<div class="muted" style="font-size:11px;margin-top:5px">All 7 dimensions follow</div>`}
                  </td>
                  <td><div style="display:flex;flex-wrap:wrap;gap:4px">${rests || '<span class="muted">none</span>'}</div></td>
                </tr>`;
            }).join("") || `<tr><td colspan="4" class="muted" style="padding:18px;text-align:center">No claims match this filter.</td></tr>`}
          </tbody>
        </table>
      </div>
    `;

    body.querySelector("#au-paper").onchange = (e) => { st.auditPaper = e.target.value; renderClaimsPanel(body, data); };
    body.querySelectorAll("[data-au-v]").forEach((b) => {
      b.onclick = () => { st.auditVerdict = b.getAttribute("data-au-v"); renderClaimsPanel(body, data); };
    });
  }

  function renderFindingsPanel(body, data) {
    const st = LL.state;
    const derivs = (data.derivations || []).filter((d) => st.auditPaper === "ALL" || d.paper === st.auditPaper);
    const findings = (data.findings || []).filter((f) => st.auditPaper === "ALL" || f.paper === st.auditPaper);
    const papers = (data.papers || []).map((p) => p.paper);

    body.innerHTML = `
      <div class="toolbar">
        <select id="au-paper-f" aria-label="Filter checks by paper">
          <option value="ALL">All papers</option>
          ${papers.map((p) => `<option value="${LL.esc(p)}" ${st.auditPaper === p ? "selected" : ""}>${LL.esc(p)}</option>`).join("")}
        </select>
        <span class="muted" style="margin-left:auto;font-size:12px">Automated SymPy &amp; raw-data checks — preliminary diagnostics, not peer-reviewed critiques</span>
      </div>

      <div class="card" style="margin-bottom:14px">
        <div class="card-title">
          <span>Automated Numerical &amp; Statistical Findings (${findings.length})</span>
          <span class="pill ${findings.length ? "warn" : "ok"}">${findings.length} flagged for human review</span>
        </div>
        ${findings.length ? `
          <div style="display:flex;flex-direction:column;gap:8px">
            ${findings.map((f) => `
              <div class="kv-item">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
                  <span class="mono" style="font-weight:700">${LL.esc(f.paper)} · ${LL.esc(f.check)}</span>
                  <span class="pill ${f.verdict === "inconsistent" ? "bad" : "warn"}">${LL.esc(f.verdict)}</span>
                </div>
                <div style="margin-top:4px">${LL.esc(f.example || f.unit)}</div>
              </div>`).join("")}
          </div>` : `<div class="muted">Zero automated discrepancies flagged in this filter.</div>`}
      </div>

      <div class="card" style="padding:0;overflow-x:auto">
        <div class="card-title" style="padding:12px 14px 4px">
          <span>SymPy Formula Verifications (${derivs.length})</span>
          <button type="button" class="btn btn-sm" data-jump-formula="" data-jump-scope="ALL">Open Formula Library →</button>
        </div>
        ${derivs.length ? `
          <table class="data-table">
            <thead><tr><th>Paper / Check</th><th>Evidence Item</th><th>Equation &amp; Library Match</th><th>Rebuilt Value</th><th>Verdict</th></tr></thead>
            <tbody>
              ${derivs.map((d) => {
                const rb = d.rebuilt || {};
                const rbStr = rb.value != null ? `${LL.fmtNum(rb.value, 3)}${rb.unit ? " " + rb.unit : ""}` : "—";
                return `
                <tr>
                  <td class="mono" style="font-weight:700">${LL.esc(d.paper)}/${LL.esc(d.derivation)}</td>
                  <td><button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(d.paper)}/${LL.esc(d.item)}">${LL.esc(d.item)} ↗</button></td>
                  <td class="mono" style="font-size:11.5px">
                    ${LL.esc(d.formula)}
                    <div style="margin-top:3px;display:flex;gap:5px;flex-wrap:wrap;align-items:center">
                      ${d.library_formula ? `<button type="button" class="pill pill-btn" data-jump-formula="${LL.esc(d.library_formula)}">${LL.esc(d.library_formula)} ↗</button>` : ""}
                      <span class="muted" style="font-size:10.5px">library: ${LL.esc(d.library || "—")}</span>
                    </div>
                  </td>
                  <td class="mono" style="font-size:11.5px">${LL.esc(rbStr)}</td>
                  <td><span class="pill ${d.verdict === "consistent" ? "ok" : "warn"}">${LL.esc(d.verdict)}</span></td>
                </tr>`;
              }).join("")}
            </tbody>
          </table>` : `<div class="muted" style="padding:16px">No formula derivations recorded for this paper filter.</div>`}
      </div>
    `;

    body.querySelector("#au-paper-f").onchange = (e) => { st.auditPaper = e.target.value; renderFindingsPanel(body, data); };
  }

  function renderGapsPanel(body, data) {
    const gaps = data.missing_supplements || [];
    body.innerHTML = `
      <div class="card">
        <div class="card-title">
          <span>Missing Source Data &amp; Unreleased Supplements (${gaps.length} papers)</span>
          <span class="muted">Items referenced in published text or scripts that were omitted from supplemental archives</span>
        </div>
        ${gaps.length ? `
          <div style="display:flex;flex-direction:column;gap:8px">
            ${gaps.map((m) => `
              <div class="kv-item">
                <div class="mono" style="font-weight:700;margin-bottom:3px">${LL.esc(m.paper)}</div>
                <div class="muted">${LL.esc((m.missing || []).join("; "))}</div>
              </div>`).join("")}
          </div>` : `<div class="muted">No missing supplements recorded.</div>`}
      </div>
    `;
  }

  LL.renderAuditView = function (root) {
    const st = LL.state;
    const data = st.data;
    const tab = st.auditTab || "claims";
    const nClaims = (data.claims || []).length;
    const nDeriv = (data.derivations || []).length;
    const nFind = (data.findings || []).length;
    const nGaps = (data.missing_supplements || []).length;

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Within-Paper Epistemic &amp; Numerical Audit</h2>
          <div class="muted" style="margin-top:2px">Author claims are evaluated strictly against each paper's own data across 7 dimensions and never enter cross-paper comparisons.</div>
        </div>
        <div class="seg-switch" role="tablist" aria-label="Audit workspace modes">
          <button type="button" class="seg-btn ${tab === "claims" ? "active" : ""}" data-audit-tab="claims" role="tab">Claim Verdicts <span class="pill">${nClaims}</span></button>
          <button type="button" class="seg-btn ${tab === "findings" ? "active" : ""}" data-audit-tab="findings" role="tab">SymPy &amp; Findings <span class="pill ${nFind ? "warn" : ""}">${nDeriv}·${nFind}</span></button>
          <button type="button" class="seg-btn ${tab === "gaps" ? "active" : ""}" data-audit-tab="gaps" role="tab">Source Data Gaps <span class="pill">${nGaps}</span></button>
        </div>
      </div>
      <div id="audit-body"></div>
    `;

    root.querySelectorAll("[data-audit-tab]").forEach((b) => {
      b.onclick = () => {
        st.auditTab = b.getAttribute("data-audit-tab");
        LL.renderAuditView(root);
      };
    });

    const body = root.querySelector("#audit-body");
    if (tab === "findings") renderFindingsPanel(body, data);
    else if (tab === "gaps") renderGapsPanel(body, data);
    else renderClaimsPanel(body, data);
  };
})(window.LL);
