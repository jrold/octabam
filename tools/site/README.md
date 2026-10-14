# The manual site

The musician-facing manual, built with MkDocs Material and deployed to
GitHub Pages by `.github/workflows/pages.yml` on pushes to main. The same
build, without the deploy, runs as the `site` job on every PR
(`.github/workflows/ci.yml`).

`gen_pages.py` renders the generated pages from this commit's manifests
(`tools/remix/index.py`, the registry). The generated files sit under
`reference/` in the site directory, are gitignored, and never appear in
the tree, so the site and the manifests cannot drift: a merge to main
rebuilds them.

Generated, gitignored:

- the module reference (every module grouped by category, with author,
  kind, proof status, FX2 id and knobs; stock effects in their own
  section)
- the credits (authors linked, with their module keys)
- one `_remix-<name>.md` fragment per non-test remix (the remix doc, its
  proof line, and its module table), pulled into each remix page with
  `pymdownx.snippets` (`--8<-- "reference/_remix-<name>.md"`)

## Rules the doclinks gate forces on these files

`tools/verify/doclinks.py` scans every tracked text file, these pages
included. Three consequences:

- The `REPOPATH` rule matches any `docs/…md`, `tools/…md`,
  `modules/…md` or `remixes/…md` string anywhere in a tracked file and
  requires the path to exist. The remix pages are therefore named flat at
  the site root (`remix-core.md`, `remix-inserts.md`, `remix-bus.md`) so
  the nav needs no `remixes/…` entry, and links into the repository are
  written as full `https://github.com/sambanks/octabam/…` URLs.
  `reference/…` paths are safe (not in the alternation). `gen_pages.py`
  builds all paths with pathlib joins and all GitHub links as f-strings
  (strings containing `{}` are exempt), so it stays quiet too.
- Markdown links in a tracked page must resolve from the page's own
  directory, and `#anchor` targets must match a heading under GitHub's
  slug rule.
- No section sign in any tracked page ("section N" instead).

`mkdocs build --strict` is the complementary gate: it fails on a broken
site link or a broken snippet include (it does not check anchors;
doclinks does).

## Build

```bash
python3 -m venv .venv-site
.venv-site/bin/pip install -r docs/site/requirements.txt
python3 tools/site/gen_pages.py
.venv-site/bin/mkdocs serve --config-file docs/site/mkdocs.yml   # http://127.0.0.1:8000
.venv-site/bin/mkdocs build --strict --config-file docs/site/mkdocs.yml
```

`gen_pages.py` needs the submodules initialized (`git submodule update
--init`): the registry execs the authors' manifests.
