"""Golden questions a supply manager would ask, the tool call an agent should make, and the facts the
answer must contain. If a change to the tools breaks one of these, CI fails before an agent ever sees it."""
import pytest

from supplyline import tools

CASES = [
    ("What's the riskiest part for the headset launch?",
     tools.supply_risks, {"product": "Aurora Headset"}, lambda r: r["risks"][0]["part_id"] == "P115"),
    ("Which part drives the phone's cost the most?",
     tools.bom_cost, {"product": "Aurora Phone"}, lambda r: r["top_cost_drivers"][0]["name"] == "Application processor"),
    ("Which parts would we lose if Bluefin slips two months?",
     tools.simulate_delay, {"supplier_id": "S03", "days": 60}, lambda r: "P115" in r["parts_with_stockout_risk"]),
    ("Is Lumen Display a single point of failure?",
     tools.supplier_scorecard, {"supplier_id": "S07"}, lambda r: len(r["sole_source_parts"]) == 2),
    ("Do we have a backup for the power management IC?",
     tools.search_parts, {"query": "Power management"}, lambda r: len(r["parts"][0]["suppliers"]) == 2),
]


@pytest.mark.parametrize("question,tool,args,check", CASES, ids=[c[0] for c in CASES])
def test_golden(question, tool, args, check):
    assert check(tool(tools.Store.load(), **args)), question
