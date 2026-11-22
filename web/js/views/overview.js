/* Editorial Landing Page: Interactive Workflow Schematic, Core Principles & Curated Entry Points */
window.LL = window.LL || {};

(function (LL) {
  function renderWorkflowSvg(stats, dark) {
    const bg = dark ? "#141b24" : "#ffffff";
    const boxFill = dark ? "#1a2330" : "#faf9f5";
    const boxStroke = dark ? "#314154" : "#d5d0c4";
    const accent = dark ? "#4ab3c9" : "#0f5f73";
    const accentSoft = dark ? "rgba(74,179,201,0.14)" : "#e6f4f7";
    const ok = dark ? "#4ade80" : "#1f7a4c";
    const okSoft = dark ? "rgba(74,222,128,0.12)" : "#e8f6ee";
    const warn = dark ? "#fbbf24" : "#b45309";
    const warnSoft = dark ? "rgba(251,191,36,0.12)" : "#fef3c7";
    const ink = dark ? "#e8edf3" : "#1a222b";
    const muted = dark ? "#94a3b8" : "#52606d";
    const lineCol = dark ? "#475569" : "#94a3b8";

    const stages = [
      {
        num: "01",
        title: "Open-Access Intake",
        sub: "manifest · JATS XML",
        stat: `${stats.nPapers} OA papers`,
        action: `data-jump-view="papers"`,
        x: 16,
      },
      {
        num: "02",
        title: "Atomic Panels",
        sub: "1-letter crops · QA gate",
        stat: `${stats.nPanels} panels · 0 flagged`,
        action: `data-jump-figures-tab="atlas"`,
        x: 204,
      },
      {
        num: "03",
        title: "Plot & FFT Metrology",
        sub: ".py extractors · 2D-FFT",
        stat: `${stats.nPlots} plots · ${stats.nFft} FFT`,
        action: `data-jump-figures-tab="plots"`,
        x: 392,
      },
      {
        num: "04",
        title: "Audit & GRN Layer",
        sub: "7-dim claims · SymPy · GRN",
        stat: `${stats.nClaims} claims · ${stats.nGrn} GRN`,
        action: `data-jump-view="audit"`,
        x: 580,
      },
      {
        num: "05",
        title: "Cross-Paper Synthesis",
        sub: "empirical compare · v4 vocab",
        stat: `${stats.nTerms} terms · ${stats.nFormulas} eqs`,
        action: `data-jump-view="compare"`,
        x: 768,
      },
    ];

    const w = 956, h = 236;
    const bw = 172, bh = 104, by = 22;

    const arrows = stages.slice(0, -1).map((s) => {
      const x1 = s.x + bw + 2;
      const x2 = x1 + 12;
      const cy = by + bh / 2;
      return `<path d="M ${x1} ${cy} L ${x2} ${cy}" stroke="${lineCol}" stroke-width="1.8" marker-end="url(#ov-arrow)" />`;
    }).join("");

    const boxes = stages.map((s) => `
      <g class="ov-stage-node" ${s.action} style="cursor:pointer" role="button" tabindex="0">
        <rect x="${s.x}" y="${by}" width="${bw}" height="${bh}" rx="9" fill="${boxFill}" stroke="${boxStroke}" stroke-width="1.3" />
        <rect x="${s.x + 12}" y="${by + 12}" width="26" height="18" rx="4" fill="${accentSoft}" />
        <text x="${s.x + 25}" y="${by + 24.5}" text-anchor="middle" font-size="10" font-weight="800" font-family="ui-monospace, monospace" fill="${accent}">${s.num}</text>
        <text x="${s.x + bw - 12}" y="${by + 24}" text-anchor="end" font-size="10" font-weight="600" fill="${accent}">Open →</text>
        <text x="${s.x + 12}" y="${by + 51}" font-size="12.5" font-weight="700" fill="${ink}">${LL.esc(s.title)}</text>
        <text x="${s.x + 12}" y="${by + 68}" font-size="10.5" fill="${muted}">${LL.esc(s.sub)}</text>
        <line x1="${s.x + 12}" y1="${by + 79}" x2="${s.x + bw - 12}" y2="${by + 79}" stroke="${boxStroke}" stroke-width="0.8" />
        <text x="${s.x + 12}" y="${by + 94}" font-size="10.2" font-weight="700" font-family="ui-monospace, monospace" fill="${muted}">${LL.esc(s.stat)}</text>
      </g>`).join("");

    // Bottom epistemic firewall lane separating Within-Paper Claims from Cross-Paper Empirical Evidence
    const fy = 150;
    return `
      <svg viewBox="0 0 ${w} ${h}" class="ov-workflow-svg" role="img" aria-label="LivingLit Lepidoptera 5-stage pipeline and epistemic firewall schematic">
        <defs>
          <marker id="ov-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 1 1.5 L 9 5 L 1 8.5 z" fill="${lineCol}" />
          </marker>
          <marker id="ov-arrow-ok" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M 1 1.5 L 9 5 L 1 8.5 z" fill="${ok}" />
          </marker>
        </defs>
        <rect x="0" y="0" width="${w}" height="${h}" rx="10" fill="${bg}" />
        ${arrows}
        ${boxes}

        <!-- Epistemic Firewall Row -->
        <rect x="16" y="${fy}" width="546" height="68" rx="9" fill="${okSoft}" stroke="${ok}" stroke-width="1.1" stroke-opacity="0.45" />
        <text x="30" y="${fy + 22}" font-size="10.5" font-weight="800" letter-spacing="0.05em" fill="${ok}">ANCHORED EMPIRICAL EVIDENCE + DIGITIZED DATA</text>
        <text x="30" y="${fy + 40}" font-size="11.2" fill="${ink}">Raw tables, digitized curves (${stats.nPts.toLocaleString()} pts), calibrated FFT readings &amp; assay-backed GRN edges</text>
        <text x="30" y="${fy + 56}" font-size="10.5" fill="${muted}">Flows across papers into Compare, True-Scale Micrographs, GRN Workbench &amp; Knowledge Graph</text>

        <line x1="571" y1="${fy + 6}" x2="571" y2="${fy + 62}" stroke="${warn}" stroke-width="2" stroke-dasharray="4 3" opacity="0.6" />

        <rect x="580" y="${fy}" width="360" height="68" rx="9" fill="${warnSoft}" stroke="${warn}" stroke-width="1.1" stroke-opacity="0.55" />
        <text x="594" y="${fy + 22}" font-size="10.5" font-weight="800" letter-spacing="0.05em" fill="${warn}">EPISTEMIC FIREWALL · WITHIN-PAPER CLAIMS ONLY</text>
        <text x="594" y="${fy + 40}" font-size="11.2" fill="${ink}">Author conclusions stay quarantined inside Audit</text>
        <text x="594" y="${fy + 56}" font-size="10.5" fill="${muted}">7-dimension &amp; SymPy checks; never mixed across papers</text>

        <!-- Vertical connectors tying stage 3/4/5 to bottom epistemic lanes -->
        <line x1="478" y1="${by + bh}" x2="478" y2="${fy - 2}" stroke="${ok}" stroke-width="1.4" stroke-dasharray="3 3" marker-end="url(#ov-arrow-ok)" />
        <line x1="666" y1="${by + bh}" x2="666" y2="${fy - 2}" stroke="${warn}" stroke-width="1.4" stroke-dasharray="3 3" />
        <line x1="854" y1="${fy}" x2="854" y2="${by + bh + 4}" stroke="${ok}" stroke-width="1.4" stroke-dasharray="3 3" />
      </svg>`;
  }

  LL.renderOverviewView = function (root) {
    const data = LL.state.data || {};
    const panels = data.panels || [];
    const stats = {
      nPapers: (data.papers || []).length,
      nPanels: panels.length,
      nPlots: panels.filter(LL.panelHasPlot).length,
      nFft: panels.filter(LL.panelHasFft).length,
      nPts: (data.summary && data.summary.n_digitized_series_points) || 0,
      nClaims: (data.claims || []).length,
      nGrn: (data.genetic_relations || []).length,
      nTables: (data.genomic_tables || []).length,
      nTableRows: (data.genomic_tables || []).reduce((s, t) => s + (t.n_rows || 0), 0),
      nTerms: (data.terms || []).length,
      nFormulas: (data.formulas || []).length,
      nExtractors: (data.summary && data.summary.n_custom_extractors) || 0,
    };

    const dark = LL.isDark();

    root.innerHTML = `
      <section class="ov-hero">
        <div class="ov-hero-main">
          <h1 class="ov-title">LivingLit · Lepidoptera</h1>
          <p class="ov-lead">
            An auditable living literature review, developmental gene regulatory network workbench, and calibrated figure atlas for
            <strong>butterflies and moths</strong> — built so every extracted number, digitized curve, microscopy measurement, and regulatory edge can be inspected directly against its original figure and verbatim source text.
          </p>
          <div class="ov-cta-row">
            <button type="button" class="btn primary" data-jump-figures-tab="atlas">Browse Figures &amp; Overlays →</button>
            <button type="button" class="btn" data-jump-view="compare">Compare Measurements</button>
            <button type="button" class="btn" data-jump-view="graph">Explore GRN Workbench</button>
            <button type="button" class="btn" data-jump-view="papers">View 10 OA Papers</button>
          </div>
        </div>
        <dl class="ov-ledger" aria-label="Corpus metrics">
          <div><dt>Open-Access Corpus</dt><dd>${stats.nPapers} papers <span class="muted">(9 butterflies · 1 moth)</span></dd></div>
          <div><dt>Atomic Figure Panels</dt><dd>${stats.nPanels} panels <span class="muted">(${stats.nPlots} plots · ${stats.nFft} FFT)</span></dd></div>
          <div><dt>Extracted Data</dt><dd>${stats.nPts.toLocaleString()} plot pts <span class="muted">· ${stats.nTableRows} table rows</span></dd></div>
          <div><dt>Audit &amp; Genetics</dt><dd>${stats.nClaims} claims <span class="muted">· ${stats.nGrn} GRN edges</span></dd></div>
          <div><dt>Schema &amp; Math</dt><dd>${stats.nTerms} terms <span class="muted">· ${stats.nFormulas} SymPy formulas</span></dd></div>
        </dl>
      </section>

      <section class="card ov-section">
        <div class="ov-section-head">
          <div>
            <h2>Pipeline &amp; Epistemic Architecture</h2>
            <p class="muted">Click any stage below to jump directly into that workspace.</p>
          </div>
          <span class="mono muted" style="font-size:11.5px">Zero external CDNs · Deterministic gate checks · Open-Access only</span>
        </div>
        <div id="ov-workflow-wrap">${renderWorkflowSvg(stats, dark)}</div>
      </section>

      <section class="ov-principles" aria-label="Core principles">
        <div class="ov-principle">
          <div class="ov-p-num mono">01</div>
          <h3>Verbatim &amp; Visual Provenance</h3>
          <p class="muted">Every extracted value links to an exact source quote and raw figure crop. Digitized curves and 2D-FFT ridge gratings draw live on top of the original image alongside the Python script that produced them.</p>
        </div>
        <div class="ov-principle">
          <div class="ov-p-num mono">02</div>
          <h3>Epistemic Firewall</h3>
          <p class="muted">Author claims stay quarantined in <strong>Audit</strong> and are checked only against each paper's own data across 7 dimensions. Cross-paper <strong>Compare</strong> pairs raw empirical measurements only.</p>
        </div>
        <div class="ov-principle">
          <div class="ov-p-num mono">03</div>
          <h3>Researcher Discretion</h3>
          <p class="muted">Instead of hiding cross-species comparisons behind rigid pre-filters, physical unit compatibility is enforced automatically while biological and methodological confounders remain live toggleable controls.</p>
        </div>
        <div class="ov-principle">
          <div class="ov-p-num mono">04</div>
          <h3>Tiered Genetics &amp; Reproducibility</h3>
          <p class="muted">Regulatory edges distinguish direct chromatin binding (ChIP/CUT&amp;Tag), functional perturbation (CRISPR/CK-666), and correlative expression — enforced automatically by schema gates and backed by SymPy checks.</p>
        </div>
      </section>

      <section class="ov-section">
        <div class="ov-section-head" style="margin-bottom:10px">
          <div>
            <h2>Guided Starting Points</h2>
            <p class="muted">Jump straight into four concrete examples across microscopy, plot digitization, evo-devo genetics, and numerical auditing.</p>
          </div>
        </div>
        <div class="ov-examples">
          <button type="button" class="ov-example-card" data-jump-panel="2024_Lloyd/F1/E">
            <div class="ov-ex-kicker mono">Figures · 2D-FFT Metrology</div>
            <div class="ov-ex-title">Phase-aligned SEM ridge grating</div>
            <div class="muted">Inspect calibrated 2D-FFT ridge (0.833 µm) and crossrib (0.501 µm) overlays on <em>Heliconius sara</em>, or drag your own ROI box to measure pitch live in the browser.</div>
          </button>

          <button type="button" class="ov-example-card" data-jump-plot="2020_Stavenga/F5/A">
            <div class="ov-ex-kicker mono">Figures · Digitized Plots</div>
            <div class="ov-ex-title">Bogong moth reflectance vs. thin-film model</div>
            <div class="muted">Compare extracted spectra against the original <em>Agrotis infusa</em> figure crop, inspect the custom Python extractor, and export CSV/JSON directly.</div>
          </button>

          <button type="button" class="ov-example-card" data-jump-grn="ivory_required_for_melanic_heliconius">
            <div class="ov-ex-kicker mono">GRN &amp; Graph · Cross-Paper Hub</div>
            <div class="ov-ex-title"><em>ivory</em> lncRNA across 2 papers &amp; 5 species</div>
            <div class="muted">Trace 33 anchor-backed regulatory edges uniting <em>Colias</em> ChIP/snRNA-seq (<code>2025_Loh</code>) with Nymphalidae CRISPR knockouts (<code>2024_Livraghi</code>).</div>
          </button>

          <button type="button" class="ov-example-card" data-jump-audit-tab="findings">
            <div class="ov-ex-kicker mono">Audit · SymPy &amp; Raw Data Checks</div>
            <div class="ov-ex-title">Automated numerical &amp; variance findings</div>
            <div class="muted">Inspect the preliminary <code>2018_Parnell</code> Table 1 digit transposition (369 vs. 396 nm in raw CSV) and <code>2023_Seah</code> pooled-SD vs. Welch variance sensitivity.</div>
          </button>
        </div>
      </section>
    `;
  };
})(window.LL);
