/* Slide-Over Result Audit Drawer (verbatim anchors, resolved context, values, checks, linked panels) */
window.LL = window.LL || {};

(function (LL) {
  LL.closeDrawer = function () {
    document.getElementById("audit-drawer").classList.remove("open");
    document.getElementById("drawer-backdrop").classList.remove("open");
  };

  LL.openItemDrawer = function (itemKey) {
    const data = LL.state.data;
    if (!data) return;
    // itemKey can be "2024_Lloyd/F2_ridge_spacing" or "2024_Lloyd/F2_ridge_spacing/blue_all"
    const parts = itemKey.split("/");
    const paper = parts[0], itemId = parts[1];
    const item = (data.items || []).find((it) => it.paper === paper && it.item === itemId);
    if (!item) return;

    const vals = (data.values || []).filter((v) => v.paper === paper && v.item === itemId);
    const checks = (data.checks || []).filter((c) => c.paper === paper && c.item === itemId);
    const linkedPanels = (data.panels || []).filter((p) => p.paper === paper && (p.linked_items || []).includes(itemId));

    document.getElementById("drawer-sub").textContent = `${paper} · Unit ${item.unit} · Measure: ${item.measure}`;
    document.getElementById("drawer-title").textContent = itemId;

    const statusCls = item.status === "consistent" || item.status === "consistent within reading" ? "ok" : (item.status === "inconsistent" ? "bad" : "warn");

    const valRows = vals.map((v) => `
      <tr>
        <td>${LL.esc(v.group_label || v.group)}</td>
        <td class="mono">${LL.esc(v.value_printed || v.value)} ${LL.esc(v.unit_of_value || "")}</td>
        <td><span class="pill">${LL.esc(v.kind)}</span></td>
        <td><span class="pill info">${LL.esc(v.origin)}</span></td>
      </tr>`).join("");

    const ctxStr = vals[0] && vals[0].context_terms ? vals[0].context_terms : "";
    const ctxPairs = ctxStr ? ctxStr.split("; ").map((p) => p.split("=")).filter((a) => a.length === 2) : [];

    document.getElementById("drawer-body").innerHTML = `
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <span class="pill ${statusCls}">Status: ${LL.esc(item.status)}</span>
        <span class="pill">Depth: ${LL.esc(item.depth)}</span>
        ${item.direction && item.direction !== "not available" ? `<span class="pill accent">Direction: ${LL.esc(item.direction)} (${LL.esc(item.direction_origin)})</span>` : ""}
        ${item.p ? `<span class="pill mono">${LL.esc(item.p)}</span>` : ""}
      </div>

      <div>
        <div style="font-weight:700;margin-bottom:5px">Empirical Finding</div>
        <div>${LL.esc(item.finding)}</div>
      </div>

      <div>
        <div style="font-weight:700;margin-bottom:5px">Verbatim Paper Anchor (≤ 30 words)</div>
        <blockquote class="quote-block">“${LL.esc(item.anchor)}”</blockquote>
      </div>

      <div class="kv-grid">
        <div class="kv-item"><div class="kv-k">Sample Size (n)</div><div class="kv-v">${LL.esc(item.n || "not stated")}</div></div>
        <div class="kv-item"><div class="kv-k">Statistical Test</div><div class="kv-v">${LL.esc(item.test || "not stated")}</div></div>
        <div class="kv-item"><div class="kv-k">Method</div><div class="kv-v">${LL.esc(item.method || "not stated")}</div></div>
        <div class="kv-item"><div class="kv-k">Software</div><div class="kv-v">${LL.esc(item.software || "not stated")}</div></div>
      </div>

      ${valRows ? `
        <div>
          <div style="font-weight:700;margin-bottom:6px">Audited Empirical Values (${vals.length})</div>
          <table class="data-table">
            <thead><tr><th>Group</th><th>Value</th><th>Kind</th><th>Origin</th></tr></thead>
            <tbody>${valRows}</tbody>
          </table>
        </div>` : ""}

      ${ctxPairs.length ? `
        <div>
          <div style="font-weight:700;margin-bottom:6px">Resolved Controlled-Vocabulary Context</div>
          <div class="kv-grid">
            ${ctxPairs.map(([k, v]) => `<div class="kv-item"><div class="kv-k">${LL.esc(k.replace(/_/g, " "))}</div><div class="kv-v mono" style="font-size:11px">${LL.esc(v)}</div></div>`).join("")}
          </div>
        </div>` : ""}

      ${checks.length ? `
        <div>
          <div style="font-weight:700;margin-bottom:6px">Automated Numerical Checks (${checks.length})</div>
          ${checks.map((c) => `
            <div class="kv-item" style="margin-bottom:6px">
              <div style="display:flex;justify-content:space-between">
                <span class="mono" style="font-weight:600">${LL.esc(c.name || c.check || "check")}</span>
                <span class="pill ${c.verdict === "consistent" ? "ok" : (c.verdict === "inconsistent" ? "bad" : "warn")}">${LL.esc(c.verdict)}</span>
              </div>
              <div class="muted" style="margin-top:3px">${LL.esc(c.detail || c.note || "")}</div>
            </div>`).join("")}
        </div>` : ""}

      ${linkedPanels.length ? `
        <div>
          <div style="font-weight:700;margin-bottom:6px">Linked Atomic Panels</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            ${linkedPanels.map((p) => {
              const t = LL.getThumb(p.id);
              return `<button type="button" class="btn btn-sm" data-jump-panel="${LL.esc(p.id)}">${t ? `<img src="${t}" style="width:28px;height:22px;object-fit:cover;border-radius:3px" />` : ""}${LL.esc(p.id)}</button>`;
            }).join("")}
          </div>
        </div>` : ""}
    `;

    document.getElementById("audit-drawer").classList.add("open");
    document.getElementById("drawer-backdrop").classList.add("open");
  };
})(window.LL);
