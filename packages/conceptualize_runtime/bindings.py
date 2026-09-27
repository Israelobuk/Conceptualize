import ast
import re


def python_bindings(content: str) -> list[dict]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    bindings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            for item in node.names:
                if item.name != "*":
                    bindings.append(
                        {
                            "module": module,
                            "name": item.name,
                            "local": item.asname or item.name,
                            "line": node.lineno,
                        }
                    )
        elif isinstance(node, ast.Import):
            for item in node.names:
                bindings.append(
                    {
                        "module": item.name,
                        "name": "*",
                        "local": item.asname or item.name.split(".")[0],
                        "line": node.lineno,
                    }
                )
    return bindings


def js_bindings(node, raw: bytes, module: str) -> list[dict]:
    result = []
    text = raw[node.start_byte : node.end_byte].decode()
    for match in re.finditer(r"\{([^}]+)\}", text):
        for item in match.group(1).split(","):
            parts = re.sub(r"^\s*type\s+", "", item.strip()).split(" as ")
            if re.fullmatch(r"\w+", parts[0]):
                result.append(
                    {
                        "module": module,
                        "name": parts[0],
                        "local": parts[-1].strip(),
                        "line": node.start_point.row + 1,
                    }
                )
    default = re.match(r"import\s+(?!type\b)(\w+)\s*(?:,|from)", text)
    namespace = re.search(r"\*\s+as\s+(\w+)", text)
    if default:
        result.append(
            {
                "module": module,
                "name": "default",
                "local": default.group(1),
                "line": node.start_point.row + 1,
            }
        )
    if namespace:
        result.append(
            {
                "module": module,
                "name": "*",
                "local": namespace.group(1),
                "line": node.start_point.row + 1,
            }
        )
    return result
