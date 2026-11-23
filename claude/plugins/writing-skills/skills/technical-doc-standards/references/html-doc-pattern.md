# HTML documentation page pattern

The full pattern for a self-contained HTML runbook/guide. Use when the deliverable is an HTML file. For Markdown docs, only the structural and register rules from SKILL.md apply.

## Page skeleton

```
fixed doc bar         : type badge · doc title · current section name · thin progress line
two-column shell      : sticky TOC (≈240px) | main content (max ~1000px)
  doc header          : type badge, h1, one-sentence purpose, audience block, metadata grid
  sections 1..n       : separated by hairline rules, each with a small "Section N" eyebrow
  footer              : handling notes (credential warning, ephemeral-state note, capture source)
```

- TOC collapses to a boxed list above the content below ~1040px. Highlight the active section on scroll (compare `getBoundingClientRect().top` against a fixed offset; no IntersectionObserver needed).
- The doc bar's "current section" text mirrors the active section's h2. This plus the TOC answers "where am I" at all times.

## Token set (proven values)

```css
--page:#FFFFFF; --chrome:#F7F8FA; --ink:#1B1F24; --muted:#5A646E;
--line:#E3E7EB; --line-soft:#EEF1F4;
--accent:#0A7C84; --accent-deep:#065A61; --accent-wash:#E8F4F5;   /* info/navigation */
--danger:#BF2A20; --danger-wash:#FDEDEB; --danger-line:#F0BDB7;   /* failure only   */
--warn:#8F6200;  --warn-wash:#FFF7E6;  --warn-line:#EBCE8E;       /* caution/other-party */
--ok:#17754A;    --ok-wash:#EDF7F1;    --ok-line:#A9D6BD;         /* verification   */
```

Type: a display face for headings (e.g., Archivo 600/700), a workhorse body face (e.g., IBM Plex Sans), a mono face for labels, error strings, URLs, and code (e.g., IBM Plex Mono). Body ~16.5px/1.65; h1 clamp to ≤36px; prose measure 70–75ch; figures/tables may exceed it.

## Components

**Callout**: rounded box, wash background, mono uppercase label. Three variants only: `stop` (danger), `warn` (amber), `info` (accent). The label states the situation ("If the realm reads master"), not a severity word.

**Step card**: bordered box per procedure step: actor tag row (numbered square + "Administrator action"/"Requester action" chip), h3, body, figures, callouts, collapsed mechanism, verify block.

**Verify block**: full-width button, `aria-pressed` toggled, green wash, custom checkbox drawn in CSS, "VERIFY" mono label, condition text. Count of ticked verifies shown in the TOC footer ("2 of 5 steps verified"). In-memory only.

**Mechanism disclosure**: native `<details>`; summary in mono uppercase with a +/− square; body two short paragraphs. In print CSS, force the body visible.

**Relay message block**: amber-bordered box, "Message to send" label, Copy button that flattens the block's paragraphs to plain text (`innerText`, collapse whitespace, join with blank lines).

**Failure table**: symptom / cause / resolution. Symptom cell leads with the literal error string in a red mono chip (`display:block`), then the qualifier ("Still appearing after the group was assigned").

**Credential card**: label + mono value field + Copy button per row. URLs get an "Open" link button. Password row: masked value (`••••` with wide letter-spacing), Hold button, Copy button.

## Credential reveal implementation

Pointer-only. Do not bind Space/Enter: a button's synthetic click on Space-release races the keyup and re-masks instantly; the control appears dead.

```js
['mousedown','touchstart','pointerdown'].forEach(ev =>
  btn.addEventListener(ev, e => { e.preventDefault(); show(); }, {passive:false}));
['mouseup','mouseleave','touchend','touchcancel','pointerup','pointercancel','blur']
  .forEach(ev => btn.addEventListener(ev, hide));
document.addEventListener('mouseup', hide);            // release outside the button
document.addEventListener('visibilitychange', () => { if (document.hidden) hide(); });
```

The secret lives in a `const` in a config `<script>` at the top of the file and is written into the DOM only inside `show()`. View-source and inspect-element on the masked field reveal nothing (the file itself still contains it: say so in the doc).

Config block: first `<script>` in `<head>`, boxed comment "FILL THESE IN", one `const` per editable value (secret, username, owner, last-updated). After building, report the exact line numbers to the user. Unfilled placeholders (`PASTE_...`) must degrade gracefully: metadata shows "Not set", the reveal shows an instruction instead of the placeholder.

## Clipboard

`navigator.clipboard.writeText` with a hidden-textarea `execCommand('copy')` fallback (file may be opened via `file://`). Flash the button label ("Copied") for ~1.4s.

## Image pipeline (self-contained delivery)

1. Crop each screenshot to the relevant region; make small detail crops of pivotal elements.
2. Resize to ~1500px wide (detail crops smaller).
3. Flat-UI screenshots: quantize to a 192-colour palette with dithering (`PIL: im.quantize(colors=192, method=Image.MEDIANCUT, dither=Image.FLOYDSTEINBERG)`): ~3× smaller than truecolour PNG with no visible loss on UI chrome. Captures with photographic or noisy backgrounds: JPEG q≈84 instead (palette quantization fails on them).
4. Author the HTML with `IMG:name` placeholders; embed with a script that base64-substitutes each and asserts none remain. Assert expected invariants (placeholder count, removed sections absent) in the same script.

## Print CSS

Hide: doc bar, TOC, buttons, link buttons, scroll hints. Single column. Expand all `<details>`. `break-inside:avoid` on steps, figures, tables, callouts, cards. Diagram SVGs: drop the min-width so they fit the page.

## SVG flow diagrams

Hand-authored SVG, no library. Swimlane per actor (wash-tinted lane bands, mono uppercase lane labels matching the actor-tag vocabulary). Failure/denial nodes in danger colours; terminal success node filled with the accent. Dashed amber return path for the most common failure loop, labelled. Where a return path crosses another arrow, draw a small bezier bridge over the crossing: an unbridged crossing reads as a junction. Wrap in an `overflow-x:auto` shell with `min-width:~750px` on the SVG; diagrams with real text scroll on mobile, never shrink. Provide `<title>`/`<desc>` describing the full flow.
