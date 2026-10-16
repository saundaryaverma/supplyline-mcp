# Supplyline MCP

[![tests](https://github.com/saundaryaverma/supplyline-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/saundaryaverma/supplyline-mcp/actions/workflows/ci.yml)

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent answer supply chain questions, such as "what could stop the headset launch?", by calling real tools over supplier, purchase order, inventory, and bill of materials data. Every answer comes back with the IDs of the records it used, so the agent can cite them and a supply manager can check them.

The sample dataset is synthetic: three invented products (Aurora Phone, Aurora Headset, Aurora Watch), ten invented suppliers, 19 parts, and 137 purchase orders, generated from a fixed seed.

## Why I built it

Supply managers spend a lot of their week answering the same questions by pulling reports and cross-checking spreadsheets. Which parts are single-sourced? Which POs are late? What happens if one supplier slips? An LLM can answer these well, but only if it reads the actual data instead of guessing. MCP is the standard way to give an agent that access. I wanted to see what the tools need to look like so an agent's answers can be trusted.

The design choices that came out of that:

- **Every result carries `sources`.** Part, supplier and PO IDs, so the agent can cite where each fact came from, and a test checks that every cited ID really exists.
- **Read-only.** No tool can change data.
- **Answers explain themselves.** `supply_risks` doesn't just return a score. It returns the reasons ("single source", "2.0 weeks of stock vs a 3.0-week lead time", "1 overdue PO, 100 days late") in plain words that a supply manager can act on.
- **Bad input is a helpful error, not a crash.** Ask for supplier `S7` and the agent gets back `Unknown supplier 'S7'. Did you mean: S07?`, so it can correct itself.

## Tools

| Tool | What it answers |
|---|---|
| `supply_risks(product?)` | Which parts are most at risk, ranked, with reasons: single sourcing, stock that won't last through the lead time, overdue POs, unreliable suppliers |
| `simulate_delay(supplier_id, days)` | What-if: if this supplier slips N days, which parts and products could run out, and is there a backup supplier? |
| `supplier_scorecard(supplier_id)` | Lead time, quality (defects per million), on-time delivery rate, open and overdue POs, and the parts only this supplier makes |
| `bom_cost(product, units)` | Bill of materials cost roll-up and the top cost drivers |
| `purchase_orders(part_id?, supplier_id?, state)` | Open, overdue or late POs, most late first |
| `search_parts(query)` | Find parts by name, category or ID |

It also exposes a `supplyline://products` resource and a `weekly_supply_review` prompt that walks an agent through a full review: risks, then scorecards for the suppliers behind them, then a delay simulation.

## Example

What `supply_risks` returns for `{"product": "Aurora Headset", "limit": 3}` (trimmed):

```json
{
  "product": "Aurora Headset",
  "at_risk_count": 9,
  "risks": [
    {"part_id": "P115", "name": "Li-ion cell, 4,800 mAh", "risk_score": 12,
     "reasons": ["single source (Bluefin Batteries)", "2.0 weeks of stock vs 3.0-week lead time",
                 "1 overdue PO(s), worst 100 days late", "primary supplier on-time rate 69%"],
     "alternate_suppliers": []},
    {"part_id": "P102", "name": "Application processor", "risk_score": 9,
     "reasons": ["single source (Kestrel Semiconductors)", "4.0 weeks of stock vs 10.0-week lead time",
                 "primary supplier on-time rate 78%"],
     "alternate_suppliers": []},
    {"part_id": "P110", "name": "Retail box and inserts", "risk_score": 9,
     "reasons": ["2.0 weeks of stock vs 4.0-week lead time", "1 overdue PO(s), worst 56 days late",
                 "primary supplier on-time rate 75%"],
     "alternate_suppliers": ["S06"]}
  ],
  "sources": ["P115", "S03", "PO5118", "P102", "S02", "P110", "S10", "PO5084"]
}
```

And `simulate_delay("S03", 60)` flags `P115` as a stockout risk for the Aurora Headset, with no alternate supplier.

## Run it

Needs Python 3.10 or newer.

```bash
pip install -e .
supplyline-mcp            # starts the server over stdio
```

To use it from Claude Desktop, add this to `claude_desktop_config.json` and restart:

```json
{
  "mcpServers": {
    "supplyline": { "command": "supplyline-mcp" }
  }
}
```

To use your own data, put CSVs with the same columns in a folder and set `SUPPLYLINE_DATA=/path/to/folder`. To regenerate the sample data: `python src/supplyline/generate_data.py`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

- **Unit tests** for each tool: cost roll-ups add up, overdue POs really are overdue, risks are sorted and explained, and every cited source ID exists in the data.
- **Golden questions** (`tests/test_golden.py`): questions a supply manager would ask, the tool call an agent should make, and the fact the answer must contain. If a change breaks one, CI fails.
- **End-to-end MCP tests** (`tests/test_server.py`): start the real server over stdio and call it the way Claude Desktop would, including checking that bad input comes back as a tool error.

CI runs everything on Python 3.10, 3.11 and 3.12.

## Simplifications

The stockout check in `simulate_delay` assumes the delayed supplier's share of demand has to be covered by stock on hand. It doesn't model partial shipments or expediting. The risk score uses fixed weights. Both are easy to swap out, and a real deployment would tune them with supply managers.
