"""Writes the sample dataset in data/. Everything here is synthetic: invented products,
suppliers, and numbers, generated from a fixed seed so results are reproducible."""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 7
TODAY = date(2026, 10, 1)

SUPPLIERS = [
    # id, name, country, region
    ("S01", "Northwind Glass", "Japan", "APAC"),
    ("S02", "Kestrel Semiconductors", "Taiwan", "APAC"),
    ("S03", "Bluefin Batteries", "South Korea", "APAC"),
    ("S04", "Orchard Precision Metals", "China", "APAC"),
    ("S05", "Halcyon Optics", "Germany", "EMEA"),
    ("S06", "Ridgeway Plastics", "Mexico", "AMER"),
    ("S07", "Lumen Display Co.", "South Korea", "APAC"),
    ("S08", "Copperline Interconnect", "Vietnam", "APAC"),
    ("S09", "Atlas Sensors", "United States", "AMER"),
    ("S10", "Meridian Packaging", "India", "APAC"),
]

PARTS = [
    # id, name, category, unit_cost, suppliers
    ("P100", "Cover glass, 6.1 in", "Display", 18.40, ["S01"]),
    ("P101", "OLED panel, 6.1 in", "Display", 74.00, ["S07"]),
    ("P102", "Application processor", "Silicon", 96.50, ["S02"]),
    ("P103", "Power management IC", "Silicon", 6.20, ["S02", "S09"]),
    ("P104", "Li-ion cell, 3,200 mAh", "Battery", 11.80, ["S03"]),
    ("P105", "Aluminum enclosure", "Mechanical", 22.10, ["S04"]),
    ("P106", "Camera lens stack", "Optics", 14.30, ["S05", "S01"]),
    ("P107", "Image sensor, 48 MP", "Silicon", 21.70, ["S09"]),
    ("P108", "Flex cable set", "Interconnect", 3.40, ["S08", "S04"]),
    ("P109", "Speaker module", "Audio", 2.90, ["S06", "S08"]),
    ("P110", "Retail box and inserts", "Packaging", 1.60, ["S10", "S06"]),
    ("P111", "Micro-OLED panel, 1.3 in", "Display", 188.00, ["S07"]),
    ("P112", "Pancake lens assembly", "Optics", 41.00, ["S05"]),
    ("P113", "Depth sensor module", "Silicon", 29.50, ["S09"]),
    ("P114", "Headband frame", "Mechanical", 9.80, ["S06", "S04"]),
    ("P115", "Li-ion cell, 4,800 mAh", "Battery", 16.40, ["S03"]),
    ("P116", "Wrist sensor array", "Silicon", 12.60, ["S09", "S02"]),
    ("P117", "Sapphire crystal, 44 mm", "Display", 9.10, ["S01"]),
    ("P118", "Titanium case, 44 mm", "Mechanical", 31.00, ["S04"]),
]

PRODUCTS = {
    "Aurora Phone": {"P100": 1, "P101": 1, "P102": 1, "P103": 2, "P104": 1, "P105": 1, "P106": 2,
                     "P107": 2, "P108": 6, "P109": 2, "P110": 1},
    "Aurora Headset": {"P111": 2, "P112": 2, "P102": 1, "P103": 3, "P113": 4, "P114": 1, "P115": 1,
                       "P108": 10, "P109": 2, "P110": 1},
    "Aurora Watch": {"P117": 1, "P118": 1, "P116": 1, "P103": 1, "P104": 1, "P108": 3, "P110": 1},
}


def build(out_dir):
    rng = random.Random(SEED)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    supplier_rows = []
    for sid, name, country, region in SUPPLIERS:
        supplier_rows.append({
            "supplier_id": sid, "name": name, "country": country, "region": region,
            "lead_time_days": rng.choice([21, 28, 35, 42, 56, 70]),
            "quality_ppm": rng.choice([40, 85, 120, 210, 450, 900]),
        })
    supplier_rows[6]["lead_time_days"] = 84      # display maker: long lead time
    supplier_rows[1]["lead_time_days"] = 70      # silicon: long lead time

    part_rows, part_supplier_rows, inventory_rows = [], [], []
    for pid, name, cat, cost, sups in PARTS:
        part_rows.append({"part_id": pid, "name": name, "category": cat, "unit_cost": f"{cost:.2f}"})
        for i, sid in enumerate(sups):
            share = 100 if len(sups) == 1 else (70 if i == 0 else 30)
            part_supplier_rows.append({"part_id": pid, "supplier_id": sid, "share_pct": share})
        weekly = sum(qty for bom in PRODUCTS.values() for p, qty in bom.items() if p == pid) * rng.choice([800, 1000, 1200])
        inventory_rows.append({"part_id": pid, "on_hand": weekly * rng.choice([2, 4, 6, 9, 12]), "weekly_demand": weekly})

    bom_rows = [{"product": prod, "part_id": p, "qty_per_unit": q} for prod, bom in PRODUCTS.items() for p, q in bom.items()]

    po_rows, n = [], 5000
    for ps in part_supplier_rows:
        sup = next(s for s in supplier_rows if s["supplier_id"] == ps["supplier_id"])
        reliability = {"S07": 0.6, "S03": 0.75, "S04": 0.8}.get(sup["supplier_id"], 0.92)
        for _ in range(rng.randint(4, 7)):
            n += 1
            ordered = TODAY - timedelta(days=rng.randint(10, 150))
            promised = ordered + timedelta(days=sup["lead_time_days"])
            price = float(next(p for p in PARTS if p[0] == ps["part_id"])[3]) * rng.uniform(0.97, 1.05)
            row = {"po_id": f"PO{n}", "part_id": ps["part_id"], "supplier_id": ps["supplier_id"],
                   "qty": rng.choice([5000, 10000, 20000, 40000]), "unit_price": f"{price:.2f}",
                   "order_date": ordered.isoformat(), "promised_date": promised.isoformat(),
                   "received_date": "", "status": "open"}
            if promised <= TODAY:
                if rng.random() < reliability:
                    row["received_date"] = (promised - timedelta(days=rng.randint(0, 3))).isoformat()
                    row["status"] = "received"
                elif rng.random() < 0.5:
                    row["received_date"] = (promised + timedelta(days=rng.randint(4, 20))).isoformat()
                    row["status"] = "received"
            po_rows.append(row)

    def write(name, rows):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    write("suppliers.csv", supplier_rows)
    write("parts.csv", part_rows)
    write("part_suppliers.csv", part_supplier_rows)
    write("inventory.csv", inventory_rows)
    write("bom.csv", bom_rows)
    write("purchase_orders.csv", po_rows)


if __name__ == "__main__":
    build(Path(__file__).resolve().parents[2] / "data")
