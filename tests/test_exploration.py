from conceptualize_evaluation.exploration import coverage, exploration


def test_observed_reads_are_conservative_and_ordered():
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "Get-Content shop/auth.py; rg Identity shop; Get-ChildItem shop",
                "exit_code": 0,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "Get-Content shop/auth.py",
                "exit_code": 0,
            },
        },
    ]
    result = exploration(events, ["shop/auth.py", "shop/other.py"])
    assert result["observed_file_reads"] == 2
    assert result["observed_repeated_reads"] == 1
    assert result["observed_files_inspected"] == ["shop/auth.py"]
    assert result["searches"] == 1 and result["directory_listings"] == 1
    assert result["all_file_reads"] is None


def test_coverage_only_counts_source_before_explicit_read():
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "mcp_tool_call",
                "tool": "conceptualize_pack",
                "result": {
                    "structured_content": {
                        "operation": "pack",
                        "included_files": ["shop/auth.py", "shop/noise.py"],
                        "level": "pack",
                        "metrics": {"duplicate_tokens_avoided": 5},
                        "deliveries": [
                            {"path": "shop/auth.py", "level": "pack"},
                            {"path": "shop/noise.py", "level": "pack"},
                        ],
                    }
                },
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "Get-Content shop/auth.py",
                "exit_code": 0,
            },
        },
    ]
    observed = exploration(events, ["shop/auth.py", "shop/noise.py"])
    metrics = coverage(events, observed, {"shop/auth.py"}, True)
    assert metrics["relevant_file_recall_before_observed_read"] == 1.0
    assert metrics["unnecessary_files_surfaced"] == ["shop/noise.py"]
    assert metrics["duplicate_tokens_avoided"] == 5
