# patch-stats

Counts upstream Linux kernel activity for one or more people over a date range, shown side by side (default: Anuj, Kanchan, Nitesh):

| stat | source |
|---|---|
| merged | commits authored by the person in a kernel tree (`git log`) |
| signoff / reviewed / tested | commits carrying their `Signed-off-by` / `Reviewed-by` / `Tested-by` |
| submitted | every patch email the person authored on a mailing list, including revisions, resends and patches sent by others on their behalf (patchwork.kernel.org) |

Needs Python 3 (stdlib only), git, and network access to patchwork.

```
./patch-stats.py --tree /path/to/linux                       # default three people
./patch-stats.py --tree /path/to/linux --person "Me=me@x.org,me@y.org" --person "You=you@x.org"
./patch-stats.py --tree /path/to/linux -v                    # per-person commit/patch lists, with lore links
```

- `--tree` / `--ref`: the repo and ref(s) to scan. Defaults to the current directory and `HEAD`, i.e. whatever is checked out; nothing is ever checked out or fetched. `--ref` can be repeated (e.g. `--ref origin/master --ref origin/for-next`) when your work landed in different trees; each commit is counted once.
- `--since` / `--until`: date range. Default is `2026-01-01` to now.
- `--person NAME=EMAIL[,EMAIL...]` (repeatable): a person to report on and all their addresses. An address belongs to one person only. `--email` is a shortcut for a single person named `you`.
- `--carrier` (repeatable): other people who post series containing these people's patches (maintainers who forward their work). The listed people are always scanned themselves. Patches carried by anyone else are not counted as submitted.
- `--no-submitted`: git counts only (no network).

Every option has a `PATCH_STATS_*` environment variable, see `--help`.

Notes: git counts only cover what is in the tree you point at, so use a full, up-to-date clone (the script warns about shallow or stale trees). Submitted counts depend on patchwork having indexed the patch. The defaults for `--person` and `--carrier` are specific to this team; override them. A person with other addresses than the ones listed will be undercounted.
