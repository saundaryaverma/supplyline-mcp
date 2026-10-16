import pytest

from supplyline import tools


@pytest.fixture(scope="module")
def store():
    return tools.Store.load()


def test_search_finds_by_name_category_and_id(store):
    assert {p["part_id"] for p in tools.search_parts(store, "battery")["parts"]} == {"P104", "P115"}
    assert {p["part_id"] for p in tools.search_parts(store, "Display")["parts"]} == {"P100", "P101", "P111", "P117"}
    assert tools.search_parts(store, "p102")["parts"][0]["name"] == "Application processor"


def test_unknown_ids_suggest_close_matches(store):
    with pytest.raises(ValueError, match="Did you mean: S07"):
        tools.supplier_scorecard(store, "S7")
    with pytest.raises(ValueError, match="Aurora Phone"):
        tools.bom_cost(store, "Aurora Phon")


def test_scorecard_counts_sole_source_parts(store):
    card = tools.supplier_scorecard(store, "s07")
    assert card["name"] == "Lumen Display Co."
    assert set(card["sole_source_parts"]) == {"P101", "P111"}
    assert 0 <= card["on_time_rate"] <= 1


def test_bom_cost_adds_up(store):
    cost = tools.bom_cost(store, "aurora phone", units=1000)
    assert cost["cost_per_unit"] == pytest.approx(sum(line["line_cost"] for line in cost["lines"]))
    assert cost["total_cost"] == pytest.approx(cost["cost_per_unit"] * 1000)
    assert cost["top_cost_drivers"][0]["part_id"] == "P102"  # processor is the biggest line
    assert sum(line["share_pct"] for line in cost["lines"]) == pytest.approx(100, abs=0.5)


def test_overdue_pos_are_past_promise_and_not_received(store):
    for po in tools.purchase_orders(store, state="overdue", limit=500)["purchase_orders"]:
        assert po["received_date"] is None and po["promised_date"] < store.as_of.isoformat()
        assert po["days_late"] > 0


def test_purchase_orders_rejects_bad_state(store):
    with pytest.raises(ValueError):
        tools.purchase_orders(store, state="lost")


def test_risks_are_ranked_and_explained(store):
    risks = tools.supply_risks(store, "Aurora Headset")["risks"]
    scores = [r["risk_score"] for r in risks]
    assert scores == sorted(scores, reverse=True)
    assert all(r["reasons"] for r in risks)


def test_every_source_id_exists(store):
    known = set(store.parts) | set(store.suppliers) | {p["po_id"] for p in store.pos}
    results = [tools.supply_risks(store), tools.supplier_scorecard(store, "S03"),
               tools.bom_cost(store, "Aurora Watch"), tools.simulate_delay(store, "S02", 60),
               tools.purchase_orders(store, state="all")]
    for r in results:
        assert r["sources"] and set(r["sources"]) <= known


def test_long_delay_on_sole_source_supplier_creates_stockout_risk(store):
    sim = tools.simulate_delay(store, "S03", 60)
    assert "P115" in sim["parts_with_stockout_risk"]
    assert "Aurora Headset" in sim["products_affected"]


def test_delay_bounds(store):
    with pytest.raises(ValueError):
        tools.simulate_delay(store, "S03", 0)
