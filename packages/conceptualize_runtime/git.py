import subprocess
from collections import Counter
from pathlib import Path


def git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def metadata(root: Path, base: str | None = None) -> dict:
    head = git(root, "rev-parse", "HEAD")
    if not head:
        return {
            "available": False,
            "head": None,
            "changed_files": [],
            "commits": [],
            "cochanges": [],
        }
    changed = git(root, "diff", "--name-only", "HEAD").splitlines()
    changed += git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    working_tree = sorted(set(changed))
    branch = git(root, "branch", "--show-current")
    if base is None:
        for candidate in ("origin/main", "main", "origin/master", "master"):
            if candidate != branch and git(root, "rev-parse", "--verify", candidate + "^{commit}"):
                base = candidate
                break
    branch_changed = []
    merge_base = git(root, "merge-base", base, "HEAD") if base else ""
    base_diff = ""
    if base:
        if base.startswith("-"):
            raise ValueError("Git base must be a ref, not an option")
        if not git(root, "rev-parse", "--verify", base + "^{commit}"):
            raise ValueError("Git base does not resolve to a commit")
        branch_changed = git(root, "diff", "--name-only", f"{base}...HEAD").splitlines()
        changed += branch_changed
        base_diff = git(root, "diff", "--stat", f"{base}...HEAD")[:10000]
    log = git(root, "log", "-20", "--format=COMMIT:%H|%aI|%s", "--name-only")
    commits = []
    for line in log.splitlines():
        if line.startswith("COMMIT:"):
            sha, timestamp, subject = line[7:].split("|", 2)
            commits.append({"sha": sha, "timestamp": timestamp, "subject": subject, "files": []})
        elif line and commits:
            commits[-1]["files"].append(line)
    pairs = Counter()
    for commit in commits:
        paths = sorted(commit["files"])[:50]
        for i, a in enumerate(paths):
            for b in paths[i + 1 :]:
                pairs[(a, b)] += 1
    return {
        "available": True,
        "head": head,
        "branch": branch,
        "working_tree_files": working_tree,
        "branch_changed_files": sorted(set(branch_changed)),
        "merge_base": merge_base or None,
        "base": base,
        "base_diff_stat": base_diff,
        "changed_files": sorted(set(changed)),
        "commits": commits,
        "cochanges": [
            {"files": list(pair), "count": count} for pair, count in pairs.most_common(30)
        ],
    }
