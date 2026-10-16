"""MCP server exposing the supply chain tools to any MCP client (Claude Desktop, Cursor, an agent framework).

Run it:  supplyline-mcp            (stdio, for desktop clients)
Data:    set SUPPLYLINE_DATA to a folder with the same CSV files to point it at your own data."""
import os

from mcp.server.fastmcp import FastMCP

from supplyline import tools

mcp = FastMCP("supplyline")
_store = None


def store():
    global _store
    if _store is None:
        _store = tools.Store.load(os.environ.get("SUPPLYLINE_DATA", tools.DEFAULT_DATA))
    return _store


@mcp.tool()
def search_parts(query: str, limit: int = 10) -> dict:
    """Find parts by name, category, or part ID (for example "battery", "Display", or "P104")."""
    return tools.search_parts(store(), query, limit)


@mcp.tool()
def supplier_scorecard(supplier_id: str) -> dict:
    """Lead time, quality (defects per million), on-time delivery rate, open and overdue POs,
    and sole-source parts for one supplier."""
    return tools.supplier_scorecard(store(), supplier_id)


@mcp.tool()
def purchase_orders(part_id: str | None = None, supplier_id: str | None = None,
                    state: str = "open", limit: int = 25) -> dict:
    """List purchase orders, most late first. state is "open" (not yet received), "overdue",
    "late" (any PO that arrived or is running late), or "all"."""
    return tools.purchase_orders(store(), part_id, supplier_id, state, limit)


@mcp.tool()
def bom_cost(product: str, units: int = 1) -> dict:
    """Roll up the bill of materials cost for a product and show the biggest cost drivers."""
    return tools.bom_cost(store(), product, units)


@mcp.tool()
def supply_risks(product: str | None = None, limit: int = 10) -> dict:
    """Rank parts by supply risk, with the reasons: single sourcing, stock that won't last through
    the lead time, overdue POs, and unreliable suppliers. Leave product empty to check every part."""
    return tools.supply_risks(store(), product, limit)


@mcp.tool()
def simulate_delay(supplier_id: str, days: int) -> dict:
    """What-if: if this supplier's shipments slip by N days, which parts and products could run out?"""
    return tools.simulate_delay(store(), supplier_id, days)


@mcp.resource("supplyline://products")
def products() -> str:
    """The products in the dataset, one per line."""
    return "\n".join(store().products())


@mcp.prompt()
def weekly_supply_review(product: str) -> str:
    """A ready-made prompt for a weekly supply review of one product."""
    return (f"Run a weekly supply review for {product}. Call supply_risks for the product, then "
            "supplier_scorecard for each primary supplier behind the top three risks, then simulate a "
            "14-day delay for the riskiest supplier. Write a short summary for a supply manager: the top "
            "risks, what to do about each, and the IDs of the records you used. Only state facts that "
            "appear in tool results.")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
