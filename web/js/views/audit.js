/* Full 7-Dimension Within-Paper Claim Audit, SymPy Formula Checks & Source Data Gaps */
window.LL = window.LL || {};

(function (LL) {
  const DIMS = ["direction", "support", "comparison", "scope", "replication", "strength", "presence"];

  function verdictClass(v) {
    if (v === "follows") return "ok";
    if (v === "overstated" || v === "does not follow") return "bad";
    return "warn";
  }

  LL.renderAuditView = function (root) {
    const st = LL.state;
    const data = st.data;
    const claims = data.claims || [];
    const derivs = data.derivations || [];
    const findings = data.findings || [];
    const papers = (data.papers || []).map((p) => p.paper);

    const filtered = claims.filter((c) => {
      if (st.auditPaper !== "ALL" && c.paper !== st.auditPaper) return false;
      if (st.auditVerdict !== "ALL" && c.verdict !== st.auditVerdict) return false;
      return true;
    });

    const vCounts = claims.reduce((acc, c) => { acc[c.verdict] = (acc[c.verdict] || 0) + 1; return acc; }, {});

    root.innerHTML = `
      <div class="epistemic-banner">
        <strong>Within-Paper Epistemic Audit (Full 7-Dimension Depth):</strong>
        Every major claim across Abstract, Highlights, Results conclusions, Discussion, and Figure Titles is evaluated strictly against the paper's own empirical evidence across all 7 dimensions (<code>direction</code>, <code>support</code>, <code>comparison</code>, <code>scope</code>, <code>replication</code>, <code>strength</code>, <code>presence</code>). Claims never enter cross-paper comparisons.
      </div>

      <div class="toolbar">
        <select id="au-paper" aria-label="Filter claims by paper">
          <option value="ALL">All papers (${claims.length} claims)</option>
          ${papers.map((p) => `<option value="${LL.esc(p)}" ${st.auditPaper === p ? "selected" : ""}>${LL.esc(p)}</option>`).join("")}
        </select>
        <select id="au-verdict" aria-label="Filter claims by verdict">
          <option value="ALL">All verdicts</option>
          ${["overstated", "follows", "cannot judge", "does not follow"].map((v) =>
            `<option value="${v}" ${st.auditVerdict === v ? "selected" : ""}>${v} (${vCounts[v] || 0})</option>`
          ).join("")}
        </select>
        <div style="margin-left:auto;display:flex;gap:6px;flex-wrap:wrap">
          <span class="pill bad">Overstated: ${vCounts.overstated || 0}</span>
          <span class="pill ok">Follows: ${vCounts.follows || 0}</span>
          <span class="pill warn">Cannot judge: ${vCounts["cannot judge"] || 0}</span>
        </div>
      </div>

      <div class="card" style="margin-bottom:16px;overflow-x:auto">
        <div class="card-title">Within-Paper Claim Verdicts (${filtered.length})</div>
        <table class="data-table">
          <thead>
            <tr>
              <th style="width:155px">Paper &amp; Claim</th>
              <th>Verbatim Claim Quote &amp; Scope</th>
              <th style="width:310px">7-Dimension Audit Matrix</th>
              <th style="width:200px">Rests On (Evidence)</th>
            </tr>
          </thead>
          <tbody>
            ${filtered.map((c) => {
              const j = c.judgement || {};
              const dimHtml = DIMS.map((d) => {
                const val = j[d] || "—";
                return `<span class="pill ${verdictClass(val)}" title="${d}: ${val}">${d}: ${LL.esc(val)}</span>`;
              }).join("");
              const rests = (c.rests_on || []).map((iid) =>
                `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(c.paper)}/${LL.esc(iid)}">${LL.esc(iid)}</button>`
              ).join(" ");
              return `
                <tr>
                  <td>
                    <div class="mono" style="font-weight:700;font-size:11.5px">${LL.esc(c.paper)}</div>
                    <div class="mono muted" style="font-size:11px;margin:2px 0 5px">${LL.esc(c.claim)}</div>
                    <span class="pill ${verdictClass(c.verdict)}">${LL.esc(c.verdict)}</span>
                  </td>
                  <td>
                    <div style="font-family:var(--font-serif);font-size:13px">“${LL.esc(c.quote)}”</div>
                    <div class="muted" style="margin-top:4px"><strong>Scope:</strong> ${LL.esc(c.scope)}</div>
                  </td>
                  <td><div class="dim-strip">${dimHtml}</div></td>
                  <td><div style="display:flex;flex-wrap:wrap;gap:4px">${rests || '<span class="muted">none</span>'}</div></td>
                </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>

      <div class="vault-pair">
        <div class="card">
          <div class="card-title">SymPy Formula Derivations (${derivs.length})</div>
          ${derivs.length ? `
            <table class="data-table">
              <thead><tr><th>Paper / Derivation</th><th>Formula</th><th>Verdict</th></tr></thead>
              <tbody>
                ${derivs.map((d) => `
                  <tr>
                    <td>
                      <div class="mono" style="font-weight:700">${LL.esc(d.paper)}/${LL.esc(d.derivation)}</div>
                      <button type="button" class="pill accent pill-btn mono" style="margin-top:3px" data-open-item="${LL.esc(d.paper)}/${LL.esc(d.item)}">${LL.esc(d.item)}</button>
                    </td>
                    <td class="mono" style="font-size:11.5px">${LL.esc(d.formula)}<div class="muted">lib: ${LL.esc(d.library)}</div></td>
                    <td><span class="pill ${d.verdict === "consistent" ? "ok" : "warn"}">${LL.esc(d.verdict)}</span></td>
                  </tr>`).join("")}
              </tbody>
            </table>` : `<div class="muted">No formula derivations in this filter.</div>`}
        </div>

        <div class="card">
          <div class="card-title">Automated Numerical Findings &amp; Data Gaps (${findings.length})</div>
          ${findings.length ? findings.map((f) => `
            <div class="kv-item" style="margin-bottom:7px">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px">
                <span class="mono" style="font-weight:700">${LL.esc(f.paper)} · ${LL.esc(f.check)}</span>
                <span class="pill ${f.verdict === "inconsistent" ? "bad" : "warn"}">${LL.esc(f.verdict)}</span>
              </div>
              <div class="muted" style="margin-top:3px">${LL.esc(f.example || f.unit)}</div>
            </div>`).join("") : `<div class="muted">Zero automated inconsistencies flagged.</div>`}
          <div style="margin-top:10px">
            <div style="font-weight:700;font-size:12px;margin-bottom:5px">Missing Source Data / Supplements</div>
            ${(data.missing_supplements || []).map((m) => `
              <div class="kv-item" style="margin-bottom:5px">
                <div class="mono" style="font-weight:700">${LL.esc(m.paper)}</div>
                <div class="muted">${LL.esc((m.missing || []).join("; "))}</div>
              </div>`).join("")}
          </div>
        </div>
      </div>
    `;

    document.getElementById("au-paper").onchange = (e) => { st.auditPaper = e.target.value; LL.renderAuditView(root); };
    document.getElementById("au-verdict").onchange = (e) => { st.auditVerdict = e.target.value; LL.renderAuditView(root); };
  };
})(window.LL);
