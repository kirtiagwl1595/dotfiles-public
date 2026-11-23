---
name: rdf-check
description: Validates local RDF files and runs SPARQL on them with Apache Jena (riot, sparql). Use when the user asks to check, validate or parse Turtle, TriG, N-Triples, N-Quads, RDF/XML or JSON-LD, or to test a SPARQL query on a local file.
---

# RDF check

Use local files only. These commands send nothing over the network.

On Windows, Jena ships `riot.bat` and `sparql.bat` in its `bat\` folder: use `riot.bat` and `sparql.bat` where this skill says `riot` and `sparql`, from Git Bash or PowerShell.

1. If `riot` is missing, tell the user how to install Apache Jena, and ask before you run any install. Jena needs Java 17 or later (for example Eclipse Temurin). Download the binary release from <https://jena.apache.org/download/>, check it against the `.sha512` file next to it, unpack it, and add its `bin/` folder (Windows: `bat\`) to `PATH`. macOS also has `brew install jena`.
2. Validate: `riot --validate <file>`. A clean file prints nothing and exits 0. Report each error with its line and column.
3. Count triples: `riot --count <file>`.
4. Run a query: `sparql --data=<file> --query=<query.rq>`.
5. Show a parse problem or a query result in a short table. Do not change the data file unless the user asks.
