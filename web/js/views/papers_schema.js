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
          <div class="card-title">
            <span>Lepidoptera Controlled Vocabulary (${terms.length} terms · field_set 3)</span>
            <button type="button" class="btn btn-sm primary" data-jump-term="" data-jump-field="ALL">Open Explorer →</button>
          </div>
          <div class="muted" style="margin-bottom:8px">Click any field below to explore its hierarchy, definitions, synonyms, and live corpus usage.</div>
          <div class="kv-grid">
            ${Object.entries(byField).sort((a, b) => b[1].length - a[1].length).map(([f, list]) => `
              <button type="button" class="kv-item kv-clickable" data-jump-term="" data-jump-field="${LL.esc(f)}">
                <div class="kv-k">${LL.esc(f.replace(/_/g, " "))}</div>
                <div class="kv-v mono">${list.length} terms →</div>
              </button>`).join("")}
          </div>
        </div>

        <div class="card">
          <div class="card-title">
            <span>SymPy Formula Library (${formulas.length} formulas)</span>
            <button type="button" class="btn btn-sm primary" data-jump-formula="" data-jump-scope="ALL">Open Workbench →</button>
          </div>
          <div class="muted" style="margin-bottom:8px">Click any Lepidoptera physics or statistical audit formula to inspect equations, assumptions, dependencies, and run live calculations.</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">
            <button type="button" class="btn btn-sm" data-jump-formula="" data-jump-scope="lepidoptera">Lepidoptera Physics &amp; Morphometrics (${formulas.filter((f) => f.scope === "lepidoptera").length}) →</button>
            <button type="button" class="btn btn-sm" data-jump-formula="" data-jump-scope="shared">Statistical &amp; Audit Core (${formulas.filter((f) => f.scope !== "lepidoptera").length}) →</button>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px">
            ${formulas.filter((f) => f.scope === "lepidoptera").map((f) => `
              <button type="button" class="kv-item kv-clickable" style="display:flex;justify-content:space-between;align-items:center;gap:8px;text-align:left" data-jump-formula="${LL.esc(f.formula)}" data-jump-scope="lepidoptera">
                <div>
                  <div class="mono" style="font-size:12px;font-weight:700">${LL.esc(f.formula)}</div>
                  <div class="muted" style="font-size:11px">${LL.esc((f.equations || []).join(" · "))}</div>
                </div>
                <span class="pill accent">${LL.esc(f.kind)}</span>
              </button>`).join("")}
          </div>
        </div>
      </div>
    `;
  };
})(window.LL);
