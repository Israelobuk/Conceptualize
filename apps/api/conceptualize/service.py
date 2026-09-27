import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Callable

from conceptualize_runtime.git import metadata
from conceptualize_runtime.index import inspect_repository
from conceptualize_runtime.runtime import ContextRuntime, token_count
from sqlalchemy import select

from .models import Project, Repository, RepositoryFile, now
from .telemetry import tracer


def index_project(
    db,
    project: Project,
    root: Path,
    base: str | None = None,
    incremental: bool = False,
    commit: bool = True,
) -> dict:
    root = root.resolve(strict=True)
    project = db.scalar(
        select(Project)
        .where(Project.id == project.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # V1 intentionally has one repository per project: paths are unambiguous across MCP calls.
    repository = db.scalar(select(Repository).where(Repository.project_id == project.id))
    if repository and repository.root != str(root):
        raise ValueError("This MVP supports one repository per project; create another project")
    repository = repository or Repository(project_id=project.id, root=str(root))
    db.add(repository)
    db.flush()
    rows = list(
        db.scalars(select(RepositoryFile).where(RepositoryFile.repository_id == repository.id))
    )
    previous = {row.path: {**row.structure, "content": row.content} for row in rows}
    with tracer.start_as_current_span("repository.index") as span:
        scan_started = perf_counter()
        files = inspect_repository(root, previous, fast=incremental)
        scan_ms = (perf_counter() - scan_started) * 1000
        signature = git_signature(root)
        git_started = perf_counter()
        content_changed = {p: f["hash"] for p, f in files.items()} != {
            p: f["hash"] for p, f in previous.items()
        }
        git_info = (
            metadata(root, base)
            if not incremental
            or content_changed
            or repository.git_info.get("_disk_signature") != signature
            else dict(repository.git_info)
        )
        git_info["_disk_signature"] = signature
        git_ms = (perf_counter() - git_started) * 1000
        digest = hashlib.sha256(
            json.dumps(
                {
                    "files": [(p, f["hash"], f["index_version"]) for p, f in sorted(files.items())],
                    "git": git_info,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        by_path = {row.path: row for row in rows}
        changed = 0
        for path, record in files.items():
            old = by_path.get(path)
            if (
                old
                and old.content_hash == record["hash"]
                and old.structure.get("index_version") == record["index_version"]
            ):
                if old.structure.get("_stat") != record.get("_stat"):
                    old.structure = {k: v for k, v in record.items() if k != "content"}
                continue
            row = old or RepositoryFile(repository_id=repository.id, path=path)
            row.content = record["content"]
            row.content_hash = record["hash"]
            row.structure = {k: v for k, v in record.items() if k != "content"}
            row.token_count = token_count(record["content"])
            db.add(row)
            changed += 1
        removed = set(by_path) - set(files)
        for path in removed:
            db.delete(by_path[path])
        if repository.state_hash != digest:
            project.revision += 1
        repository.state_hash = digest
        repository.git_info = git_info
        repository.indexed_at = now()
        span.set_attribute("project.id", project.id)
        span.set_attribute("index.files", len(files))
        if commit:
            db.commit()
        else:
            db.flush()
    return {
        "files": len(files),
        "symbols": sum(len(f["symbols"]) for f in files.values()),
        "languages": sorted({f["language"] for f in files.values() if f.get("language")}),
        "changed_files": changed,
        "deleted_files": len(removed),
        "revision": project.revision,
        "repository_id": repository.id,
        "git_available": git_info["available"],
        "git_branch": git_info.get("branch"),
        "index_lookup_ms": scan_ms,
        "git_ms": git_ms,
    }


def project_runtime(db, project_id: str) -> tuple[ContextRuntime, Repository | None]:
    repository = db.scalar(select(Repository).where(Repository.project_id == project_id))
    files = {}
    if repository:
        rows = db.scalars(
            select(RepositoryFile).where(RepositoryFile.repository_id == repository.id)
        )
        files = {r.path: {**r.structure, "content": r.content} for r in rows}
    return ContextRuntime(files, repository.git_info if repository else {}), repository


class SourceFreshnessRegistry:
    """Dispatch freshness checks only to requested source providers."""

    def __init__(self) -> None:
        self._strategies: dict[str, Callable] = {}
        self._aliases = {"repository_file": "repository", "code_symbol": "repository"}

    def register(self, source_type: str, strategy: Callable) -> None:
        self._strategies[source_type] = strategy

    def refresh(
        self,
        db,
        project: Project,
        requested_sources: set[str],
        *,
        force_refresh: bool,
        source_snapshots: dict | None = None,
    ) -> dict:
        results = {"git_ms": 0}
        snapshots = source_snapshots or {}
        checked = set()
        for source_type in sorted(requested_sources):
            provider = self._aliases.get(source_type, source_type)
            if provider in checked:
                continue
            checked.add(provider)
            strategy = self._strategies.get(provider)
            if strategy is not None:
                results.update(
                    strategy(
                        db,
                        project,
                        force_refresh=force_refresh,
                        source_snapshot=snapshots.get(provider),
                    )
                )
        return results


def _refresh_repository(db, project: Project, *, force_refresh: bool, source_snapshot=None) -> dict:
    if source_snapshot is None:
        return {"git_ms": 0}
    return index_project(
        db,
        project,
        Path(source_snapshot.root),
        source_snapshot.git_info.get("base"),
        incremental=not force_refresh,
        commit=False,
    )


source_freshness = SourceFreshnessRegistry()
source_freshness.register("repository", _refresh_repository)


def git_signature(root):
    for parent in [root, *root.parents]:
        gitdir = parent / ".git"
        if gitdir.is_file():
            try:
                text = gitdir.read_text().strip()
                gitdir = (parent / text.removeprefix("gitdir: ").strip()).resolve()
            except OSError:
                return []
        if gitdir.is_dir():
            head = gitdir / "HEAD"
            try:
                ref = head.read_text().strip().removeprefix("ref: ")
                common_file = gitdir / "commondir"
                common = (gitdir / common_file.read_text().strip()).resolve() if common_file.is_file() else gitdir
                candidates = [
                    head,
                    gitdir / ref,
                    gitdir / "index",
                    gitdir / "packed-refs",
                    gitdir / "config",
                    gitdir / "refs/heads/main",
                    gitdir / "refs/heads/master",
                    common_file,
                    common / "packed-refs",
                    common / "config",
                ]
                candidates += list((common / "refs").rglob("*"))
                return [
                    [str(p), p.stat().st_mtime_ns, p.stat().st_size]
                    for p in sorted(set(candidates))
                    if p.is_file()
                ]
            except OSError:
                return []
    return []
