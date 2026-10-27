#!/usr/bin/env python3
"""Upstream patch stats for one author over a date range.

merged / signoff / reviewed / tested come from `git log` on a kernel tree.
submitted comes from patchwork.kernel.org: every patch email that hit a
mailing list (all revisions and resends) whose author -- the body "From:"
line, falling back to the header From -- is one of --email.  Patches sent
by other people on the author's behalf are found by scanning the series of
the submitters listed in --carrier.

  ./patch-stats.py --tree /path/to/linux      # 2026-01-01 .. today
  ./patch-stats.py --tree /path/to/linux -v   # also list every commit/patch

Every option has an environment variable (shown in --help) so a test machine
can be configured once, e.g. export PATCH_STATS_TREE=/srv/linux.
"""
import argparse, datetime as dt, email, email.policy, email.utils, json, os, re, subprocess, sys
import urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

PW = "https://patchwork.kernel.org"
CACHE = os.path.expanduser("~/.cache/patch-stats")
DEFAULT_EMAILS = "anuj20.g@samsung.com,anuj1072538@gmail.com"
DEFAULT_CARRIERS = "joshi.k@samsung.com,asml.silence@gmail.com,hch@lst.de"


def env_list(name, default):
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def http(url, binary=False, cache=True):
    key = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", url)[-200:])
    if cache and os.path.exists(key):
        return open(key, "rb").read() if binary else open(key).read()
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "patch-stats"}), timeout=60) as r:
                data = r.read()
            break
        except Exception as e:
            if attempt == 3:
                raise
    os.makedirs(CACHE, exist_ok=True)
    open(key, "wb").write(data)
    return data if binary else data.decode("utf-8", "replace")


def pw_list(path, **params):
    page, out = 1, []
    while True:
        q = urllib.parse.urlencode(dict(params, format="json", per_page=100, page=page))
        try:
            chunk = json.loads(http(f"{PW}/api/{path}/?{q}", cache=False))
        except Exception:
            break
        if not chunk:
            break
        out += chunk
        page += 1
    return out


TRAILER = re.compile(r"(?im)^[ \t]*(signed-off-by|reviewed-by|tested-by):[^\n]*?<([^>\n]+)>")


def git_counts(a):
    mine = {e.lower() for e in a.email}
    cmd = ["git", "-C", a.tree, "log", a.ref, "--no-merges", "--since=" + a.since]
    if a.until_given:
        cmd.append("--until=" + a.until + " 23:59:59")
    cmd.append("--format=%H%x1f%ae%x1f%s%x1f%B%x1e")
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=True).stdout
    res = {"merged": [], "signoff": [], "reviewed": [], "tested": []}
    key = {"signed-off-by": "signoff", "reviewed-by": "reviewed", "tested-by": "tested"}
    for rec in out.split("\x1e"):
        f = rec.strip("\n").split("\x1f", 3)
        if len(f) < 4:
            continue
        h, ae, subj, body = f
        line = f"{h[:12]} {subj}"
        if ae.lower() in mine:
            res["merged"].append(line)
        hit = {key[t.lower()] for t, e in TRAILER.findall(body) if e.lower() in mine}
        for k in hit:
            res[k].append(line)
    head = subprocess.run(["git", "-C", a.tree, "log", "-1", "--format=%h %cs", a.ref], capture_output=True, text=True).stdout.strip()
    return res, head


def authors_in_mbox(raw):
    """Yield (subject, author_email, msgid) for each patch message in an mbox."""
    for chunk in re.split(rb"(?m)^From (?=\S+ +\w{3} \w{3} )", raw):
        if not chunk.strip():
            continue
        msg = email.message_from_bytes(chunk.split(b"\n", 1)[1] if chunk.startswith(b"mboxrd") or True else chunk, policy=email.policy.default)
        subj = re.sub(r"\s+", " ", str(msg.get("Subject", "")))
        if re.search(r"\[[^\]]*\b0+/\d+\]", subj) or "PATCH" not in subj.upper():
            continue
        body = msg.get_body(preferencelist=("plain",))
        text = body.get_content() if body else ""
        m = re.match(r"\s*From:\s*(.*)", text)
        who = m.group(1) if m else str(msg.get("From", ""))
        addr = re.search(r"<([^>]+)>", who)
        try:
            when = email.utils.parsedate_to_datetime(str(msg.get("Date", ""))).astimezone(dt.timezone.utc).date().isoformat()
        except Exception:
            when = "????-??-??"
        yield f"{when} {subj}", (addr.group(1) if addr else who.strip()).lower(), str(msg.get("Message-ID", "")).strip()


def submitted(a):
    mine = {e.lower() for e in a.email}
    series, singles = {}, {}
    senders = a.email + a.carrier
    for s in senders:
        for p in pw_list("patches", submitter=s, since=a.since + "T00:00:00", before=a.until + "T23:59:59"):
            if p["series"]:
                series[p["series"][0]["id"]] = p["series"][0].get("mbox") or f"{PW}/series/{p['series'][0]['id']}/mbox/"
            else:
                singles[p["id"]] = p["mbox"]
    urls = list(series.values()) + list(singles.values())
    with ThreadPoolExecutor(8) as ex:
        raws = list(ex.map(lambda u: http(u, binary=True), urls))
    seen = {}
    for raw in raws:
        for subj, addr, mid in authors_in_mbox(raw):
            if addr in mine:
                seen[mid] = subj
    lo, hi = a.since, a.until
    kept = sorted((v, m) for m, v in seen.items() if lo <= v[:10] <= hi)
    return kept, len(series) + len(singles)


def main():
    global PW, CACHE
    E = os.environ.get
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default=E("PATCH_STATS_SINCE", "2026-01-01"), help="YYYY-MM-DD [PATCH_STATS_SINCE]")
    ap.add_argument("--until", default=E("PATCH_STATS_UNTIL"), help="YYYY-MM-DD, default: no upper bound [PATCH_STATS_UNTIL]")
    ap.add_argument("--tree", default=E("PATCH_STATS_TREE", "."), help="linux git repo, default cwd [PATCH_STATS_TREE]")
    ap.add_argument("--ref", default=E("PATCH_STATS_REF", "HEAD"), help="ref to scan, default HEAD i.e. the checked-out tree; never checks anything out [PATCH_STATS_REF]")
    ap.add_argument("--email", action="append", help="author email, repeatable [PATCH_STATS_EMAILS, comma separated]")
    ap.add_argument("--carrier", action="append", help="other submitters whose series may carry your patches, repeatable [PATCH_STATS_CARRIERS, comma separated]")
    ap.add_argument("--patchwork", default=E("PATCH_STATS_PATCHWORK", PW), help="patchwork base URL [PATCH_STATS_PATCHWORK]")
    ap.add_argument("--cache-dir", default=E("PATCH_STATS_CACHE", CACHE), help="HTTP cache dir [PATCH_STATS_CACHE]")
    ap.add_argument("--no-submitted", action="store_true", help="skip patchwork, git counts only")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    a.until_given = bool(a.until)
    a.until = a.until or dt.date.today().isoformat()
    a.email = a.email or env_list("PATCH_STATS_EMAILS", DEFAULT_EMAILS)
    a.carrier = a.carrier or env_list("PATCH_STATS_CARRIERS", DEFAULT_CARRIERS)
    a.tree = os.path.expanduser(a.tree)
    PW, CACHE = a.patchwork.rstrip("/"), os.path.expanduser(a.cache_dir)

    if subprocess.run(["git", "-C", a.tree, "rev-parse", "--verify", "-q", a.ref + "^{commit}"], capture_output=True).returncode:
        sys.exit(f"error: '{a.ref}' not found in git repo '{a.tree}' (use --tree / --ref)")

    g, head = git_counts(a)
    shallow = subprocess.run(["git", "-C", a.tree, "rev-parse", "--is-shallow-repository"], capture_output=True, text=True).stdout.strip() == "true"
    total = subprocess.run(["git", "-C", a.tree, "rev-list", "--count", "--no-merges", "--since=" + a.since] + (["--until=" + a.until + " 23:59:59"] if a.until_given else []) + [a.ref],
                           capture_output=True, text=True).stdout.strip()
    print(f"Period {a.since} .. {a.until if a.until_given else 'now'}   ({a.ref} head: {head}; {total} commits in range)")
    top = subprocess.run(["git", "-C", a.tree, "log", "-1", "--format=%h%x09%ae%x09%ce%x09%cs%x09%P%x09%s", a.ref], capture_output=True, text=True).stdout.rstrip("\n").split("\t")
    if len(top) == 6:
        h, ae, ce, cd, parents, subj = top
        counted = any(l.startswith(h) for l in g["merged"])
        why = ("counted as merged" if counted else
               "NOT counted: merge commit" if len(parents.split()) > 1 else
               f"NOT counted: author {ae} is not in --email {a.email}" if ae.lower() not in {e.lower() for e in a.email} else
               f"NOT counted: committed {cd}, outside {a.since}..{a.until}")
        tb = subprocess.run(["git", "-C", a.tree, "log", "-1", "--format=%B", a.ref], capture_output=True, text=True, errors="replace").stdout
        tr = ", ".join(f"{t}:{e}" for t, e in TRAILER.findall(tb)) or "none"
        print(f"top commit {h} \"{subj[:50]}\" author {ae} committer {ce} {cd}: {why}\n    trailers: {tr}")
    if shallow:
        print("WARNING: shallow clone, git history is truncated so counts are too low (git fetch --unshallow)", file=sys.stderr)
    if total in ("", "0"):
        print(f"WARNING: no commits at all in range on '{a.ref}'; wrong --ref/--tree or stale clone (git fetch)", file=sys.stderr)
    elif head.split()[-1] < a.until and (dt.date.fromisoformat(a.until) - dt.date.fromisoformat(head.split()[-1])).days > 14:
        print(f"WARNING: '{a.ref}' head is {head.split()[-1]}, older than --until; newer commits are missing (git fetch)", file=sys.stderr)
    for k in ("merged", "signoff", "reviewed", "tested"):
        print(f"{k:10s}{len(g[k]):4d}")
        if a.verbose:
            print("\n".join("    " + l for l in g[k]))
    if not a.no_submitted:
        subs, n = submitted(a)
        print(f"{'submitted':10s}{len(subs):4d}   (scanned {n} series/patches)")
        if a.verbose:
            for subj, mid in subs:
                print(f"    {subj}\n        https://lore.kernel.org/all/{urllib.parse.quote(mid.strip('<>'), safe='@')}/")


if __name__ == "__main__":
    main()
