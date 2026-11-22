/* Interactive Controlled Vocabulary Explorer & SymPy Formula Workbench (Zero-Dependency) */
window.LL = window.LL || {};

(function (LL) {
  // =========================================================================
  // 1. Safe Zero-Eval Math & Statistical Evaluator (covers all 34 formulas)
  // =========================================================================
  function erfApprox(x) {
    const sign = x < 0 ? -1 : 1;
    const ax = Math.abs(x);
    const t = 1 / (1 + 0.3275911 * ax);
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
    return sign * y;
  }

  function normCdf(z) {
    return 0.5 * (1 + erfApprox(z / Math.SQRT2));
  }

  function normP2(z) {
    return Math.max(0, Math.min(1, 1 - erfApprox(Math.abs(z) / Math.SQRT2)));
  }

  function logGamma(z) {
    const p = [
      0.99999999999980993, 676.5203681218851, -1259.1392167224028,
      771.32342877765313, -176.61502916214059, 12.507343278686905,
      -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
    ];
    if (z < 0.5) {
      return Math.log(Math.PI / Math.sin(Math.PI * z)) - logGamma(1 - z);
    }
    const zm = z - 1;
    let x = p[0];
    for (let i = 1; i < p.length; i++) x += p[i] / (zm + i);
    const t = zm + 7.5;
    return 0.5 * Math.log(2 * Math.PI) + (zm + 0.5) * Math.log(t) - t + Math.log(x);
  }

  function betacf(a, b, x) {
    const MAXIT = 200;
    const EPS = 3e-12;
    const FPMIN = 1e-30;
    const qab = a + b, qap = a + 1, qam = a - 1;
    let c = 1;
    let d = 1 - qab * x / qap;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    d = 1 / d;
    let h = d;
    for (let m = 1; m <= MAXIT; m++) {
      const m2 = 2 * m;
      let aa = m * (b - m) * x / ((qam + m2) * (a + m2));
      d = 1 + aa * d;
      if (Math.abs(d) < FPMIN) d = FPMIN;
      c = 1 + aa / c;
      if (Math.abs(c) < FPMIN) c = FPMIN;
      d = 1 / d;
      h *= d * c;
      aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2));
      d = 1 + aa * d;
      if (Math.abs(d) < FPMIN) d = FPMIN;
      c = 1 + aa / c;
      if (Math.abs(c) < FPMIN) c = FPMIN;
      d = 1 / d;
      const del = d * c;
      h *= del;
      if (Math.abs(del - 1) < EPS) break;
    }
    return h;
  }

  function regIncBeta(x, a, b) {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    const bt = Math.exp(logGamma(a + b) - logGamma(a) - logGamma(b) + a * Math.log(x) + b * Math.log(1 - x));
    if (x < (a + 1) / (a + b + 2)) return bt * betacf(a, b, x) / a;
    return 1 - bt * betacf(b, a, 1 - x) / b;
  }

  function tdistP2(t, df) {
    if (!(df > 0)) return NaN;
    const x = df / (df + t * t);
    return regIncBeta(x, df / 2, 0.5);
  }

  function fdistP(F, df1, df2) {
    if (!(df1 > 0 && df2 > 0)) return NaN;
    if (F <= 0) return 1;
    const x = df2 / (df2 + df1 * F);
    return regIncBeta(x, df2 / 2, df1 / 2);
  }

  function chi2P(x, df) {
    if (!(df > 0)) return NaN;
    if (x <= 0) return 1;
    const a = df / 2;
    const z = x / 2;
    const gln = logGamma(a);
    if (z < a + 1) {
      let ap = a, sum = 1 / a, del = sum;
      for (let n = 1; n <= 200; n++) {
        ap += 1;
        del *= z / ap;
        sum += del;
        if (Math.abs(del) < Math.abs(sum) * 1e-12) break;
      }
      return Math.max(0, 1 - sum * Math.exp(-z + a * Math.log(z) - gln));
    }
    let b = z + 1 - a, c = 1 / 1e-30, d = 1 / b, h = d;
    for (let i = 1; i <= 200; i++) {
      const an = -i * (i - a);
      b += 2;
      d = an * d + b;
      if (Math.abs(d) < 1e-30) d = 1e-30;
      c = b + an / c;
      if (Math.abs(c) < 1e-30) c = 1e-30;
      d = 1 / d;
      const del = d * c;
      h *= del;
      if (Math.abs(del - 1) < 1e-12) break;
    }
    return Math.max(0, Math.min(1, Math.exp(-z + a * Math.log(z) - gln) * h));
  }

  function tq975(df) {
    if (!(df > 0)) return NaN;
    let lo = 0, hi = 1;
    while (tdistP2(hi, df) > 0.05 && hi < 1e8) hi *= 2;
    for (let i = 0; i < 64; i++) {
      const mid = 0.5 * (lo + hi);
      if (tdistP2(mid, df) > 0.05) lo = mid;
      else hi = mid;
    }
    return 0.5 * (lo + hi);
  }

  // Studentized range upper-tail p-value via exact 2D midpoint quadrature
  function normRangeCdf(w, k) {
    if (w <= 0) return 0;
    const zMin = -6.5, zMax = 6.5, N = 65;
    const dz = (zMax - zMin) / N;
    const invSqrt2Pi = 1 / Math.sqrt(2 * Math.PI);
    let sum = 0;
    for (let i = 0; i < N; i++) {
      const z = zMin + (i + 0.5) * dz;
      const phi = Math.exp(-0.5 * z * z) * invSqrt2Pi;
      const diff = Math.max(0, normCdf(z + w) - normCdf(z));
      sum += phi * Math.pow(diff, k - 1);
    }
    return Math.max(0, Math.min(1, k * sum * dz));
  }

  function qrangeP(q, k, df) {
    if (!(k >= 2 && df > 0)) return NaN;
    if (q <= 0) return 1;
    if (df > 1000) return Math.max(0, 1 - normRangeCdf(q, k));
    // u = chi / sqrt(df) has density proportional to u^(df-1) * exp(-df*u^2 / 2)
    const halfDf = df / 2;
    const logConst = Math.log(2) + halfDf * Math.log(halfDf) - logGamma(halfDf);
    const uMax = Math.max(2.6, 1 + 6 / Math.sqrt(df));
    const uMin = Math.max(1e-4, 1 - 6 / Math.sqrt(df));
    const M = 60;
    const du = (uMax - uMin) / M;
    let cdf = 0;
    for (let i = 0; i < M; i++) {
      const u = uMin + (i + 0.5) * du;
      const dens = Math.exp(logConst + (df - 1) * Math.log(u) - 0.5 * df * u * u);
      cdf += dens * normRangeCdf(q * u, k);
    }
    return Math.max(0, Math.min(1, 1 - cdf * du));
  }

  const MATH_FUNCS = {
    sqrt: Math.sqrt,
    abs: Math.abs,
    Abs: Math.abs,
    min: Math.min,
    Min: Math.min,
    max: Math.max,
    Max: Math.max,
    cos: Math.cos,
    sin: Math.sin,
    log: Math.log,
    exp: Math.exp,
    norm_p2: normP2,
    tdist_p2: tdistP2,
    fdist_p: fdistP,
    chi2_p: chi2P,
    tq975: tq975,
    qrange_p: qrangeP,
  };

  function tokenizeExpr(expr) {
    const tokens = [];
    let i = 0;
    const s = String(expr || "");
    while (i < s.length) {
      const ch = s[i];
      if (/\s/.test(ch)) { i++; continue; }
      if (ch === "*" && s[i + 1] === "*") { tokens.push({ t: "op", v: "^" }); i += 2; continue; }
      if ("+-*/^(),".includes(ch)) { tokens.push({ t: ch === "(" || ch === ")" || ch === "," ? ch : "op", v: ch }); i++; continue; }
      if (/[0-9.]/.test(ch)) {
        let j = i;
        while (j < s.length && /[0-9.eE]/.test(s[j])) {
          if ((s[j] === "e" || s[j] === "E") && (s[j + 1] === "+" || s[j + 1] === "-")) j += 2;
          else j++;
        }
        tokens.push({ t: "num", v: parseFloat(s.slice(i, j)) });
        i = j;
        continue;
      }
      if (/[A-Za-z_]/.test(ch)) {
        let j = i;
        while (j < s.length && /[A-Za-z0-9_]/.test(s[j])) j++;
        tokens.push({ t: "id", v: s.slice(i, j) });
        i = j;
        continue;
      }
      throw new Error("Unexpected char: " + ch);
    }
    return tokens;
  }

  function evalMathExpr(expr, scope) {
    const toks = tokenizeExpr(expr);
    let pos = 0;
    const peek = () => toks[pos];
    const eat = () => toks[pos++];

    function parseAdd() {
      let left = parseMul();
      while (peek() && peek().t === "op" && (peek().v === "+" || peek().v === "-")) {
        const op = eat().v;
        const right = parseMul();
        left = op === "+" ? left + right : left - right;
      }
      return left;
    }

    function parseMul() {
      let left = parseUnary();
      while (peek() && peek().t === "op" && (peek().v === "*" || peek().v === "/")) {
        const op = eat().v;
        const right = parseUnary();
        left = op === "*" ? left * right : left / right;
      }
      return left;
    }

    function parseUnary() {
      if (peek() && peek().t === "op" && (peek().v === "+" || peek().v === "-")) {
        const op = eat().v;
        const v = parseUnary();
        return op === "-" ? -v : v;
      }
      return parsePow();
    }

    function parsePow() {
      const base = parsePrimary();
      if (peek() && peek().t === "op" && peek().v === "^") {
        eat();
        const exp = parseUnary();
        return Math.pow(base, exp);
      }
      return base;
    }

    function parsePrimary() {
      const tk = peek();
      if (!tk) return NaN;
      if (tk.t === "num") { eat(); return tk.v; }
      if (tk.t === "(") {
        eat();
        const v = parseAdd();
        if (peek() && peek().t === ")") eat();
        return v;
      }
      if (tk.t === "id") {
        eat();
        if (peek() && peek().t === "(") {
          eat();
          const args = [];
          if (peek() && peek().t !== ")") {
            args.push(parseAdd());
            while (peek() && peek().t === ",") { eat(); args.push(parseAdd()); }
          }
          if (peek() && peek().t === ")") eat();
          const fn = MATH_FUNCS[tk.v];
          if (!fn) return NaN;
          return fn.apply(null, args);
        }
        if (tk.v === "pi") return Math.PI;
        if (tk.v === "e") return Math.E;
        return scope[tk.v] !== undefined ? Number(scope[tk.v]) : NaN;
      }
      return NaN;
    }

    return parseAdd();
  }

  function extractEqMeta(formulaObj) {
    const eqs = formulaObj.equations || [];
    const outputs = [];
    const rhsIds = new Set();
    const lhsRatioDenom = new Set();

    eqs.forEach((eq) => {
      const idx = eq.indexOf("=");
      if (idx < 0) return;
      const lhs = eq.slice(0, idx).trim();
      const rhs = eq.slice(idx + 1).trim();
      let outVar = lhs;
      const ratioMatch = lhs.match(/^([A-Za-z_][A-Za-z0-9_]*)\s*\/\s*([A-Za-z_][A-Za-z0-9_]*)$/);
      if (ratioMatch) {
        outVar = ratioMatch[1];
        lhsRatioDenom.add(ratioMatch[2]);
      }
      outputs.push({ lhs, rhs, outVar, denomVar: ratioMatch ? ratioMatch[2] : null });
      tokenizeExpr(rhs).forEach((tk) => {
        if (tk.t === "id" && !MATH_FUNCS[tk.v] && tk.v !== "pi" && tk.v !== "e") {
          rhsIds.add(tk.v);
        }
      });
    });

    const outNames = new Set(outputs.map((o) => o.outVar));
    const inputs = [];
    const seen = new Set();
    const pushIn = (v) => {
      if (!seen.has(v) && !outNames.has(v)) { seen.add(v); inputs.push(v); }
    };
    rhsIds.forEach(pushIn);
    lhsRatioDenom.forEach(pushIn);
    // Include any test-given inputs (e.g. normalized_to_own_control where my = 1 has given mx)
    ((formulaObj.tests && formulaObj.tests[0] && formulaObj.tests[0].given) ? Object.keys(formulaObj.tests[0].given) : []).forEach(pushIn);

    return { outputs, inputs, outNames };
  }

  LL.evalFormulaEntry = function (formulaObj, given) {
    const meta = extractEqMeta(formulaObj);
    const scope = {};
    Object.entries(given || {}).forEach(([k, v]) => {
      if (v !== "" && v !== null && v !== undefined) scope[k] = Number(v);
    });
    const results = {};
    meta.outputs.forEach((o) => {
      try {
        const rhsVal = evalMathExpr(o.rhs, scope);
        if (o.denomVar) {
          const denom = scope[o.denomVar];
          const val = Number.isFinite(denom) ? rhsVal * denom : NaN;
          scope[o.outVar] = val;
          results[o.outVar] = val;
          results[o.lhs] = rhsVal;
        } else {
          scope[o.outVar] = rhsVal;
          results[o.outVar] = rhsVal;
        }
      } catch (_err) {
        results[o.outVar] = NaN;
      }
    });
    return results;
  };

  // =========================================================================
  // 2. Pretty Zero-CDN Mathematical Formatter
  // =========================================================================
  const GREEK_MAP = {
    lam: "λ", theta: "θ", pi: "π", nu: "ν", rho: "ρ",
  };

  function formatVarHtml(sym) {
    if (GREEK_MAP[sym]) return `<i>${GREEK_MAP[sym]}</i>`;
    if (sym === "sp2") return "<i>s</i><sub>p</sub><sup>2</sup>";
    if (sym === "qgh") return "<i>q</i><sub>GH</sub>";
    if (sym.includes("_")) {
      const [base, ...rest] = sym.split("_");
      const b = GREEK_MAP[base] ? GREEK_MAP[base] : LL.esc(base);
      return `<i>${b}</i><sub>${LL.esc(rest.join("_"))}</sub>`;
    }
    const numSub = sym.match(/^([A-Za-z]+)([0-9]+)$/);
    if (numSub && numSub[1].length <= 2) {
      return `<i>${LL.esc(numSub[1])}</i><sub>${LL.esc(numSub[2])}</sub>`;
    }
    return `<i>${LL.esc(sym)}</i>`;
  }

  function formatEquationHtml(eq) {
    let s = LL.esc(String(eq || ""));
    s = s.replace(/\*\*2\b|\^2\b/g, "<sup>2</sup>");
    s = s.replace(/\*\*\(([^)]+)\)|\^\(([^)]+)\)/g, (_m, a, b) => `<sup>${a || b}</sup>`);
    s = s.replace(/\^([A-Za-z0-9_]+)/g, (_m, a) => `<sup>${a}</sup>`);
    s = s.replace(/\bsqrt\(/g, "√(");
    s = s.replace(/\bAbs\(([^()]+)\)/g, "|$1|");
    s = s.replace(/\b(lam|theta|pi|nu|rho)\b/g, (_m, g) => `<i>${GREEK_MAP[g]}</i>`);
    s = s.replace(/\bsp2\b/g, "<i>s</i><sub>p</sub><sup>2</sup>");
    s = s.replace(/\bqgh\b/g, "<i>q</i><sub>GH</sub>");
    s = s.replace(/\b([A-Za-z])_([A-Za-z0-9]+)\b/g, "<i>$1</i><sub>$2</sub>");
    s = s.replace(/\b(stage|d)_(frac|app)\b/g, "<i>$1</i><sub>$2</sub>");
    s = s.replace(/\b(m|n|s|df|a|b|u|v)([12])\b/g, "<i>$1</i><sub>$2</sub>");
    s = s.replace(/\s*\*\s*/g, " · ");
    s = s.replace(/\s-\s/g, " − ");
    return s;
  }

  function copyWithFeedback(btn, text) {
    const done = () => {
      const old = btn.textContent;
      btn.textContent = "Copied ✓";
      setTimeout(() => { btn.textContent = old; }, 1100);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(done);
    } else {
      done();
    }
  }

  const ACRONYMS = {
    fvk: "FvK", sem: "SEM", saxs: "SAXS", anova: "ANOVA", ci95: "95% CI",
    sd: "SD", cv: "CV", chi2: "χ²", def: "Definition", q: "q", t: "t", f: "F",
  };

  function prettyTitle(id) {
    return String(id || "")
      .split("_")
      .map((w, idx) => {
        const low = w.toLowerCase();
        if (ACRONYMS[low]) return ACRONYMS[low];
        if (idx > 0 && (low === "and" || low === "of" || low === "to" || low === "from")) return low;
        return w.charAt(0).toUpperCase() + w.slice(1);
      })
      .join(" ");
  }

  // =========================================================================
  // 3. Controlled Vocabulary Explorer
  // =========================================================================
  function buildVocabIndexes(data) {
    const terms = data.terms || [];
    const byId = new Map();
    const byField = new Map();
    const childrenByParent = new Map();
    const usage = data.term_usage || {};

    terms.forEach((t) => {
      byId.set(t.id, t);
      (t.fields || []).forEach((f) => {
        if (!byField.has(f)) byField.set(f, []);
        byField.get(f).push(t);
      });
      if (t.parent) {
        if (!childrenByParent.has(t.parent)) childrenByParent.set(t.parent, []);
        childrenByParent.get(t.parent).push(t);
      }
    });

    const fieldDecls = new Map((data.field_decls || []).map((d) => [d.name, d]));
    return { terms, byId, byField, childrenByParent, usage, fieldDecls };
  }

  function isTermUsed(tid, usage) {
    const u = usage[tid];
    return !!(u && ((u.papers && u.papers.length) || (u.items && u.items.length) || (u.panels && u.panels.length)));
  }

  function getAncestors(term, byId) {
    const chain = [];
    const seen = new Set([term.id]);
    let cur = term;
    while (cur && cur.parent && !seen.has(cur.parent) && byId.has(cur.parent)) {
      seen.add(cur.parent);
      cur = byId.get(cur.parent);
      chain.unshift(cur);
    }
    return chain;
  }

  function filterTerms(idx, st) {
    const q = (st.vocabQuery || "").trim().toLowerCase();
    const pool = st.vocabField === "ALL" ? idx.terms : (idx.byField.get(st.vocabField) || []);
    return pool.filter((t) => {
      if (st.vocabFilter === "used" && !isTermUsed(t.id, idx.usage)) return false;
      if (st.vocabFilter === "defined" && !t.definition) return false;
      if (st.vocabFilter === "synonyms" && !(t.synonyms && t.synonyms.length)) return false;
      if (!q) return true;
      const u = idx.usage[t.id];
      const stated = u ? (u.stated_examples || []).map((e) => e.stated).join(" ") : "";
      const hay = `${t.id} ${t.label} ${(t.synonyms || []).join(" ")} ${t.definition || ""} ${t.scope || ""} ${stated}`.toLowerCase();
      return hay.includes(q);
    });
  }

  function buildTreeRows(filtered, idx) {
    const visibleIds = new Set(filtered.map((t) => t.id));
    const rows = [];
    const visited = new Set();

    const roots = filtered
      .filter((t) => !t.parent || !visibleIds.has(t.parent))
      .sort((a, b) => a.label.localeCompare(b.label));

    function walk(term, depth) {
      if (visited.has(term.id)) return;
      visited.add(term.id);
      const kids = (idx.childrenByParent.get(term.id) || [])
        .filter((k) => visibleIds.has(k.id))
        .sort((a, b) => a.label.localeCompare(b.label));
      rows.push({ term, depth, childCount: kids.length });
      kids.forEach((k) => walk(k, depth + 1));
    }
    roots.forEach((r) => walk(r, 0));
    filtered.forEach((t) => { if (!visited.has(t.id)) walk(t, 0); });
    return rows;
  }

  function renderVocabListMarkup(filtered, idx, st) {
    if (!filtered.length) {
      return `<div class="card muted" style="text-align:center;padding:24px">No controlled-vocabulary terms match this filter.</div>`;
    }
    const useTree = st.vocabMode === "tree" && !st.vocabQuery.trim() && st.vocabField !== "ALL";
    const rows = useTree
      ? buildTreeRows(filtered, idx)
      : filtered.slice().sort((a, b) => a.label.localeCompare(b.label)).map((term) => ({ term, depth: 0, childCount: (idx.childrenByParent.get(term.id) || []).length }));

    return rows.map(({ term, depth, childCount }) => {
      const u = idx.usage[term.id];
      const nPanels = u ? (u.panels || []).length : 0;
      const nPapers = u ? (u.papers || []).length : 0;
      const nSyn = (term.synonyms || []).length;
      const sel = term.id === st.selectedTermId;
      const indent = depth * 18;
      return `
        <button type="button" class="term-row ${sel ? "selected" : ""}" data-select-term="${LL.esc(term.id)}" style="padding-left:${10 + indent}px">
          <div style="min-width:0">
            <div style="display:flex;align-items:center;gap:5px;flex-wrap:wrap">
              ${depth > 0 ? `<span class="term-tree-branch">└─</span>` : ""}
              <span style="font-weight:700;font-size:12.5px">${LL.esc(term.label)}</span>
              ${st.vocabField === "ALL" && term.fields && term.fields[0] ? `<span class="pill">${LL.esc(term.fields[0].replace(/_/g, " "))}</span>` : ""}
              ${childCount > 0 && useTree ? `<span class="muted mono" style="font-size:10.5px">(${childCount})</span>` : ""}
            </div>
            <div class="mono muted" style="font-size:11px;margin-top:1px">${LL.esc(term.id)}</div>
          </div>
          <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end">
            ${nPapers > 0 ? `<span class="pill ok">${nPapers}p${nPanels > 0 ? ` · ${nPanels} pan` : ""}</span>` : ""}
            ${nSyn > 0 ? `<span class="pill">${nSyn} syn</span>` : ""}
          </div>
        </button>`;
    }).join("");
  }

  function renderTermDetailMarkup(term, idx, data) {
    if (!term) {
      return `<div class="card muted" style="padding:24px">Select a term from the list to inspect its lineage, definition, synonyms, and live corpus references.</div>`;
    }
    const ancestors = getAncestors(term, idx.byId);
    const children = (idx.childrenByParent.get(term.id) || []).slice().sort((a, b) => a.label.localeCompare(b.label));
    const siblings = term.parent
      ? (idx.childrenByParent.get(term.parent) || []).filter((s) => s.id !== term.id).sort((a, b) => a.label.localeCompare(b.label))
      : [];
    const u = idx.usage[term.id] || { papers: [], items: [], panels: [], stated_examples: [] };
    const fieldName = (term.fields && term.fields[0]) || "";
    const decl = idx.fieldDecls.get(fieldName);
    const isMeasure = fieldName === "measure";
    const matchingComps = isMeasure
      ? (data.comparisons || []).filter((c) => c.measure === term.id || c.measure === term.label || c.measure === term.id.split(":")[1])
      : [];

    return `
      <div class="card">
        ${ancestors.length ? `
          <div class="breadcrumb" aria-label="Taxonomy lineage">
            ${ancestors.map((a) => `<button type="button" class="pill pill-btn" data-select-term="${LL.esc(a.id)}">${LL.esc(a.label)}</button><span class="breadcrumb-sep">›</span>`).join("")}
            <span class="pill accent">${LL.esc(term.label)}</span>
          </div>` : ""}

        <div class="card-title" style="align-items:flex-start">
          <div>
            <div style="font-size:17px;font-weight:800;letter-spacing:-0.01em">${LL.esc(term.label)}</div>
            <div class="mono muted" style="font-size:12px;margin-top:2px">${LL.esc(term.id)}</div>
          </div>
          <button type="button" class="btn btn-sm" id="vf-copy-term" data-copy-text="${LL.esc(term.id)}">Copy ID</button>
        </div>

        <div class="chip-row" style="margin-bottom:12px">
          ${(term.fields || []).map((f) => `<span class="pill accent">${LL.esc(f.replace(/_/g, " "))}</span>`).join("")}
          <span class="pill">Source: ${LL.esc(term.source || "LivingLit")}</span>
          ${term.added ? `<span class="pill">Added: ${LL.esc(term.added)}</span>` : ""}
          ${u.papers.length ? `<span class="pill ok">Used in ${u.papers.length} paper${u.papers.length > 1 ? "s" : ""}</span>` : `<span class="pill">Prepared for future ingestion</span>`}
        </div>

        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="kv-item">
            <div class="kv-k">Definition</div>
            <div style="font-size:13px;margin-top:3px;color:var(--ink)">${term.definition ? LL.esc(term.definition) : `<span class="muted">No prose definition entered yet (label &amp; field scope define this term).</span>`}</div>
          </div>

          ${term.scope ? `
            <div class="kv-item">
              <div class="kv-k">Disambiguation &amp; Scope Note</div>
              <div style="font-size:12.5px;margin-top:3px;color:var(--ink)">${LL.esc(term.scope)}</div>
            </div>` : ""}

          ${(term.synonyms || []).length ? `
            <div>
              <div class="kv-k" style="margin-bottom:5px">Accepted Synonyms (${term.synonyms.length})</div>
              <div class="chip-row">
                ${term.synonyms.map((s) => `<span class="pill info">“${LL.esc(s)}”</span>`).join("")}
              </div>
            </div>` : ""}

          ${(term.parent || children.length || siblings.length) ? `
            <div style="display:flex;flex-direction:column;gap:8px;padding-top:6px;border-top:1px solid var(--border)">
              ${term.parent && idx.byId.has(term.parent) ? `
                <div>
                  <div class="kv-k" style="margin-bottom:4px">Parent Term</div>
                  <button type="button" class="pill pill-btn" data-select-term="${LL.esc(term.parent)}">↑ ${LL.esc(idx.byId.get(term.parent).label)} <span class="mono muted">${LL.esc(term.parent)}</span></button>
                </div>` : ""}
              ${children.length ? `
                <div>
                  <div class="kv-k" style="margin-bottom:4px">Child Terms (${children.length})</div>
                  <div class="chip-row">
                    ${children.map((c) => `<button type="button" class="pill pill-btn" data-select-term="${LL.esc(c.id)}">↳ ${LL.esc(c.label)}</button>`).join("")}
                  </div>
                </div>` : ""}
              ${siblings.length ? `
                <div>
                  <div class="kv-k" style="margin-bottom:4px">Sibling Terms (${siblings.length})</div>
                  <div class="chip-row">
                    ${siblings.slice(0, 12).map((s) => `<button type="button" class="pill pill-btn" data-select-term="${LL.esc(s.id)}">${LL.esc(s.label)}</button>`).join("")}
                    ${siblings.length > 12 ? `<span class="muted">+${siblings.length - 12} more</span>` : ""}
                  </div>
                </div>` : ""}
            </div>` : ""}

          <div style="padding-top:8px;border-top:1px solid var(--border)">
            <div class="card-title" style="font-size:13px;margin-bottom:6px">
              <span>Live Corpus Usage</span>
              <div style="display:flex;gap:6px;flex-wrap:wrap">
                ${u.panels.length ? `<button type="button" class="btn btn-sm" data-jump-atlas-query="${LL.esc(term.label)}">Filter Atlas (${u.panels.length}) →</button>` : ""}
                ${matchingComps.length ? `<button type="button" class="btn btn-sm primary" data-jump-compare-measure="${LL.esc(matchingComps[0].measure)}">Compare (${matchingComps.length}) →</button>` : ""}
              </div>
            </div>

            ${!(u.stated_examples.length || u.items.length || u.panels.length) ? `
              <div class="muted">Not yet referenced in the 2-paper pilot; registered in <span class="mono">field_set 3</span> for autonomous ingestion of upcoming Lepidoptera papers.</div>
            ` : `
              ${u.items.length ? `
                <div style="margin-bottom:8px">
                  <div class="kv-k" style="margin-bottom:4px">Evidence Items (${u.items.length})</div>
                  <div class="chip-row">
                    ${u.items.map((ik) => `<button type="button" class="pill accent pill-btn mono" data-open-item="${LL.esc(ik)}">${LL.esc(ik)} ↗</button>`).join("")}
                  </div>
                </div>` : ""}

              ${u.stated_examples.length ? `
                <div style="margin-bottom:8px;overflow-x:auto">
                  <div class="kv-k" style="margin-bottom:4px">Author Phrasings Mapped to This Term (${u.stated_examples.length})</div>
                  <table class="data-table" style="font-size:11.5px">
                    <thead><tr><th>Paper</th><th>Stated in Paper</th><th>Origin</th></tr></thead>
                    <tbody>
                      ${u.stated_examples.slice(0, 8).map((ex) => `
                        <tr>
                          <td class="mono">${LL.esc(ex.paper)}</td>
                          <td>“${LL.esc(ex.stated)}” <div class="mono muted" style="font-size:10px">${LL.esc(ex.at)}</div></td>
                          <td><span class="pill ${ex.origin === "matched" ? "ok" : "info"}">${LL.esc(ex.origin)}</span></td>
                        </tr>`).join("")}
                    </tbody>
                  </table>
                </div>` : ""}

              ${u.panels.length ? `
                <div>
                  <div class="kv-k" style="margin-bottom:4px">Linked Panels in Atlas (${u.panels.length})</div>
                  <div class="chip-row">
                    ${u.panels.slice(0, 14).map((pid) => `<button type="button" class="pill pill-btn mono" data-jump-panel="${LL.esc(pid)}">${LL.esc(pid)} ↗</button>`).join("")}
                    ${u.panels.length > 14 ? `<span class="muted">+${u.panels.length - 14} more</span>` : ""}
                  </div>
                </div>` : ""}
            `}
          </div>

          ${decl ? `
            <div style="padding-top:8px;border-top:1px solid var(--border)">
              <div class="kv-k">Field Contract: ${LL.esc(decl.name)} (${LL.esc(decl.kind)})</div>
              <div class="muted" style="margin-top:2px">${LL.esc(decl.scope)}${decl.states && decl.states.length ? ` · Special states: ${decl.states.map((s) => `“${s}”`).join(", ")}` : ""}</div>
            </div>` : ""}
        </div>
      </div>`;
  }

  function renderVocabExplorer(container, data) {
    const st = LL.state;
    const idx = buildVocabIndexes(data);
    const fieldOrder = Array.from(idx.byField.keys()).sort((a, b) => idx.byField.get(b).length - idx.byField.get(a).length);
    const filtered = filterTerms(idx, st);

    if (!st.selectedTermId || !filtered.some((t) => t.id === st.selectedTermId)) {
      st.selectedTermId = filtered.length ? filtered[0].id : null;
    }

    const activeDecl = st.vocabField !== "ALL" ? idx.fieldDecls.get(st.vocabField) : null;
    const nearDups = (data.summary && data.summary.vocabulary_measures && data.summary.vocabulary_measures.near_duplicates) || [];
    const totalUsed = idx.terms.filter((t) => isTermUsed(t.id, idx.usage)).length;

    const fieldUsedCount = (f) => (idx.byField.get(f) || []).filter((t) => isTermUsed(t.id, idx.usage)).length;
    const selectedTerm = st.selectedTermId ? idx.byId.get(st.selectedTermId) : null;

    container.innerHTML = `
      <div class="toolbar">
        <input type="search" id="vf-vocab-search" placeholder="Search label, ID, synonym, definition, or paper phrase…" value="${LL.esc(st.vocabQuery)}" style="max-width:340px" />
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          ${[
            ["all", "All"],
            ["used", `Used in pilot (${totalUsed})`],
            ["defined", "Defined"],
            ["synonyms", "With synonyms"],
          ].map(([k, lbl]) => `<button type="button" class="btn btn-sm ${st.vocabFilter === k ? "active" : ""}" data-vocab-filter="${k}">${lbl}</button>`).join("")}
        </div>
        <div style="display:flex;gap:4px;margin-left:auto;flex-wrap:wrap">
          <button type="button" class="btn btn-sm ${st.vocabMode === "tree" ? "active" : ""}" data-vocab-mode="tree" title="Show parent → child hierarchy when viewing a field">Tree</button>
          <button type="button" class="btn btn-sm ${st.vocabMode === "flat" ? "active" : ""}" data-vocab-mode="flat">Flat</button>
          <button type="button" class="btn btn-sm" id="vf-vocab-export-csv">CSV</button>
          <button type="button" class="btn btn-sm" id="vf-vocab-export-json">JSON</button>
        </div>
      </div>

      <div class="vocab-layout">
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="card" style="padding:10px">
            <div class="kv-k" style="padding:2px 6px 6px">Controlled Fields (${fieldOrder.length})</div>
            <div class="field-rail">
              <button type="button" class="field-rail-btn ${st.vocabField === "ALL" ? "active" : ""}" data-vocab-field="ALL">
                <span>All fields</span>
                <span class="field-rail-meta"><span class="used-dot" title="Used in pilot"></span>${idx.terms.length}</span>
              </button>
              ${fieldOrder.map((f) => {
                const list = idx.byField.get(f) || [];
                const nu = fieldUsedCount(f);
                return `
                  <button type="button" class="field-rail-btn ${st.vocabField === f ? "active" : ""}" data-vocab-field="${LL.esc(f)}">
                    <span>${LL.esc(prettyTitle(f))}</span>
                    <span class="field-rail-meta">${nu > 0 ? `<span class="used-dot" title="${nu} used in pilot"></span>` : ""}${list.length}</span>
                  </button>`;
              }).join("")}
            </div>
          </div>

          ${activeDecl ? `
            <div class="card" style="padding:11px 12px">
              <div class="kv-k">Field Scope · ${LL.esc(activeDecl.kind)}</div>
              <div class="muted" style="margin-top:4px;line-height:1.45">${LL.esc(activeDecl.scope)}</div>
              ${activeDecl.states && activeDecl.states.length ? `<div class="muted" style="margin-top:6px">Allowed states: <span class="mono">${LL.esc(activeDecl.states.join(", "))}</span></div>` : ""}
            </div>` : ""}

          ${nearDups.length ? `
            <div class="card" style="padding:11px 12px">
              <div class="kv-k" style="margin-bottom:5px">Near-Duplicate Monitor (${nearDups.length})</div>
              ${nearDups.map((nd) => `
                <div class="muted" style="font-size:11px;margin-bottom:4px">
                  <button type="button" class="pill pill-btn" style="font-size:10px" data-select-term="${LL.esc(nd.a)}">${LL.esc(nd.a)}</button>
                  ↔
                  <button type="button" class="pill pill-btn" style="font-size:10px" data-select-term="${LL.esc(nd.b)}">${LL.esc(nd.b)}</button>
                </div>`).join("")}
            </div>` : ""}
        </div>

        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;padding:0 2px">
            <span class="muted" id="vf-vocab-count">Showing <strong>${filtered.length}</strong> of ${idx.terms.length} terms${st.vocabField !== "ALL" ? ` in <strong>${LL.esc(st.vocabField)}</strong>` : ""}${st.vocabMode === "tree" && st.vocabField === "ALL" ? " (select a field for hierarchy tree)" : ""}</span>
          </div>
          <div class="term-list" id="vf-vocab-list-wrap">
            ${renderVocabListMarkup(filtered, idx, st)}
          </div>
        </div>

        <div class="inspector-sticky vocab-detail" id="vf-vocab-detail">
          ${renderTermDetailMarkup(selectedTerm, idx, data)}
        </div>
      </div>
    `;

    const listWrap = container.querySelector("#vf-vocab-list-wrap");
    const detailWrap = container.querySelector("#vf-vocab-detail");
    const countEl = container.querySelector("#vf-vocab-count");
    const searchInput = container.querySelector("#vf-vocab-search");

    function bindDetailCopy() {
      const cp = detailWrap.querySelector("#vf-copy-term");
      if (cp) cp.onclick = () => copyWithFeedback(cp, cp.getAttribute("data-copy-text"));
    }
    bindDetailCopy();

    function refreshListAndDetail() {
      const flt = filterTerms(idx, st);
      if (!st.selectedTermId || !flt.some((t) => t.id === st.selectedTermId)) {
        st.selectedTermId = flt.length ? flt[0].id : null;
      }
      countEl.innerHTML = `Showing <strong>${flt.length}</strong> of ${idx.terms.length} terms${st.vocabField !== "ALL" ? ` in <strong>${LL.esc(st.vocabField)}</strong>` : ""}`;
      listWrap.innerHTML = renderVocabListMarkup(flt, idx, st);
      detailWrap.innerHTML = renderTermDetailMarkup(st.selectedTermId ? idx.byId.get(st.selectedTermId) : null, idx, data);
      bindDetailCopy();
    }

    searchInput.oninput = (e) => {
      st.vocabQuery = e.target.value;
      refreshListAndDetail();
    };

    container.onclick = (ev) => {
      const fBtn = ev.target.closest("[data-vocab-field]");
      if (fBtn) {
        st.vocabField = fBtn.getAttribute("data-vocab-field");
        renderVocabExplorer(container, data);
        return;
      }
      const fltBtn = ev.target.closest("[data-vocab-filter]");
      if (fltBtn) {
        st.vocabFilter = fltBtn.getAttribute("data-vocab-filter");
        renderVocabExplorer(container, data);
        return;
      }
      const mBtn = ev.target.closest("[data-vocab-mode]");
      if (mBtn) {
        st.vocabMode = mBtn.getAttribute("data-vocab-mode");
        renderVocabExplorer(container, data);
        return;
      }
      const selBtn = ev.target.closest("[data-select-term]");
      if (selBtn) {
        const tid = selBtn.getAttribute("data-select-term");
        const target = idx.byId.get(tid);
        st.selectedTermId = tid;
        if (target && st.vocabField !== "ALL" && !(target.fields || []).includes(st.vocabField)) {
          st.vocabField = (target.fields && target.fields[0]) || "ALL";
          renderVocabExplorer(container, data);
          return;
        }
        listWrap.querySelectorAll(".term-row").forEach((el) => {
          el.classList.toggle("selected", el.getAttribute("data-select-term") === tid);
        });
        detailWrap.innerHTML = renderTermDetailMarkup(target || null, idx, data);
        bindDetailCopy();
      }
    };

    container.querySelector("#vf-vocab-export-json").onclick = () => {
      const flt = filterTerms(idx, st);
      LL.downloadText("livinglit_lepidoptera_vocabulary.json", JSON.stringify(flt, null, 2), "application/json");
    };
    container.querySelector("#vf-vocab-export-csv").onclick = () => {
      const flt = filterTerms(idx, st);
      const q = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
      const header = ["id", "label", "fields", "parent", "synonyms", "definition", "scope", "source", "added"].join(",");
      const lines = flt.map((t) => [t.id, t.label, (t.fields || []).join(";"), t.parent || "", (t.synonyms || []).join(";"), t.definition || "", t.scope || "", t.source || "", t.added || ""].map(q).join(","));
      LL.downloadText("livinglit_lepidoptera_vocabulary.csv", [header, ...lines].join("\n"), "text/csv");
    };
  }

  // =========================================================================
  // 4. SymPy Formula Library & Interactive Live Workbench
  // =========================================================================
  function filterFormulas(formulas, derivsByFormula, st) {
    const q = (st.formulaQuery || "").trim().toLowerCase();
    return formulas.filter((f) => {
      if (st.formulaScope !== "ALL" && (f.scope || "shared") !== st.formulaScope) return false;
      if (st.formulaKind !== "ALL" && f.kind !== st.formulaKind) return false;
      const usedCount = (derivsByFormula.get(f.formula) || []).length || f.derivations || 0;
      if (st.formulaOnlyUsed && usedCount === 0) return false;
      if (!q) return true;
      const hay = [
        f.formula, f.kind, f.scope, f.statement,
        (f.equations || []).join(" "),
        Object.keys(f.variables || {}).join(" "),
        (f.assumes || []).join(" "),
        (f.holds_under || []).join(" "),
        f.does_not_apply || "",
        (f.cites && f.cites.text) || "",
      ].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }

  function renderFormulaListMarkup(filtered, derivsByFormula, st) {
    if (!filtered.length) {
      return `<div class="card muted" style="text-align:center;padding:24px">No formulas match this filter.</div>`;
    }
    const lep = filtered.filter((f) => f.scope === "lepidoptera");
    const shared = filtered.filter((f) => f.scope !== "lepidoptera");

    const cardHtml = (f) => {
      const sel = f.formula === st.selectedFormulaId;
      const liveDerivs = derivsByFormula.get(f.formula) || [];
      const nUse = Math.max(liveDerivs.length, f.derivations || 0);
      return `
        <button type="button" class="formula-card ${f.scope === "lepidoptera" ? "lep" : ""} ${sel ? "selected" : ""}" data-select-formula="${LL.esc(f.formula)}">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap">
            <span class="mono" style="font-weight:700;font-size:12.5px">${LL.esc(f.formula)}</span>
            <div style="display:flex;gap:4px;flex-wrap:wrap">
              <span class="pill ${f.scope === "lepidoptera" ? "accent" : ""}">${f.scope === "lepidoptera" ? "lepidoptera" : "shared"}</span>
              <span class="pill">${LL.esc(f.kind)}</span>
              ${nUse > 0 ? `<span class="pill ok">${nUse} derivation${nUse > 1 ? "s" : ""}</span>` : ""}
              ${f.suspect ? `<span class="pill bad">suspect</span>` : ""}
            </div>
          </div>
          <div class="eq-preview">${(f.equations || []).map(formatEquationHtml).join(" &nbsp;·&nbsp; ")}</div>
          <div class="muted" style="font-size:11.5px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden">${LL.esc(f.statement)}</div>
        </button>`;
    };

    let html = "";
    if (lep.length) {
      html += `<div class="formula-group-label">Lepidoptera Physics &amp; Morphometrics (${lep.length})</div>`;
      html += lep.map(cardHtml).join("");
    }
    if (shared.length) {
      html += `<div class="formula-group-label">Shared Statistical &amp; Audit Core (${shared.length})</div>`;
      html += shared.map(cardHtml).join("");
    }
    return html;
  }

  function ensureCalcInputs(formulaObj, st) {
    if (!st.formulaCalcInputs[formulaObj.formula]) {
      const t0 = formulaObj.tests && formulaObj.tests[0] && formulaObj.tests[0].given;
      const init = {};
      const meta = extractEqMeta(formulaObj);
      meta.inputs.forEach((v) => {
        init[v] = (t0 && t0[v] !== undefined) ? t0[v] : 1;
      });
      st.formulaCalcInputs[formulaObj.formula] = init;
    }
    return st.formulaCalcInputs[formulaObj.formula];
  }

  function renderCalcOutputsHtml(formulaObj, given) {
    const res = LL.evalFormulaEntry(formulaObj, given);
    const meta = extractEqMeta(formulaObj);
    const chips = meta.outputs.map((o) => {
      const v = res[o.outVar];
      const fmt = Number.isFinite(v) ? (Math.abs(v) > 0 && Math.abs(v) < 1e-3 ? v.toExponential(4) : LL.fmtNum(v, 5)) : "NaN";
      return `<div class="calc-result-chip">${formatVarHtml(o.outVar)} = ${LL.esc(fmt)}</div>`;
    }).join("");

    // Check if current inputs match any built-in test case
    let matchBadge = "";
    (formulaObj.tests || []).forEach((tc, ti) => {
      const gKeys = Object.keys(tc.given || {});
      const sameGiven = gKeys.length > 0 && gKeys.every((k) => Math.abs(Number(given[k]) - Number(tc.given[k])) <= 1e-9);
      if (sameGiven) {
        const expOk = Object.entries(tc.expect || {}).every(([k, ev]) => {
          const got = res[k];
          const tol = Math.max(1e-3, Math.abs(Number(ev)) * 1e-3);
          return Number.isFinite(got) && Math.abs(got - Number(ev)) <= tol;
        });
        matchBadge = expOk
          ? `<span class="pill ok">✓ Matches Test ${ti + 1} expect</span>`
          : `<span class="pill warn">Differs from Test ${ti + 1}</span>`;
      }
    });
    return `${chips}${matchBadge}`;
  }

  function renderFormulaDetailMarkup(formulaObj, formulaById, derivsByFormula, st) {
    if (!formulaObj) {
      return `<div class="card muted" style="padding:24px">Select a formula to view its equations, variable dimensions, assumptions, dependency graph, and interactive calculator.</div>`;
    }
    const meta = extractEqMeta(formulaObj);
    const given = ensureCalcInputs(formulaObj, st);
    const vars = formulaObj.variables || {};
    const liveDerivs = derivsByFormula.get(formulaObj.formula) || [];
    const rawSympy = (formulaObj.equations || []).join("; ");
    const allAssumes = Array.from(new Set([...(formulaObj.assumes || []), ...(formulaObj.holds_under || [])]));
    const uses = formulaObj.uses || [];
    const usedBy = formulaObj.used_by || [];

    return `
      <div class="card" style="display:flex;flex-direction:column;gap:12px">
        <div class="card-title" style="margin:0;align-items:flex-start">
          <div>
            <div style="font-size:16.5px;font-weight:800;letter-spacing:-0.01em">${LL.esc(prettyTitle(formulaObj.formula))}</div>
            <div class="mono muted" style="font-size:12px;margin-top:2px">${LL.esc(formulaObj.formula)}</div>
          </div>
          <div style="display:flex;gap:5px;flex-wrap:wrap">
            <span class="pill ${formulaObj.scope === "lepidoptera" ? "accent" : ""}">${formulaObj.scope === "lepidoptera" ? "Lepidoptera domain" : "Shared core"}</span>
            <span class="pill">${LL.esc(formulaObj.kind)}</span>
            ${formulaObj.added_version ? `<span class="pill">v${LL.esc(formulaObj.added_version)}</span>` : ""}
          </div>
        </div>

        <div class="eq-banner">
          ${(formulaObj.equations || []).map((eq) => `<div class="eq-banner-math">${formatEquationHtml(eq)}</div>`).join("")}
          <div class="eq-sympy-row">
            <code class="mono" style="word-break:break-word">SymPy: ${LL.esc(rawSympy)}</code>
            <button type="button" class="btn btn-sm" id="vf-copy-sympy" data-copy-text="${LL.esc(rawSympy)}">Copy SymPy</button>
          </div>
        </div>

        <div style="font-size:13px;color:var(--ink)">${LL.esc(formulaObj.statement)}</div>

        <div class="calc-box">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="font-size:12px;font-weight:700">Interactive Live Calculator</span>
            <div style="display:flex;gap:5px;flex-wrap:wrap">
              ${(formulaObj.tests || []).map((_tc, i) => `<button type="button" class="btn btn-sm" data-calc-preset="test:${i}">Test ${i + 1}</button>`).join("")}
              ${liveDerivs.map((d, i) => `<button type="button" class="btn btn-sm primary" data-calc-preset="deriv:${i}">Load ${LL.esc(d.paper)} (${LL.esc(d.derivation)})</button>`).join("")}
            </div>
          </div>
          <div class="calc-inputs">
            ${meta.inputs.map((v) => `
              <div class="calc-field">
                <label for="calc-in-${LL.esc(v)}">
                  <span>${formatVarHtml(v)}</span>
                  <span class="mono muted" style="font-size:10px">${LL.esc(vars[v] || "")}</span>
                </label>
                <input id="calc-in-${LL.esc(v)}" type="number" step="any" data-calc-var="${LL.esc(v)}" value="${LL.esc(given[v])}" />
              </div>`).join("")}
          </div>
          <div class="calc-outputs" id="vf-calc-outputs">
            ${renderCalcOutputsHtml(formulaObj, given)}
          </div>
        </div>

        ${Object.keys(vars).length ? `
          <div>
            <div class="kv-k" style="margin-bottom:5px">Variables &amp; Dimensional Signature</div>
            <table class="data-table" style="font-size:12px">
              <thead><tr><th>Symbol</th><th>SymPy ID</th><th>Dimension</th><th>Role</th></tr></thead>
              <tbody>
                ${Object.entries(vars).map(([sym, dim]) => {
                  const role = meta.outNames.has(sym) ? "output (LHS)" : (meta.inputs.includes(sym) ? "input (RHS)" : "auxiliary / proof");
                  return `
                    <tr>
                      <td style="font-family:var(--font-serif);font-size:14px">${formatVarHtml(sym)}</td>
                      <td class="mono">${LL.esc(sym)}</td>
                      <td><span class="pill">${LL.esc(dim)}</span></td>
                      <td class="muted">${role}</td>
                    </tr>`;
                }).join("")}
              </tbody>
            </table>
          </div>` : ""}

        ${allAssumes.length ? `
          <div>
            <div class="kv-k" style="margin-bottom:5px">Modeling Assumptions (${allAssumes.length})</div>
            <ul style="margin:0;padding-left:18px;font-size:12.5px;color:var(--ink)">
              ${allAssumes.map((a) => `<li style="margin-bottom:3px">${LL.esc(a)}</li>`).join("")}
            </ul>
          </div>` : ""}

        ${formulaObj.does_not_apply ? `
          <div class="warn-callout">
            <strong>Does not apply when:</strong> ${LL.esc(formulaObj.does_not_apply)}
          </div>` : ""}

        ${(uses.length || usedBy.length) ? `
          <div style="display:flex;flex-direction:column;gap:8px;padding-top:6px;border-top:1px solid var(--border)">
            ${uses.length ? `
              <div>
                <div class="kv-k" style="margin-bottom:4px">Derived From (SymPy Proof Dependencies)</div>
                <div class="chip-row">
                  ${uses.map((u) => {
                    const subsTxt = Object.entries(u.subs || {}).map(([k, v]) => `${k}→${v}`).join(", ");
                    return `<button type="button" class="pill accent pill-btn mono" data-select-formula="${LL.esc(u.formula)}">${LL.esc(u.formula)}${subsTxt ? ` (${LL.esc(subsTxt)})` : ""}</button>`;
                  }).join("")}
                </div>
              </div>` : ""}
            ${usedBy.length ? `
              <div>
                <div class="kv-k" style="margin-bottom:4px">Used By Derived Formulas (${usedBy.length})</div>
                <div class="chip-row">
                  ${usedBy.map((fid) => `<button type="button" class="pill pill-btn mono" data-select-formula="${LL.esc(fid)}">↳ ${LL.esc(fid)}</button>`).join("")}
                </div>
              </div>` : ""}
          </div>` : ""}

        <div style="padding-top:8px;border-top:1px solid var(--border)">
          <div class="kv-k" style="margin-bottom:5px">Live Corpus Derivations (${liveDerivs.length})</div>
          ${liveDerivs.length ? liveDerivs.map((d) => `
            <div class="kv-item" style="margin-bottom:6px">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap">
                <span class="mono" style="font-weight:700">${LL.esc(d.paper)} · ${LL.esc(d.derivation)}</span>
                <div style="display:flex;gap:5px;align-items:center">
                  <span class="pill ${d.verdict === "consistent" ? "ok" : "warn"}">${LL.esc(d.verdict)}</span>
                  <button type="button" class="btn btn-sm" data-open-item="${LL.esc(d.paper)}/${LL.esc(d.item)}">Audit ${LL.esc(d.item)} ↗</button>
                </div>
              </div>
              <div class="muted" style="margin-top:4px;font-size:11.5px">
                Inputs: <span class="mono">${LL.esc(Object.entries(d.inputs || {}).map(([k, obj]) => `${k}=${obj && obj.value != null ? obj.value : obj}${obj && obj.unit && obj.unit !== "1" ? " " + obj.unit : ""}`).join(", "))}</span>
                ${d.rebuilt && d.rebuilt.value != null ? ` · Rebuilt: <strong>${LL.esc(d.rebuilt.value)} ${LL.esc(d.rebuilt.unit || "")}</strong>` : ""}
              </div>
            </div>`).join("") : `<div class="muted">No pilot derivations invoke this formula yet; available in the verified SymPy library for autonomous auditing.</div>`}
        </div>

        ${formulaObj.cites && formulaObj.cites.text ? `
          <div style="padding-top:8px;border-top:1px solid var(--border);font-size:12px">
            <div class="kv-k" style="margin-bottom:3px">Reference Citation</div>
            <div class="muted">
              ${LL.esc(formulaObj.cites.text)}
              ${formulaObj.cites.url ? ` · <a href="${LL.esc(formulaObj.cites.url)}" target="_blank" rel="noopener" style="color:var(--accent)">DOI / Source ↗</a>` : ""}
            </div>
          </div>` : ""}
      </div>`;
  }

  function renderFormulaWorkbench(container, data) {
    const st = LL.state;
    const formulas = data.formulas || [];
    const formulaById = new Map(formulas.map((f) => [f.formula, f]));
    const derivsByFormula = new Map();
    (data.derivations || []).forEach((d) => {
      const key = d.library_formula || d.library;
      if (key && formulaById.has(key)) {
        if (!derivsByFormula.has(key)) derivsByFormula.set(key, []);
        derivsByFormula.get(key).push(d);
      }
    });

    const filtered = filterFormulas(formulas, derivsByFormula, st);
    if (!st.selectedFormulaId || !filtered.some((f) => f.formula === st.selectedFormulaId)) {
      const pref = filtered.find((f) => f.scope === "lepidoptera") || filtered[0];
      st.selectedFormulaId = pref ? pref.formula : null;
    }

    const nLep = formulas.filter((f) => f.scope === "lepidoptera").length;
    const nShared = formulas.length - nLep;
    const selected = st.selectedFormulaId ? formulaById.get(st.selectedFormulaId) : null;

    container.innerHTML = `
      <div class="toolbar">
        <div style="display:flex;gap:4px;flex-wrap:wrap">
          <button type="button" class="btn btn-sm ${st.formulaScope === "ALL" ? "active" : ""}" data-f-scope="ALL">All (${formulas.length})</button>
          <button type="button" class="btn btn-sm ${st.formulaScope === "lepidoptera" ? "active" : ""}" data-f-scope="lepidoptera">Lepidoptera Physics (${nLep})</button>
          <button type="button" class="btn btn-sm ${st.formulaScope === "shared" ? "active" : ""}" data-f-scope="shared">Statistical Core (${nShared})</button>
        </div>
        <select id="vf-formula-kind" aria-label="Filter by formula kind">
          <option value="ALL" ${st.formulaKind === "ALL" ? "selected" : ""}>All kinds</option>
          <option value="model" ${st.formulaKind === "model" ? "selected" : ""}>model</option>
          <option value="definition" ${st.formulaKind === "definition" ? "selected" : ""}>definition</option>
          <option value="derived" ${st.formulaKind === "derived" ? "selected" : ""}>derived</option>
        </select>
        <label class="chk">
          <input type="checkbox" id="vf-formula-used" ${st.formulaOnlyUsed ? "checked" : ""} /> Used in pilot
        </label>
        <input type="search" id="vf-formula-search" placeholder="Search formula, symbol, equation, citation…" value="${LL.esc(st.formulaQuery)}" />
        <button type="button" class="btn btn-sm" id="vf-formula-export" style="margin-left:auto">Export JSON</button>
      </div>

      <div class="formula-layout">
        <div>
          <div class="muted" id="vf-formula-count" style="margin-bottom:7px;padding:0 2px">Showing <strong>${filtered.length}</strong> of ${formulas.length} SymPy formulas</div>
          <div class="formula-list" id="vf-formula-list-wrap">
            ${renderFormulaListMarkup(filtered, derivsByFormula, st)}
          </div>
        </div>

        <div class="inspector-sticky" id="vf-formula-detail">
          ${renderFormulaDetailMarkup(selected, formulaById, derivsByFormula, st)}
        </div>
      </div>
    `;

    const listWrap = container.querySelector("#vf-formula-list-wrap");
    const detailWrap = container.querySelector("#vf-formula-detail");
    const countEl = container.querySelector("#vf-formula-count");

    function bindDetailHandlers() {
      const fObj = st.selectedFormulaId ? formulaById.get(st.selectedFormulaId) : null;
      if (!fObj) return;
      const cp = detailWrap.querySelector("#vf-copy-sympy");
      if (cp) cp.onclick = () => copyWithFeedback(cp, cp.getAttribute("data-copy-text"));

      detailWrap.querySelectorAll("[data-calc-var]").forEach((inp) => {
        inp.oninput = () => {
          const v = inp.getAttribute("data-calc-var");
          const cur = ensureCalcInputs(fObj, st);
          cur[v] = inp.value === "" ? "" : Number(inp.value);
          const outEl = detailWrap.querySelector("#vf-calc-outputs");
          if (outEl) outEl.innerHTML = renderCalcOutputsHtml(fObj, cur);
        };
      });

      detailWrap.querySelectorAll("[data-calc-preset]").forEach((btn) => {
        btn.onclick = () => {
          const [kind, idxStr] = btn.getAttribute("data-calc-preset").split(":");
          const idxNum = Number(idxStr);
          const cur = ensureCalcInputs(fObj, st);
          if (kind === "test" && fObj.tests && fObj.tests[idxNum]) {
            Object.entries(fObj.tests[idxNum].given || {}).forEach(([k, val]) => { cur[k] = val; });
          } else if (kind === "deriv") {
            const live = (derivsByFormula.get(fObj.formula) || [])[idxNum];
            if (live && live.inputs) {
              Object.entries(live.inputs).forEach(([k, obj]) => {
                cur[k] = obj && obj.value != null ? Number(obj.value) : Number(obj);
              });
            }
          }
          detailWrap.innerHTML = renderFormulaDetailMarkup(fObj, formulaById, derivsByFormula, st);
          bindDetailHandlers();
        };
      });
    }
    bindDetailHandlers();

    function refreshFormulaList() {
      const flt = filterFormulas(formulas, derivsByFormula, st);
      if (!st.selectedFormulaId || !flt.some((f) => f.formula === st.selectedFormulaId)) {
        st.selectedFormulaId = flt.length ? flt[0].formula : null;
      }
      countEl.innerHTML = `Showing <strong>${flt.length}</strong> of ${formulas.length} SymPy formulas`;
      listWrap.innerHTML = renderFormulaListMarkup(flt, derivsByFormula, st);
      detailWrap.innerHTML = renderFormulaDetailMarkup(st.selectedFormulaId ? formulaById.get(st.selectedFormulaId) : null, formulaById, derivsByFormula, st);
      bindDetailHandlers();
    }

    container.querySelector("#vf-formula-search").oninput = (e) => {
      st.formulaQuery = e.target.value;
      refreshFormulaList();
    };
    container.querySelector("#vf-formula-kind").onchange = (e) => {
      st.formulaKind = e.target.value;
      refreshFormulaList();
    };
    container.querySelector("#vf-formula-used").onchange = (e) => {
      st.formulaOnlyUsed = e.target.checked;
      refreshFormulaList();
    };
    container.querySelector("#vf-formula-export").onclick = () => {
      const flt = filterFormulas(formulas, derivsByFormula, st);
      LL.downloadText("livinglit_lepidoptera_formulas.json", JSON.stringify(flt, null, 2), "application/json");
    };

    container.onclick = (ev) => {
      const sBtn = ev.target.closest("[data-f-scope]");
      if (sBtn) {
        st.formulaScope = sBtn.getAttribute("data-f-scope");
        renderFormulaWorkbench(container, data);
        return;
      }
      const selBtn = ev.target.closest("[data-select-formula]");
      if (selBtn) {
        const fid = selBtn.getAttribute("data-select-formula");
        const fObj = formulaById.get(fid);
        st.selectedFormulaId = fid;
        if (fObj && st.formulaScope !== "ALL" && (fObj.scope || "shared") !== st.formulaScope) {
          st.formulaScope = "ALL";
          renderFormulaWorkbench(container, data);
          return;
        }
        listWrap.querySelectorAll(".formula-card").forEach((el) => {
          el.classList.toggle("selected", el.getAttribute("data-select-formula") === fid);
        });
        detailWrap.innerHTML = renderFormulaDetailMarkup(fObj || null, formulaById, derivsByFormula, st);
        bindDetailHandlers();
      }
    };
  }

  // =========================================================================
  // 5. Top-Level View Entry Point
  // =========================================================================
  LL.renderVocabFormulasView = function (root) {
    const st = LL.state;
    const data = st.data;
    const nTerms = (data.terms || []).length;
    const nFormulas = (data.formulas || []).length;

    root.innerHTML = `
      <div class="schema-hero">
        <div>
          <h2 style="margin:0;font-size:17px;font-weight:800;letter-spacing:-0.01em">Controlled Vocabulary &amp; SymPy Formula Workbench</h2>
          <div class="muted" style="margin-top:2px">Browse hierarchical Lepidoptera terms, inspect author phrasings &amp; panel links, and verify or test all ${nFormulas} symbolic equations interactively.</div>
        </div>
        <div class="seg-switch" role="tablist" aria-label="Vocabulary or Formula mode">
          <button type="button" class="seg-btn ${st.schemaTab === "vocab" ? "active" : ""}" data-schema-tab="vocab" role="tab">Controlled Vocabulary <span class="pill">${nTerms}</span></button>
          <button type="button" class="seg-btn ${st.schemaTab === "formulas" ? "active" : ""}" data-schema-tab="formulas" role="tab">Formula Library <span class="pill">${nFormulas}</span></button>
        </div>
      </div>
      <div id="vf-body"></div>
    `;

    root.querySelectorAll("[data-schema-tab]").forEach((btn) => {
      btn.onclick = () => {
        st.schemaTab = btn.getAttribute("data-schema-tab");
        LL.renderVocabFormulasView(root);
      };
    });

    const body = root.querySelector("#vf-body");
    if (st.schemaTab === "formulas") {
      renderFormulaWorkbench(body, data);
    } else {
      renderVocabExplorer(body, data);
    }
  };
})(window.LL);
