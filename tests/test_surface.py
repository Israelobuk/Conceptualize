from conceptualize_evaluation.surface import profile_surface


def test_surface_profile_counts_schema_bytes_without_claiming_model_tokens():
    surface = {"tools": [{"name": "inspect", "description": "hello", "inputSchema": {"type": "object"}, "outputSchema": {"type": "string"}}],
               "initialization": {"instructions": "Use around known targets"}}
    result = profile_surface(surface)
    assert result["description_characters"] == 5
    assert result["schema_bytes"] > 0
    assert result["model_visible_tokens"] is None
    assert result["tools"] == 1
