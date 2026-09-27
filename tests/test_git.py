import subprocess

from conceptualize_runtime.git import metadata


def test_git_history_current_changes_and_base_diff(tmp_path):
    def run(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    run("init")
    run("config", "user.name", "Test")
    run("config", "user.email", "test@localhost")
    (tmp_path / "auth.py").write_text("def login(): pass")
    (tmp_path / "tokens.py").write_text("def verify(): pass")
    run("add", ".")
    run("commit", "-m", "Add auth")
    run("branch", "baseline")
    (tmp_path / "auth.py").write_text("def login(): return True")
    run("add", ".")
    run("commit", "-m", "Update auth")
    (tmp_path / "tokens.py").write_text("def verify(): return True")
    result = metadata(tmp_path, "baseline")
    assert set(result["changed_files"]) == {"auth.py", "tokens.py"}
    assert result["commits"][0]["subject"] == "Update auth"
    assert result["cochanges"][0]["files"] == ["auth.py", "tokens.py"]
    assert "auth.py" in result["base_diff_stat"]


def test_git_automatically_compares_current_branch_to_main(tmp_path):
    def run(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    run("init", "-b", "main")
    run("config", "user.name", "Test")
    run("config", "user.email", "test@localhost")
    (tmp_path / "base.py").write_text("value = 1")
    run("add", ".")
    run("commit", "-m", "Baseline")
    run("checkout", "-b", "feature")
    (tmp_path / "branch.py").write_text("branch = 1")
    run("add", ".")
    run("commit", "-m", "Branch change")
    (tmp_path / "base.py").write_text("value = 2")
    result = metadata(tmp_path)
    assert result["base"] == "main"
    assert result["branch_changed_files"] == ["branch.py"]
    assert result["working_tree_files"] == ["base.py"]
    assert result["merge_base"] == run("rev-parse", "main")
