import hashlib
import os
import re
from pathlib import Path

import pathspec
import tree_sitter_javascript
import tree_sitter_python
import tree_sitter_typescript
from tree_sitter import Language, Parser

from .bindings import js_bindings, python_bindings

INDEX_VERSION = "tree-sitter-v3"
LANGUAGES = {
    ".py": ("python", Language(tree_sitter_python.language())),
    ".js": ("javascript", Language(tree_sitter_javascript.language())),
    ".jsx": ("javascript", Language(tree_sitter_javascript.language())),
    ".ts": ("typescript", Language(tree_sitter_typescript.language_typescript())),
    ".tsx": ("tsx", Language(tree_sitter_typescript.language_tsx())),
}
TEXT_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".sql",
    ".css",
    ".html",
    ".sh",
    ".ps1",
}
EXCLUDED = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "out",
    "target",
    "vendor",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".ssh",
}
NOISE = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "credentials.json",
    "secrets.json",
    "secrets.yaml",
    "secrets.yml",
}
DECLARATIONS = {
    "function_definition",
    "class_definition",
    "function_declaration",
    "class_declaration",
    "method_definition",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
    "variable_declarator",
}


def parse_file(path: str, content: str) -> dict:
    suffix = Path(path).suffix.lower()
    symbols, imports, references, bindings, identifiers = [], [], [], [], []
    language = LANGUAGES.get(suffix)
    has_errors = False
    if language:
        raw = content.encode("utf-8")
        root = Parser(language[1]).parse(raw).root_node
        has_errors = root.has_error
        stack = [root]
        while stack:
            node = stack.pop()
            stack.extend(reversed(node.named_children))
            text = raw[node.start_byte : node.end_byte].decode("utf-8")
            if node.type in {"identifier", "type_identifier"}:
                identifiers.append(text)
            if node.type in DECLARATIONS:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = raw[name_node.start_byte : name_node.end_byte].decode("utf-8")
                    parent = node.parent
                    exported = parent is not None and parent.type == "export_statement"
                    body_node = node.child_by_field_name("body")
                    signature = (
                        raw[node.start_byte : body_node.start_byte].decode("utf-8").strip()
                        if body_node
                        else text.splitlines()[0]
                    )
                    symbols.append(
                        {
                            "name": name,
                            "kind": node.type,
                            "start_line": node.start_point.row + 1,
                            "end_line": node.end_point.row + 1,
                            "exported": exported,
                            "signature": signature[:500],
                        }
                    )
            if node.type == "import_from_statement":
                match = re.match(r"from\s+(\S+)\s+import", text)
                if match:
                    imports.append(match.group(1))
            elif node.type == "import_statement" and suffix == ".py":
                imports.extend(part.strip().split(" as ")[0] for part in text[7:].split(","))
            elif node.type in {"import_statement", "export_statement"} and suffix != ".py":
                source = node.child_by_field_name("source")
                if source:
                    module = raw[source.start_byte : source.end_byte].decode().strip("\"'")
                    imports.append(module)
                    bindings.extend(js_bindings(node, raw, module))
            elif node.type == "call_expression":
                function = node.child_by_field_name("function")
                if function:
                    call = raw[function.start_byte : function.end_byte].decode()
                    if re.fullmatch(r"[A-Za-z_]\w*", call):
                        references.append(call)
            elif node.type == "call":
                function = node.child_by_field_name("function")
                if function and function.type == "identifier":
                    references.append(raw[function.start_byte : function.end_byte].decode())
    if suffix == ".py":
        bindings = python_bindings(content)
    return {
        "path": path,
        "content": content,
        "hash": hashlib.sha256(content.encode()).hexdigest(),
        "index_version": INDEX_VERSION,
        "language": language[0] if language else "text",
        "symbols": symbols,
        "imports": sorted(set(imports)),
        "references": sorted(set(references)),
        "bindings": bindings,
        "identifiers": sorted(set(identifiers)),
        "parse_errors": has_errors,
        "line_count": len(content.splitlines()),
    }


def inspect_repository(root: Path, previous: dict | None = None, fast: bool = False) -> dict:
    """Read local text safely; reuse unchanged parse records. Nested ignore scopes are isolated."""
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository path must be a directory")
    previous = previous or {}
    result = {}
    ignore_scopes = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        folder = Path(directory)
        inherited = list(ignore_scopes.get(folder, []))
        ignore = folder / ".gitignore"
        if ignore.is_file() and not ignore.is_symlink():
            inherited.append(
                (
                    folder,
                    pathspec.PathSpec.from_lines(
                        "gitwildmatch",
                        ignore.read_text(encoding="utf-8", errors="replace").splitlines(),
                    ),
                )
            )

        def ignored(path: Path, directory: bool = False) -> bool:
            matched = None
            for base, spec in inherited:
                relative = path.relative_to(base).as_posix() + ("/" if directory else "")
                for pattern in spec.patterns:
                    if pattern.include is not None and pattern.match_file(relative):
                        matched = pattern.include
            return bool(matched)

        dirs[:] = sorted(
            d
            for d in dirs
            if d not in EXCLUDED
            and not d.startswith(".env")
            and not (folder / d).is_symlink()
            and not ignored(folder / d, True)
        )
        for child in dirs:
            ignore_scopes[folder / child] = inherited
        for name in sorted(files):
            path = folder / name
            lower = name.lower()
            if (
                path.is_symlink()
                or path.suffix.lower() not in LANGUAGES.keys() | TEXT_EXTENSIONS
                or lower in NOISE
                or lower.startswith((".env", "secret", "credential"))
                or lower.endswith((".min.js", ".min.css", ".d.ts"))
                or ignored(path)
            ):
                continue
            try:
                stat = path.stat()
                if stat.st_size > 1_000_000:
                    continue
                relative = path.relative_to(root).as_posix()
                stamp = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
                old = previous.get(relative)
                if (
                    fast
                    and old
                    and old.get("_stat") == stamp
                    and old.get("index_version") == INDEX_VERSION
                ):
                    result[relative] = old
                    continue
                text = path.read_text(encoding="utf-8")
                if (
                    "\0" in text
                    or ("-----BEGIN " in text and "PRIVATE KEY-----" in text)
                    or re.search(r"@generated|DO NOT EDIT|auto-generated", text[:500], re.I)
                ):
                    continue
            except (OSError, UnicodeError):
                continue
            relative = path.relative_to(root).as_posix()
            digest = hashlib.sha256(text.encode()).hexdigest()
            old = previous.get(relative)
            result[relative] = (
                old
                if old and old["hash"] == digest and old.get("index_version") == INDEX_VERSION
                else parse_file(relative, text)
            )
            if result[relative].get("_stat") != stamp:
                result[relative] = {**result[relative], "_stat": stamp}
    return result
