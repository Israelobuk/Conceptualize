from conceptualize.service import git_signature


def test_shared_worktree_refs_invalidate_git_metadata(tmp_path):
    common = tmp_path / "storage"
    gitdir = common / "worktrees/w1"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/feature\n")
    (gitdir / "commondir").write_text("../..\n")
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".git").write_text(f"gitdir: {gitdir}\n")
    refs = common / "refs/remotes/origin"
    refs.mkdir(parents=True)
    base = refs / "main"
    base.write_text("0" * 40)
    before = git_signature(root)
    base.write_text("1" * 40 + "\n")
    assert git_signature(root) != before
