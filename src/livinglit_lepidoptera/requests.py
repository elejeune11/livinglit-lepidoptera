"""Source-data request drafts (08 decision 46; 06-releases, Source data requests).

One draft per paper whose items stay cannot check for lack of per-sample data,
naming the figures and how many items the data would open. Drafts are written
for Emma to send; nothing is sent and no address is guessed.
"""
from __future__ import annotations

from collections import Counter


from . import DEFAULT_FIELD


def draft(paper: str, rec, audit: dict) -> str:
    stuck = [(iid, i) for iid, i in audit["items"].items()
             if i["status"] == "cannot check" and i["depth"] in ("none", "printed only")]
    by_unit = Counter(i["unit"] for _, i in stuck)
    field_label = DEFAULT_FIELD.replace("_", " ")
    lines = [f"Subject: Request for source data: {rec.source.title}", "",
             f"Dear {rec.source.last_author or 'corresponding author'},", "",
             f"We are auditing published {field_label} studies, including \"{rec.source.title}\""
             + (f" ({rec.source.journal}, {rec.source.year})" if rec.source.journal else f" ({rec.source.year})") + ".",
             f"For {len(stuck)} of {len(audit['items'])} reported results, the per-sample values are needed to "
             f"reproduce the statistics. Would you be willing to share the individual data points behind:", ""]
    for uid, n in sorted(by_unit.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {rec.units[uid].where} ({rec.units[uid].title}): {n} result{'s' if n > 1 else ''}")
    lines += ["", "A spreadsheet with one column per group is ideal. We will cite the dataset and share our audit with you.",
              "", "With thanks,", "Emma Lejeune"]
    return "\n".join(lines)


def write_drafts(audits: dict, records: dict, out_dir) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for pid, a in audits.items():
        if any(i["status"] == "cannot check" and i["depth"] in ("none", "printed only") for i in a["items"].values()):
            (out_dir / f"{pid}.md").write_text(draft(pid, records[pid], a))
            written.append(pid)
    return written
