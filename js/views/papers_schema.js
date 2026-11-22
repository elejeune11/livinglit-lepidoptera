/* Streamlined Papers Directory: Open-Access Manifests, QA Scorecards, Direct Workspace Jumps & Author Scripts */
window.LL = window.LL || {};

(function (LL) {
  LL.renderPapersView = function (root) {
    const data = LL.state.data;
    const papers = data.papers || [];
    const manifests = data.manifests || {};
    const qaReports = data.qa_reports || {};
    const codeReg = data.code_registry || [];

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Open-Access Corpus (${papers.length} Papers)</h2>
          <div class="muted" style="margin-top:2px">Every ingested paper carries a verified Open-Access license, automated QA gate scorecard, and direct links into Figures, Audit, and GRN views.</div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <button type="button" class="btn btn-sm" data-jump-term="" data-jump-field="ALL">Vocab (${(data.terms || []).length}) →</button>
          <button type="button" class="btn btn-sm" data-jump-formula="" data-jump-scope="ALL">Formulas (${(data.formulas || []).length}) →</button>
        </div>
      </div>

      <div class="vault-pair" style="margin-bottom:16px">
        ${papers.map((p) => {
          const mf = manifests[p.paper] || {};
          const qa = qaReports[p.paper] || {};
          const paperPanels = (data.panels || []).filter((x) => x.paper === p.paper);
          const nPanels = qa.total_panels != null ? qa.total_panels : paperPanels.length;
          const nFft = qa.n_fft_panels != null ? qa.n_fft_panels : paperPanels.filter(LL.panelHasFft).length;
          const nPlots = paperPanels.filter(LL.panelHasPlot).length;
          const items = (data.items || []).filter((i) => i.paper === p.paper);
          const claims = (data.claims || []).filter((c) => c.paper === p.paper);
          const grnCnt = (data.genetic_relations || []).filter((r) => r.paper === p.paper).length;
          return `
            <div class="card paper-card">
              <div class="card-title">
                <span class="mono" style="font-size:13.5px">${LL.esc(p.paper)}</span>
                <div style="display:flex;gap:5px;flex-wrap:wrap">
                  <span class="pill info">${LL.esc(mf.license || "OA")}</span>
                  ${grnCnt ? `<span class="pill accent">${grnCnt} GRN</span>` : ""}
                  <span class="pill ${qa.flagged_panels && qa.flagged_panels.length ? "bad" : "ok"}">QA: ${(qa.flagged_panels || []).length} flagged</span>
                </div>
              </div>
              <div style="font-weight:700;margin-bottom:3px;line-height:1.35">${LL.esc(p.title)}</div>
              <div class="muted" style="margin-bottom:10px;font-size:12px">${LL.esc(p.lab)} · DOI: <span class="mono">${LL.esc(p.doi)}</span></div>

              <div class="paper-kpi-row">
                <div class="kv-item"><div class="kv-k">Panels</div><div class="kv-v mono">${nPanels}</div></div>
                <div class="kv-item"><div class="kv-k">Plots / .py</div><div class="kv-v mono">${nPlots} / ${qa.n_custom_extractors || 0}</div></div>
                <div class="kv-item"><div class="kv-k">FFT</div><div class="kv-v mono">${nFft}</div></div>
                <div class="kv-item"><div class="kv-k">Items / Claims</div><div class="kv-v mono">${items.length} / ${claims.length}</div></div>
              </div>

              ${(mf.repositories || []).length ? `
                <div class="muted" style="margin-top:9px;font-size:11.8px;line-height:1.4">
                  ${mf.repositories.map((r) => `<div><strong>${LL.esc(r.kind)}:</strong> ${LL.esc(r.note || r.url)}</div>`).join("")}
                </div>` : ""}

              <div class="paper-actions">
                <button type="button" class="btn btn-sm" data-jump-paper-atlas="${LL.esc(p.paper)}">Atlas (${nPanels}) →</button>
                ${nPlots ? `<button type="button" class="btn btn-sm" data-jump-paper-plots="${LL.esc(p.paper)}">Plots (${nPlots}) →</button>` : ""}
                <button type="button" class="btn btn-sm" data-jump-paper-audit="${LL.esc(p.paper)}">Audit (${claims.length}) →</button>
                ${grnCnt ? `<button type="button" class="btn btn-sm" data-jump-paper-grn="${LL.esc(p.paper)}">GRN (${grnCnt}) →</button>` : ""}
              </div>
            </div>`;
        }).join("")}
      </div>

      ${codeReg.length ? `
        <details class="card" style="overflow-x:auto">
          <summary class="card-title" style="cursor:pointer;margin:0">
            <span>Indexed Author Analysis Scripts (${codeReg.length} scripts harvested from public supplements)</span>
            <span class="muted" style="font-size:11.5px;font-weight:500">Click to expand</span>
          </summary>
          <div style="margin-top:12px">
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
          </div>
        </details>` : ""}
    `;
  };
})(window.LL);
