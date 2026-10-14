#!/usr/bin/env python3
"""Render the manual site's generated pages from the manifests.

    python3 tools/site/gen_pages.py

Writes the generated pages (gitignored, so the deploy builds them fresh):

  modules.md           every module by category, plus the stock effects
  _remix-<name>.md     one per non-test remix: its module table
  credits.md           authors grouped, with their module keys

The pages are rendered at deploy time (the Pages workflow on main; the site
job of ci.yml on a PR), so the site and the manifests cannot drift. Stdlib
only, like the rest of the tools. The registry execs the manifests, so the
author submodules must be checked out first (git submodule update --init).

Links to the repository are written as full https URLs; no literal
repository path appears in this file on purpose: tools/verify/doclinks.py
scans it too, and every path it finds must exist.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / pathlib.Path("docs") / "site" / "reference"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1])); import toolpath  # noqa: E402,F401  (every tools/ dir on sys.path)

from remix import index, registry  # noqa: E402
from remix.schema import CATEGORY_TITLE, Category  # noqa: E402

PROOF_LEGEND = (
    "| proof | what it means |\n"
    "|---|---|\n"
    "| `make check` | builds and boots under the port |\n"
    "| local render | heard or measured in a local render, never flashed |\n"
    "| port-gated | a gate under the ColdFire port pins its behaviour; not on a unit |\n"
    "| on hardware | ran on a unit |\n"
)

GH = "https://github.com/sambanks/octabam"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _author(m) -> str:
    return f"[{m.author}]({m.author_url})" if m.author_url else (m.author or "?")


def _module_url(m) -> str:
    d = pathlib.Path("modules") / m.name
    if (ROOT / d / "README.md").exists():
        return f"{GH}/blob/main/{d}/README.md"
    return f"{GH}/tree/main/{d}"


def _module_rows(ms) -> list[str]:
    out = ["| module | category | author | what it does | proof |", "|---|---|---|---|---|"]
    for m in ms:
        cat = CATEGORY_TITLE[m.category or Category.REFERENCE]
        out.append(f"| [**{m.key}**]({_module_url(m)}) | {cat} | {_author(m)} "
                   f"| {_cell(m.doc)} | {index.proof_text(m)} |")
    return out


def modules_page(mods) -> str:
    lines = ["# Modules reference", "",
             "Rendered from the manifests when the site is built; not checked "
             "into the repository. Lists every module in the registry, "
             "including ones no official remix carries.", "",
             "## Proof", "",
             PROOF_LEGEND]
    for cat, ms in index.by_category(mods).items():
        if not ms:
            continue
        lines += [f"## {CATEGORY_TITLE[cat]}"]
        for m in ms:
            fx2 = f"`0x{m.menu.fx2_id:02x}`" if m.menu is not None else "no FX2 row"
            rows = [f"| author | {_author(m)} |",
                    f"| kind | `{m.kind.value}` |",
                    f"| proof | {index.proof_text(m)} |",
                    f"| FX2 | {fx2} |"]
            if m.menu is not None:
                knobs = ", ".join(f"{n}@{i}" for n, i in sorted(
                    m.knob_map().items(), key=lambda kv: kv[1]))
                rows.append(f"| knobs | {knobs} |")
            lines += [f"### {m.key}", "",
                      m.doc, "",
                      "| | |", "|---|---|"] + rows
    from remix import stock
    lines += ["## Stock effects", "",
              "Their code, descriptors and dispatch are already in every "
              "image. A remix lists one by key to keep its chooser row; an "
              "effect on neither chooser gives up its DSP words.", "",
              "| effect | FX2 id | what it does |", "|---|---|---|"]
    for m in stock.MODULES:
        lines.append(f"| {m.key} | `0x{m.menu.fx2_id:02x}` | {_cell(m.doc)} |")
    return "\n".join(lines) + "\n"


def remix_fragment(r, mods) -> str:
    lines = [f"{r.doc}", "",
             f"Proof: {index.proof_text(r)}", "",
             "| module | category | author | what it does | proof |", "|---|---|---|---|---|"]
    for key in r.modules:
        m = mods[key]
        cat = CATEGORY_TITLE[m.category or Category.REFERENCE]
        lines.append(f"| [**{m.key}**]({_module_url(m)}) | {cat} | {_author(m)} "
                     f"| {_cell(m.doc)} | {index.proof_text(m)} |")
    return "\n".join(lines) + "\n"


def credits_page(mods) -> str:
    by_author = {}
    for m in mods.values():
        if m.is_stock:
            continue
        by_author.setdefault((m.author, m.author_url), []).append(m)
    lines = ["# Credits", "",
             "Every module names its author in its manifest; the build refuses "
             "a module without one. Grouped below by author.", ""]
    for (author, url), ms in sorted(by_author.items(), key=lambda kv: kv[0][0].lower()):
        label = f"[{author}]({url})" if url else (author or "?")
        lines += [f"## {label}", "",
                  ", ".join(f"[{m.key}]({_module_url(m)})" for m in sorted(ms, key=lambda m: m.key)), ""]
    lines += ["The project itself: see the repository README's Credit section "
              f"({GH})."]
    return "\n".join(lines) + "\n"


def main() -> int:
    mods = registry.modules()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = {"modules.md": modules_page(mods),
            "credits.md": credits_page(mods)}
    for name in registry.remix_names():
        if registry.is_test(name) or registry.remix_dir(name) is None:
            continue
        jobs[f"_remix-{name}.md"] = remix_fragment(registry.remix(name), mods)
    for name, text in sorted(jobs.items()):
        (OUT / name).write_text(text)
        print(f"wrote docs/site/reference/{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
