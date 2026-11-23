#!/usr/bin/env bash
# An R analysis repo with no CLAUDE.md.
set -e
git init -q -b main
git config user.name eval && git config user.email eval@example.com && git config commit.gpgsign false
printf -- '---\ntitle: "Sales analysis"\n---\n\n```{r}\nsales <- read.csv("data/sales.csv")\nsummary(sales)\n```\n' > analysis.Rmd
mkdir -p data && printf 'month,sales\n1,10\n2,12\n' > data/sales.csv
git add -A && git commit -q -m init
