"""The supply chain logic behind each MCP tool. Plain Python, no MCP imports, so it is easy to test.

Every result carries a `sources` list (part, supplier, and PO IDs) so an agent can cite exactly
which records an answer came from, and every tool is read-only."""
import csv
import difflib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data"
AS_OF = date(2026, 10, 1)  # the sample data is a snapshot taken on this date


def _read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@dataclass
class Store:
    suppliers: dict
    parts: dict
    part_suppliers: list
    inventory: dict
    bom: list
    pos: list
    as_of: date = AS_OF

    @classmethod
    def load(cls, data_dir=DEFAULT_DATA, as_of=AS_OF):
        d = Path(data_dir)
        return cls(
            suppliers={r["supplier_id"]: r for r in _read(d / "suppliers.csv")},
            parts={r["part_id"]: r for r in _read(d / "parts.csv")},
            part_suppliers=_read(d / "part_suppliers.csv"),
            inventory={r["part_id"]: r for r in _read(d / "inventory.csv")},
            bom=_read(d / "bom.csv"),
            pos=_read(d / "purchase_orders.csv"),
            as_of=as_of,
        )

    # lookups ---------------------------------------------------------------
    def supplier(self, supplier_id):
        return self._get(self.suppliers, supplier_id, "supplier")

    def part(self, part_id):
        return self._get(self.parts, part_id, "part")

    def products(self):
        return sorted({r["product"] for r in self.bom})

    def product_bom(self, product):
        rows = [r for r in self.bom if r["product"].lower() == product.lower()]
        if not rows:
            raise ValueError(_not_found("product", product, self.products()))
        return rows

    def suppliers_for(self, part_id):
        return [r for r in self.part_suppliers if r["part_id"] == part_id]

    @staticmethod
    def _get(table, key, kind):
        key = key.strip().upper()
        if key not in table:
            raise ValueError(_not_found(kind, key, table))
        return table[key]


def _not_found(kind, value, options):
    close = difflib.get_close_matches(value, list(options), n=3, cutoff=0.4)
    hint = f" Did you mean: {', '.join(close)}?" if close else ""
    return f"Unknown {kind} '{value}'.{hint}"


def _d(text):
    return date.fromisoformat(text) if text else None


def _po_view(store, po):
    promised, received = _d(po["promised_date"]), _d(po["received_date"])
    if received:
        days_late = max(0, (received - promised).days)
        state = "received late" if days_late > 0 else "received on time"
    elif promised < store.as_of:
        days_late, state = (store.as_of - promised).days, "overdue"
    else:
        days_late, state = 0, "open"
    return {"po_id": po["po_id"], "part_id": po["part_id"], "supplier_id": po["supplier_id"],
            "qty": int(po["qty"]), "unit_price": float(po["unit_price"]),
            "value": round(int(po["qty"]) * float(po["unit_price"]), 2),
            "order_date": po["order_date"], "promised_date": po["promised_date"],
            "received_date": po["received_date"] or None, "state": state, "days_late": days_late}


def _on_time_rate(store, supplier_id):
    views = [_po_view(store, p) for p in store.pos if p["supplier_id"] == supplier_id]
    due = [v for v in views if v["state"] != "open"]
    if not due:
        return None
    return round(sum(v["state"] == "received on time" for v in due) / len(due), 3)


# tools -----------------------------------------------------------------------
def search_parts(store, query, limit=10):
    q = query.lower().strip()
    hits = [p for p in store.parts.values()
            if q in p["name"].lower() or q in p["category"].lower() or q == p["part_id"].lower()]
    results = []
    for p in hits[:limit]:
        results.append({**p, "unit_cost": float(p["unit_cost"]),
                        "suppliers": [r["supplier_id"] for r in store.suppliers_for(p["part_id"])]})
    return {"query": query, "count": len(hits), "parts": results,
            "sources": [p["part_id"] for p in results]}


def supplier_scorecard(store, supplier_id):
    s = store.supplier(supplier_id)
    sid = s["supplier_id"]
    views = [_po_view(store, p) for p in store.pos if p["supplier_id"] == sid]
    open_views = [v for v in views if v["state"] in ("open", "overdue")]
    parts = [r["part_id"] for r in store.part_suppliers if r["supplier_id"] == sid]
    sole = [p for p in parts if len(store.suppliers_for(p)) == 1]
    return {
        "supplier_id": sid, "name": s["name"], "country": s["country"], "region": s["region"],
        "lead_time_days": int(s["lead_time_days"]), "quality_ppm": int(s["quality_ppm"]),
        "on_time_rate": _on_time_rate(store, sid),
        "open_po_count": len(open_views),
        "open_po_value": round(sum(v["value"] for v in open_views), 2),
        "overdue_pos": [v["po_id"] for v in open_views if v["state"] == "overdue"],
        "parts_supplied": parts, "sole_source_parts": sole,
        "sources": [sid] + [v["po_id"] for v in views],
    }


def purchase_orders(store, part_id=None, supplier_id=None, state="open", limit=25):
    allowed = {"open", "overdue", "late", "all"}
    if state not in allowed:
        raise ValueError(f"state must be one of {sorted(allowed)}")
    if part_id:
        part_id = store.part(part_id)["part_id"]
    if supplier_id:
        supplier_id = store.supplier(supplier_id)["supplier_id"]
    views = [_po_view(store, p) for p in store.pos
             if (not part_id or p["part_id"] == part_id) and (not supplier_id or p["supplier_id"] == supplier_id)]
    if state == "open":
        views = [v for v in views if v["state"] in ("open", "overdue")]
    elif state == "overdue":
        views = [v for v in views if v["state"] == "overdue"]
    elif state == "late":
        views = [v for v in views if v["days_late"] > 0]
    views.sort(key=lambda v: (-v["days_late"], v["promised_date"]))
    shown = views[:limit]
    return {"count": len(views), "shown": len(shown), "purchase_orders": shown,
            "sources": [v["po_id"] for v in shown]}


def bom_cost(store, product, units=1):
    if units < 1:
        raise ValueError("units must be at least 1")
    rows = store.product_bom(product)
    lines = []
    for r in rows:
        p = store.part(r["part_id"])
        qty = int(r["qty_per_unit"])
        lines.append({"part_id": p["part_id"], "name": p["name"], "qty_per_unit": qty,
                      "unit_cost": float(p["unit_cost"]), "line_cost": round(qty * float(p["unit_cost"]), 2)})
    lines.sort(key=lambda line: -line["line_cost"])
    per_unit = round(sum(line["line_cost"] for line in lines), 2)
    for line in lines:
        line["share_pct"] = round(100 * line["line_cost"] / per_unit, 1)
    return {"product": rows[0]["product"], "units": units, "cost_per_unit": per_unit,
            "total_cost": round(per_unit * units, 2), "top_cost_drivers": lines[:3], "lines": lines,
            "sources": [line["part_id"] for line in lines]}


def _part_risk(store, part_id):
    inv = store.inventory[part_id]
    weekly = int(inv["weekly_demand"])
    cover_weeks = round(int(inv["on_hand"]) / weekly, 1) if weekly else None
    links = store.suppliers_for(part_id)
    primary = max(links, key=lambda r: int(r["share_pct"]))
    sup = store.suppliers[primary["supplier_id"]]
    lead_weeks = round(int(sup["lead_time_days"]) / 7, 1)
    overdue = [v for v in (_po_view(store, p) for p in store.pos if p["part_id"] == part_id) if v["state"] == "overdue"]
    on_time = _on_time_rate(store, sup["supplier_id"])

    score, reasons = 0, []
    if len(links) == 1:
        score += 3
        reasons.append(f"single source ({sup['name']})")
    if cover_weeks is not None and cover_weeks < lead_weeks:
        score += 4
        reasons.append(f"{cover_weeks} weeks of stock vs {lead_weeks}-week lead time")
    if overdue:
        score += 2 + min(len(overdue), 3)
        reasons.append(f"{len(overdue)} overdue PO(s), worst {max(v['days_late'] for v in overdue)} days late")
    if on_time is not None and on_time < 0.8:
        score += 2
        reasons.append(f"primary supplier on-time rate {on_time:.0%}")
    return {"part_id": part_id, "name": store.parts[part_id]["name"], "risk_score": score, "reasons": reasons,
            "weeks_of_cover": cover_weeks, "lead_time_weeks": lead_weeks, "primary_supplier": sup["supplier_id"],
            "alternate_suppliers": [r["supplier_id"] for r in links if r is not primary],
            "overdue_pos": [v["po_id"] for v in overdue]}


def supply_risks(store, product=None, limit=10):
    part_ids = ([r["part_id"] for r in store.product_bom(product)] if product
                else sorted(store.parts))
    risks = [r for r in (_part_risk(store, p) for p in dict.fromkeys(part_ids)) if r["risk_score"] > 0]
    risks.sort(key=lambda r: (-r["risk_score"], r["part_id"]))
    shown = risks[:limit]
    sources = []
    for r in shown:
        sources += [r["part_id"], r["primary_supplier"], *r["overdue_pos"]]
    return {"product": product, "at_risk_count": len(risks), "risks": shown, "sources": list(dict.fromkeys(sources))}


def simulate_delay(store, supplier_id, days):
    if not 1 <= days <= 180:
        raise ValueError("days must be between 1 and 180")
    sid = store.supplier(supplier_id)["supplier_id"]
    impacts = []
    for link in (r for r in store.part_suppliers if r["supplier_id"] == sid):
        pid = link["part_id"]
        inv = store.inventory[pid]
        weekly = int(inv["weekly_demand"])
        cover = int(inv["on_hand"]) / weekly if weekly else 0
        others = [r["supplier_id"] for r in store.suppliers_for(pid) if r["supplier_id"] != sid]
        share = int(link["share_pct"]) / 100
        # Stock runs short if remaining cover can't bridge the delay for this supplier's share of demand.
        bridge_weeks = cover / share if share else float("inf")
        short = bridge_weeks < days / 7
        impacts.append({
            "part_id": pid, "name": store.parts[pid]["name"], "supplier_share_pct": int(link["share_pct"]),
            "weeks_of_cover": round(cover, 1), "stockout_risk": short,
            "alternate_suppliers": others,
            "products_affected": sorted({r["product"] for r in store.bom if r["part_id"] == pid}),
            "units_at_risk_per_week": int(weekly * share) if short else 0,
        })
    impacts.sort(key=lambda i: (not i["stockout_risk"], i["part_id"]))
    return {"supplier_id": sid, "delay_days": days,
            "parts_with_stockout_risk": [i["part_id"] for i in impacts if i["stockout_risk"]],
            "products_affected": sorted({p for i in impacts if i["stockout_risk"] for p in i["products_affected"]}),
            "impacts": impacts, "sources": [sid] + [i["part_id"] for i in impacts]}
