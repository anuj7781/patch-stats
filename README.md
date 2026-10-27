# patch-stats

Counts one author's upstream Linux kernel activity over a date range:

| stat | source |
|---|---|
| merged | commits authored by you in a kernel tree (`git log`) |
| signoff / reviewed / tested | commits carrying your `Signed-off-by` / `Reviewed-by` / `Tested-by` |
| submitted | every patch email you authored on a mailing list, including revisions, resends and patches sent by others on your behalf (patchwork.kernel.org) |

Needs Python 3 (stdlib only), git, and network access to patchwork.

```
./patch-stats.py --tree /path/to/linux --email you@example.com --carrier maintainer@example.org
./patch-stats.py --tree /path/to/linux --email you@example.com -v    # list every commit/patch, with lore links
```

- `--tree` / `--ref`: the repo and ref(s) to scan. Defaults to the current directory and `HEAD`, i.e. whatever is checked out; nothing is ever checked out or fetched. `--ref` can be repeated (e.g. `--ref origin/master --ref origin/for-next`) when your work landed in different trees; each commit is counted once.
- `--since` / `--until`: date range. Default is `2026-01-01` to now.
- `--email` (repeatable): your author addresses.
- `--carrier` (repeatable): other people who post series containing your patches (co-authors, maintainers who forward your work). Patches carried by anyone not listed are not counted as submitted.
- `--no-submitted`: git counts only (no network).

Every option has a `PATCH_STATS_*` environment variable, see `--help`.

Notes: git counts only cover what is in the tree you point at, so use a full, up-to-date clone (the script warns about shallow or stale trees). Submitted counts depend on patchwork having indexed the patch. The defaults for `--email` and `--carrier` are the author's own; override them.
