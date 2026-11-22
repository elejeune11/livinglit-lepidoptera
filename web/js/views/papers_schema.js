/* Papers, Open-Access Manifests, QA Scorecards, Author Code Registry & Extensible Lepidoptera Schema */
window.LL = window.LL || {};

(function (LL) {
  LL.renderPapersView = function (root) {
    const data = LL.state.data;
    const papers = data.papers || [];
    const manifests = data.manifests || {};
    const qaReports = data.qa_reports || {};
    const codeReg = data.code_registry || [];
    const formulas = data.formulas || [];
    const terms = data.terms || [];

    const byField = {};
    terms.forEach((t) => {
      (t.fields || []).forEach((f) => {
        byField[f] = byField[f] || [];
        byField[f].push(t);
      });
    });

    root.innerHTML = `
      <div class="section-head">
        <h2>Pilot Corpus — Open-Access Manifests &amp; QA Gate Scorecards</h2>
        <span class="muted">OA-only policy enforced by gate record · Zero copyrighted binaries committed to Git</span>
      </div>

      <div class="vault-pair" style="margin-bottom:16px">
        ${papers.map((p) => {
          const mf = manifests[p.paper] || {};
          const qa = qaReports[p.paper] || {};
          const items = (data.items || []).filter((i) => i.paper === p.paper);
          const claims = (data.claims || []).filter((c) => c.paper === p.paper);
          return `
            <div class="card">
              <div class="card-title">
                <span class="mono">${LL.esc(p.paper)}</span>
                <div style="display:flex;gap:5px;flex-wrap:wrap">
                  <span class="pill ok">${LL.esc(mf.oa_status || "open_access")}</span>
                  <span class="pill info">${LL.esc(mf.license || "OA")}</span>
                  <span class="pill ${qa.flagged_panels && qa.flagged_panels.length ? "bad" : "ok"}">QA: ${(qa.flagged_panels || []).length} flagged</span>
                </div>
              </div>
              <div style="font-weight:700;margin-bottom:4px">${LL.esc(p.title)}</div>
              <div class="muted" style="margin-bottom:10px">${LL.esc(p.lab)} · DOI: <span class="mono">${LL.esc(p.doi)}</span></div>
              <div class="kv-grid">
                <div class="kv-item"><div class="kv-k">Atomic Panels</div><div class="kv-v mono">${qa.n_panels || 0} (${qa.composite_panels || 0} composites)</div></div>
                <div class="kv-item"><div class="kv-k">Custom .py Extractors</div><div class="kv-v mono">${qa.n_custom_extractors || 0}</div></div>
                <div class="kv-item"><div class="kv-k">Calibrated FFT Panels</div><div class="kv-v mono">${qa.n_fft_panels || 0}</div></div>
                <div class="kv-item"><div class="kv-k">Evidence / Claims</div><div class="kv-v mono">${items.length} items · ${claims.length} claims</div></div>
              </div>
              ${(mf.repositories || []).length ? `
                <div style="margin-top:10px">
                  <div style="font-size:11.5px;font-weight:700;margin-bottom:4px">External Repositories</div>
                  ${mf.repositories.map((r) => `<div class="muted" style="margin-bottom:3px"><strong>${LL.esc(r.kind)}</strong>: ${LL.esc(r.note || r.url)}</div>`).join("")}
                </div>` : ""}
            </div>`;
        }).join("")}
      </div>

      ${codeReg.length ? `
        <div class="card" style="margin-bottom:16px;overflow-x:auto">
          <div class="card-title">Indexed Author Statistical Scripts (${codeReg.length})</div>
          <table class="data-table">
            <thead><tr><th>Paper</th><th>Script</th><th>Packages</th><th>Referenced Inputs</th><th>Recovered Panels</th></tr></thead>
            <tbody>
              ${codeReg.map((r) => `
                <tr>
                  <td class="mono">${LL.esc(r.paper)}</td>
                  <td class="mono" style="font-weight:600">${LL.esc(r.script)} <span class="muted">(${r.lines} ln)</span></td>
                  <td>${(r.packages || []).map((k) => `<span class="pill">${LL.esc(k)}</span>`).join(" ")}</td>
                  <td class="mono muted" style="font-size:11px">${LL.esc((r.referenced_inputs || []).join(", ") || "—")} ${r.inputs_in_repo ? "" : '<span class="pill warn">omitted by authors</span>'}</td>
                  <td class="mono">${LL.esc((r.recovered_by_digitizer || []).join(", "))}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>` : ""}

      <div class="vault-pair">
        <div class="card">
          <div class="card-title">Lepidoptera Controlled Vocabulary (${terms.length} terms · field_set 3)</div>
          <div class="muted" style="margin-bottom:8px">Covers butterflies (Papilionoidea) &amp; moths (Bombycoidea, Noctuoidea, Geometroidea, Pyraloidea) with extensible optical, acoustic, thermal, and mechanical architectures.</div>
          <div class="kv-grid">
            ${Object.entries(byField).sort((a, b) => b[1].length - a[1].length).map(([f, list]) => `
              <div class="kv-item">
                <div class="kv-k">${LL.esc(f.replace(/_/g, " "))}</div>
                <div class="kv-v mono">${list.length} terms</div>
              </div>`).join("")}
          </div>
        </div>

        <div class="card" style="max-height:360px;overflow-y:auto">
          <div class="card-title">Domain &amp; Statistical Formula Library (${formulas.length} SymPy formulas)</div>
          <table class="data-table">
            <thead><tr><th>Formula</th><th>Kind</th><th>Statement</th></tr></thead>
            <tbody>
              ${formulas.filter((f) => f.kind === "domain" || f.formula.includes("interference") || f.formula.includes("ridge") || f.formula.includes("acoustic") || f.formula.includes("saxs") || f.formula.includes("buckling")).concat(
                formulas.filter((f) => !(f.kind === "domain" || f.formula.includes("interference") || f.formula.includes("ridge") || f.formula.includes("acoustic") || f.formula.includes("saxs") || f.formula.includes("buckling"))).slice(0, 8)
              ).map((f) => `
                <tr>
                  <td class="mono" style="font-weight:600">${LL.esc(f.formula)}</td>
                  <td><span class="pill">${LL.esc(f.kind)}</span></td>
                  <td class="muted">${LL.esc(f.statement)}</td>
                </tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  };
})(window.LL);
