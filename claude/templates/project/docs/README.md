# Docs map

## Living reference

These docs say what is true now.

| Doc | Contents |
|---|---|
| [decisions.md](decisions.md) | Each design decision: the pick, the reason, the options not taken. |
| [../README.md](../README.md), [../CLAUDE.md](../CLAUDE.md) | Quick start, layout, commands. |

## Dated records

These docs describe a past run or a past plan. Do not edit them to match the code.

| Folder | Contents |
|---|---|
| [results/](results/) | One page for each run: the numbers and what they mean. |
| [plans/](plans/) | Plans as they were approved. |
| [research/](research/) | Background research. |

## Rules

1. **Same PR.** A change to behaviour updates its living doc in the same PR.
2. **Now, or Planned.** A living doc states what exists now. Mark each unbuilt item `Planned (<milestone>)`.
3. **Rules, decisions and data live apart.** A living doc states the rule and cites its decision, for example `(D8)`. Reasons and dates go to `decisions.md`. Measured numbers go to dated records.
4. **Decisions are not edited.** A new decision supersedes an old one, and lists the sections it changes. Those sections change in the same PR.
5. **State a contract once.** Define an interface a reader needs in one place. For fields, flags and defaults, link the code symbol that owns them. The code is the spec for those details.
6. **Stable section numbers.** A section number never changes, and each number is in one file only.
7. **Citations name the file.** Write the file name, then § and the number. Inside a doc, a § number with no file name means a section of that doc.
8. **One term for one concept.** Define each term once, in the doc's Terms section, and use only that word.

`tests/test_docs.py` checks rules 2, 3 and 7, the commands in docs, and this map.

Reviewers: rule 5 is this repo's policy. Do not report a detail as missing when the doc links the code that owns it. A doc that contradicts the code is still a defect.
