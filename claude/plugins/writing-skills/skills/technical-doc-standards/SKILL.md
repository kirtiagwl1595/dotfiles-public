---
name: technical-doc-standards
description: Standards for writing internal technical documentation (runbooks, how-to guides, onboarding docs, troubleshooting guides, procedure documents) in HTML or Markdown. Use this skill whenever the user asks to write, restructure, or review documentation, a runbook, a guide, an SOP, setup instructions, an access/onboarding procedure, or a troubleshooting page, even if they just say "document this process" or "write this up for a colleague". Also use it when converting notes, chat transcripts, or screenshots into a shareable doc. Not for personal lessons in .claude/lessons/, which follow the Netflix style in the shared CLAUDE.md.
---

# Technical Documentation Standards

Standards for internal technical documentation: runbooks, procedures, onboarding guides, troubleshooting pages. Derived from documentation practice at scale (problem-first framing, progressive disclosure, explicit failure scenarios) and refined through real review cycles.

The goal of every choice below is the same: a reader under time pressure, mid-task, finds what they need without reading anything twice.

**Scope and precedence.** Use this skill for a doc a teammate needs to use, run, or change the solution (a solution doc). A personal write-up of what we learned is a lesson in `.claude/lessons/`: it follows the Netflix style in the shared CLAUDE.md, not this skill. If the repo has its own doc template, CONTRIBUTING rules or docs tooling, those win; apply the rules below only where the repo is silent.

## Before writing: three questions

Answer these before producing anything. If the user's request doesn't settle them, ask: but ask once, together, not one at a time.

1. **Who is the single reader?** A doc with two audiences has none. If a procedure involves two parties (e.g., an admin and a requester), pick the one who holds the document and write the other party's steps as *instructions to issue* and *evidence to expect back*. Name the audience explicitly in the doc header.
2. **What is the deliverable context?** Internal colleague hand-off, team wiki, customer-facing? This decides register, which sections exist (feedback loops and "next steps" sections are for published docs with distant readers: cut them for a doc handed to one colleague), and whether credentials may appear at all.
3. **What does the reader see when things go wrong?** Collect the literal error strings before writing. They anchor the troubleshooting section.

## Document structure

Follow this section order. Cut sections that don't apply; never reorder.

1. **The problem**: open on the situation the reader is actually in, not the feature. "You search for the user and get zero results" beats "This document describes user provisioning." If the intuitive next action is wrong (the trap), name it here and say why.
2. **Summary**: the complete procedure in one short numbered list, for readers who have done it before. This is the second entry point; the full procedure below is the first.
3. **Prerequisites**: only items the reader must *have in hand*: credentials, identifiers, decisions. The test: if you find yourself writing "because" to justify a prerequisite, it is not one: delete it. "A way to contact the requester" fails this test; "the requester's full email address" passes.
4. **Procedure**: numbered steps (see step anatomy below).
5. **Decision reference**: if the procedure contains a choice (which role, which environment, which option), give it its own section with a table: option / what it grants / use when / do not use when, plus a stated default.
6. **Failure scenarios**: a table: symptom / cause / resolution. Lead each symptom with the **literal error string** the reader sees, verbatim, visually distinct (mono, red). People match on the text on their screen, not on a paraphrase of it. Include the out-of-scope row: the error that looks similar but belongs to someone else, and where to send it.
7. **Reverse procedure**: if the doc grants, adds, or enables something, document undoing it. Note ordering hazards (e.g., "add the new group before removing the old one").

## Step anatomy

Each procedure step contains, in order:

- **Actor tag**: who performs it ("Administrator action" / "Requester action"), when more than one party is involved.
- **The instruction**: imperative, one action per sentence.
- **Screenshot** at the exact moment of the action, with a caption stating what to confirm on it (see screenshot rules).
- **Trap callout**: if the step has a known wrong turn, a visually distinct stop block naming it. Silent failures deserve the strongest warning: "no error is raised, the action appears to succeed, and the result is still wrong" is the most expensive class of mistake.
- **Mechanism, collapsed**: a `<details>` block (or "Background:" sub-section in Markdown) answering exactly one *why* question in two short paragraphs, using correct technical terms (authentication vs authorisation, token claims, just-in-time provisioning). Collapsed so it never interrupts execution; present so a reader hitting an unlisted edge case can reason instead of re-running steps blindly. Place it at the step where the mechanism bites, not in a preamble.
- **Verify condition**: a concrete, checkable end state: "the username appears on the Members tab and the count increased", not "the user is added". Where the evidence comes from the other party, phrase it as evidence received: "a screenshot showing X has been sent to you."

### Gates beat instructions

Where a step exists only to establish a precondition, require the *artifact that proves it*, not the action that produces it. "Do not proceed without the screenshot showing Access Denied" is complied with; "ask them to try signing in" is skipped. State what the artifact must show.

### Relay messages

Wherever the doc tells the reader to communicate something to a third party, provide the exact message, ready to send, in a visually distinct block with a copy affordance. Each instruction in the message carries its reason in the same sentence ("this error is expected and confirms your account was registered: please send me a screenshot"); a stated reason materially improves compliance. Keep the register neutral-professional; note that the reader may rephrase.

## Register

Internal technical docs are professional, not conversational. The failures are consistent and specific: check for each:

- **Editorialising.** State facts; don't argue them. "Extending access afterwards is a single action, whereas investigating an unintended change is not": never "takes thirty seconds vs. considerably longer." Cut any second clause whose only job is to justify the first.
- **Speech register.** No rhetorical questions, no quoted hypothetical dialogue as argument, no conversational connectives ("That is just where the link points"). Rewrite as statements.
- **Explaining the obvious.** If a sentence tells the reader something true of any situation ("you'll need a way to contact them"), delete it.
- **One noun per role, used consistently.** Pick "the requester", "the administrator", "the account": and never alternate with "them / the person / someone". Inconsistent subject nouns damage register more than any single informal phrase.
- **Standard terminology.** "administrator" not "admin" in prose (product/group names unchanged); "select" not "click"; "private browsing window" not "incognito"; "notification" not "toast". UI element names verbatim and bold: **Add member**, **Members** tab.
- Imperative voice for instructions. Second person is fine and preferred; formality does not require the passive.

## Screenshots and figures

- Crop to the relevant region; cut empty canvas. Cut small detail crops (a button, a badge, a menu) for the one or two elements the whole procedure hinges on.
- Caption every figure in a consistent style, stating what the reader should confirm: "Realm indicator at top left": not what the image is.
- Where the doc will be used during a screenshare to guide the other party, tag those specific figures ("Screenshare reference") so they're findable by scanning.
- If the product's own wording is misleading (e.g., a heading that says "Internal Server Error" when the operative line is "Access Denied"), say so explicitly next to the screenshot. Misleading product copy is a documented fact, not something to silently paraphrase around.
- Descriptive alt text on every image: what the screen shows, including the state (checkbox selected, banner present).

## Visual design (HTML docs)

Read `references/html-doc-pattern.md` before building an HTML doc: it contains the full page pattern (document identity bar, sticky TOC, callout system, credential card, verify checkboxes) and the delivery pipeline for self-contained files.

Core rules that apply regardless:

- **Light page.** White/near-white background. Dark "cinematic" treatments read as marketing, not documentation.
- **One colour, one meaning.** Reserve red exclusively for failure/blocker content (error strings, stop callouts). Amber = caution / other-party action. Green = verification. The accent colour = navigation and information. The moment a semantic colour is also used for emphasis, it stops carrying information.
- **Document identity always visible**: type badge (RUNBOOK / GUIDE), title, and a metadata row: status, owner, last-updated, applies-to version, time required. This is what tells a reader whether to trust the page, and it's the row most internal docs skip.
- **Narrow prose, wide evidence.** Body text at ~70–75ch measure; figures and tables may break wider. If a doc feels heavy, line length is the usual cause.
- **Headings say what the section contains** ("Failure scenarios", "Which group to assign"): never headline writing.
- Type scale modest: h1 ≤ ~36px. Restraint reads as authority.

## Credentials and secrets

- Company and customer data stays in company systems. A doc saved in a personal place (a personal repo, Claude memory, `.claude/lessons/`) holds no customer names, credentials or internal URLs; use neutral placeholders. A doc committed to a repo uses placeholders for every secret.
- Never inline a secret in prose. If the doc must carry one, isolate it in a clearly-labelled config block at the very top of the file with placeholder values, and tell the user the exact line numbers to edit.
- In HTML: hold-to-reveal (pointer events only: a Space-key handler on a `<button>` fights the browser's synthetic click and breaks; give keyboard users a Copy button instead, which never renders the value). Re-mask on release, pointer-leave, blur, and `visibilitychange`. Keep the value in a JS const, injected on demand: never in the served markup.
- State plainly in the doc that the file itself is a credential: reveal controls protect the screen, not the file. Add handling guidance (internal storage only, reissue on rotation, scroll past the credential section before screensharing).

## Design and reference docs

For a design doc, spec or reference doc, the runbook structure above does not apply. Use these rules. They match the template in `templates/project/docs/README.md`.

- **Same PR.** A behaviour change updates its living doc in the same change (Google engineering practices).
- **Now, or Planned.** State what exists now. Mark each unbuilt item `Planned (<milestone>)`. Delete dead text. EGM rates a doc that contradicts the code as a Blocker.
- **Living and dated apart.** Rules go in living docs. Measured numbers, run IDs and dates go in dated records (Diátaxis separates reference from other content).
- **Decisions are records.** Do not edit an accepted decision. A new one supersedes it and lists the sections it changes (AWS ADR guidance).
- **State a contract once.** Define it in one place and link the code symbol for fields, flags and defaults. Say this policy in the repo, so reviewers do not ask for copies.
- **Stable citations.** Section numbers never change. A citation names its file.
- **One term for one concept.** Define it once (Microsoft Writing Style Guide).

Rules do not replace design review: a missing decision stays a real gap. Write it as an open question.

## Honesty about inference

When a claim in the doc is inferred rather than observed: a UI behaviour deduced from one screenshot, a group's purpose deduced from its name: either verify it or flag it in the doc ("confirm this behaviour on your own instance before relying on it") *and* tell the user it needs confirmation. Never present an inference with the same confidence as an observation. When handing over the doc, list the unverified claims explicitly.

## Delivery

- Deliver the doc as a file: in the repo's docs folder for a solution doc, or in the scratchpad for a draft. Publishing it as an artifact or sending it through a connector is outward-facing: do it only when the user asks.
- Single self-contained file unless told otherwise: HTML with images as base64 data URIs (quantize flat-UI screenshots to a ~192-colour PNG palette: roughly 3× smaller at no visible cost; use JPEG only for captures with photographic/noisy backgrounds).
- Print stylesheet: hide interactive chrome, expand collapsed sections, avoid breaks inside steps/figures/tables.
- Ephemeral state (checkbox ticks) stays in memory, resets on reload, and the doc says so: persisted ticks lie to the next reader.
- After delivering, state what still needs the user's confirmation (see Honesty about inference) and where the editable placeholders are.
