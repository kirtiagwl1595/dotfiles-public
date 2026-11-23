---
name: "ste-visual-first"
description: "Picks a diagram, table or chart over text for the user's explanations, guides and docs. Use when a visual explains better than text. Not for yes/no or single-fact answers."
---

# STE Visual-First Responses

The ASD-STE100 writing rules apply to every reply. They live in the always-loaded writing style (`CLAUDE.style.md`). This skill adds (A) rewrite examples for those rules and (B) the visual-first rule.

## A. STE rewrite examples

| Before | After (STE) |
|---|---|
| It's worth noting that the report might not refresh if the cache is being rebuilt. | The report does not refresh while the cache rebuilds. |
| Utilize the import script in order to ingest the data. | Use the import script to load the data. |
| The query was run and results were returned to the user. | The query ran. It returned the results. |
| Make sure you're checking the logs and restarting the service. | Check the logs. Then restart the service. |
| Once the config is done, the table, which feeds the dashboard, gets refreshed. | When you complete the configuration, the system refreshes the table. The table feeds the dashboard. |

## B. Visual-first rule

Wherever possible, explain with a visual. Use text only to support the visual.

### Decide the format
| Content | Use |
|---|---|
| Process, flow, pipeline, sequence | Flow diagram |
| System, architecture, data model | Structure diagram (boxes and arrows) |
| Change over time, state transitions, how data moves | Short explanatory animation (HTML/CSS/JS, under 30 s, loops or has a replay button) |
| Cycle (loop that returns to the start) | HTML stepper with Next and Back buttons |
| Values, trends, comparisons | Chart |
| Parameters the reader can change, "what if" | Interactive HTML widget (sliders, toggles, step buttons) |
| Two or more options to compare | Comparison table or side-by-side visual |
| Single fact, yes/no, short answer | Text only. A visual does not help. |
| Email, message, code, document text | Text or file only. |

### Where the visual goes
| Surface | Use |
|---|---|
| claude.ai (web, desktop, mobile app) | The inline visualizer, as in "How to build". |
| Claude Code (terminal) | No inline visualizer. Use a table, an ASCII diagram or Mermaid in the reply. An HTML visual or an animation is a published artifact: make one only when the user asks. |

### How to build
1. On claude.ai, use the inline visualizer for throwaway visuals.
2. Make it throwaway: inline, not a saved file or published artifact, unless the user asks to keep or share it.
3. Keep labels short. Use the same STE words in the visual and in the text.
4. Write one or two sentences before the visual (what it shows) and, if necessary, one or two after (the key point).
5. Put short text between two visuals.
6. Start with the visual, not with a note on which tool made it.
7. For animations: show one concept, use slow timing, add step labels, and give a replay or step control.

## Examples

### Example 1: process (flow diagram)
User: How does the nightly job load data into the dashboard?
- Text: "The diagram shows the load path from source to dashboard."
- Visual: flow diagram. Source DB -> Extract -> Transform -> Table -> Dashboard.
- Text: "If a step fails, the dashboard does not refresh."

### Example 2: data model (structure diagram)
User: Explain how orders link to customers and products.
- Text: "The diagram shows the main tables and links."
- Visual: boxes for Customer, Order, Order Line, Product. Arrows: Customer places Order; Order has Order Line; Order Line refers to Product.
- Text: "One order can hold many products, through its order lines."

### Example 3: behavior over time (animation)
User: How does incremental load differ from a full reload?
- Text: "The animation shows the two load types side by side."
- Visual: animation. Left: all rows clear, then all rows load again. Right: only new rows (highlighted) move in. Replay button.
- Text: "Incremental load is faster. It needs a reliable change column."

### Example 4: what-if (interactive widget)
User: How does a down payment change my car loan payment?
- Text: "Move the sliders to see the monthly payment."
- Visual: interactive widget. Sliders: price, down payment, rate, term. Live output: monthly payment, total interest.
- Text: "This is an estimate. The lender gives the exact number."

### Example 5: comparison (table)
User: Compare SQLite and PostgreSQL for this app.
- Text: "The table compares the two on four points."
- Visual: comparison table. Rows: setup, concurrent writes, scale, best use.
- Text: "Start with SQLite. Move to PostgreSQL when many users write at the same time."

### Example 6: no visual (text only)
User: What port does PostgreSQL use by default?
- Text: one sentence with the answer. No visual.

### Example 7: no visual (draft text)
User: Write a short email to cancel tomorrow's meeting.
- Text: the email. No visual.

## Override
If the user asks for plain text, a long explanation, or another format, follow the user request for that response.
