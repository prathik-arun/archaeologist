"""
Surgical function deletion engine.
Uses the AST byte ranges from tree-sitter to remove functions
cleanly — including decorators, docstrings, and trailing blank lines.
"""
import re
from pathlib import Path
from dataclasses import dataclass

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_ruby as tsruby
import tree_sitter_go as tsgo
import tree_sitter_java as tsjava
import tree_sitter_rust as tsrust
import tree_sitter_kotlin as tskotlin
import tree_sitter_swift as tsswift
from tree_sitter import Language, Parser

LANGUAGES = {
    "python":     Language(tspython.language()),
    "javascript": Language(tsjavascript.language()),
    "ruby":       Language(tsruby.language()),
    "go":         Language(tsgo.language()),
    "java":       Language(tsjava.language()),
    "rust":       Language(tsrust.language()),
    "kotlin":     Language(tskotlin.language()),
    "swift":      Language(tsswift.language()),
}


@dataclass
class DeletionRange:
    """The exact byte range to delete for a function, including decorators."""
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    name: str


def _get_parser(lang: str) -> Parser:
    return Parser(LANGUAGES[lang])


def _find_function_range_python(source: bytes, func_name: str, target_line: int) -> DeletionRange | None:
    """Find the full byte range of a Python function including its decorators."""
    parser = _get_parser("python")
    tree = parser.parse(source)

    def walk(node):
        if node.type in ("function_definition", "async_function_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                actual_line = node.start_point[0] + 1
                if name == func_name and abs(actual_line - target_line) <= 3:
                    # Walk back to include decorators
                    start_byte = node.start_byte
                    start_line = node.start_point[0] + 1
                    parent = node.parent
                    if parent:
                        siblings = parent.children
                        for i, sib in enumerate(siblings):
                            if sib == node:
                                # look back for decorators
                                j = i - 1
                                while j >= 0:
                                    prev = siblings[j]
                                    if prev.type == "decorator":
                                        start_byte = prev.start_byte
                                        start_line = prev.start_point[0] + 1
                                        j -= 1
                                    elif prev.type in ("comment", "expression_statement"):
                                        j -= 1
                                    else:
                                        break
                                break
                    return DeletionRange(
                        start_byte=start_byte,
                        end_byte=node.end_byte,
                        start_line=start_line,
                        end_line=node.end_point[0] + 1,
                        name=func_name,
                    )
        for child in node.children:
            result = walk(child)
            if result:
                return result
        return None

    return walk(tree.root_node)


def _find_function_range_treesitter(
    source: bytes, func_name: str, target_line: int,
    lang: str, func_node_types: list[str], name_field: str = "name"
) -> DeletionRange | None:
    """Generic tree-sitter based function range finder."""
    parser = _get_parser(lang)
    tree = parser.parse(source)

    def walk(node):
        if node.type in func_node_types:
            name_node = node.child_by_field_name(name_field)
            if name_node is None:
                # fallback: find first identifier/simple_identifier child
                for c in node.children:
                    if c.type in ("identifier", "simple_identifier"):
                        name_node = c
                        break
            if name_node:
                name = source[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                actual_line = node.start_point[0] + 1
                if name == func_name and abs(actual_line - target_line) <= 5:
                    return DeletionRange(
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        name=func_name,
                    )
        for child in node.children:
            result = walk(child)
            if result:
                return result
        return None

    return walk(tree.root_node)


def _find_function_range_dart(source_text: str, func_name: str, target_line: int) -> DeletionRange | None:
    """Find dart function range using line-based approach."""
    lines = source_text.split("\n")

    # Find the line where the function starts (near target_line)
    func_pattern = re.compile(
        r'^[\s]*(?:(?:static|async|external|abstract)\s+)*'
        r'(?:[\w<>\[\]?,\s]+?\s+)?' +
        re.escape(func_name) +
        r'\s*(?:<[^>]*>)?\s*\([^)]*\)'
    )

    start_line = None
    for i in range(max(0, target_line - 5), min(len(lines), target_line + 5)):
        if func_pattern.match(lines[i]) or (func_name + "(") in lines[i] or (func_name + " (") in lines[i]:
            start_line = i
            break

    if start_line is None:
        return None

    # Walk back to include annotations (@override etc.)
    actual_start = start_line
    for i in range(start_line - 1, max(0, start_line - 5), -1):
        stripped = lines[i].strip()
        if stripped.startswith("@") or stripped == "":
            actual_start = i
        else:
            break

    # Walk forward to find the end of the function body
    # Count braces to find matching close
    end_line = start_line
    brace_count = 0
    found_open = False

    for i in range(start_line, min(len(lines), start_line + 500)):
        for char in lines[i]:
            if char == "{":
                brace_count += 1
                found_open = True
            elif char == "}":
                brace_count -= 1
        if found_open and brace_count == 0:
            end_line = i
            break
        # arrow function: ends with semicolon
        if not found_open and "=>" in lines[i] and lines[i].rstrip().endswith(";"):
            end_line = i
            break

    # Convert line numbers to byte offsets
    byte_offset = 0
    line_starts = [0]
    for line in lines:
        byte_offset += len(line.encode("utf-8")) + 1
        line_starts.append(byte_offset)

    start_byte = line_starts[actual_start] if actual_start < len(line_starts) else 0
    end_byte = line_starts[end_line + 1] if end_line + 1 < len(line_starts) else len(source_text.encode("utf-8"))

    return DeletionRange(
        start_byte=start_byte,
        end_byte=end_byte,
        start_line=actual_start + 1,
        end_line=end_line + 1,
        name=func_name,
    )


LANG_CONFIG = {
    "python": None,  # handled separately
    "javascript": (["function_declaration"], "name"),
    "ruby": (["method"], "name"),
    "go": (["function_declaration", "method_declaration"], "name"),
    "java": (["method_declaration"], "name"),
    "rust": (["function_item"], "name"),
    "kotlin": (["function_declaration"], None),
    "swift": (["function_declaration"], None),
    "dart": None,  # handled separately
}


def find_deletion_range(filepath: str, func_name: str, target_line: int, language: str) -> DeletionRange | None:
    """Find the exact byte range to delete for a given function."""
    try:
        if language == "python":
            source = Path(filepath).read_bytes()
            return _find_function_range_python(source, func_name, target_line)

        elif language == "dart":
            source_text = Path(filepath).read_text(encoding="utf-8", errors="replace")
            return _find_function_range_dart(source_text, func_name, target_line)

        else:
            config = LANG_CONFIG.get(language)
            if config is None:
                return None
            node_types, name_field = config
            source = Path(filepath).read_bytes()
            return _find_function_range_treesitter(
                source, func_name, target_line, language, node_types, name_field or "name"
            )
    except Exception as e:
        return None


def delete_function_from_file(filepath: str, deletion: DeletionRange) -> bool:
    """
    Remove a function from a file using byte-precise deletion.
    Cleans up surrounding blank lines to avoid leaving gaps.
    Returns True if successful.
    """
    try:
        source = Path(filepath).read_bytes()
        before = source[:deletion.start_byte]
        after = source[deletion.end_byte:]

        # Clean up: remove leading blank line if there's one before the function
        before_str = before.decode("utf-8", errors="replace")
        after_str = after.decode("utf-8", errors="replace")

        # Strip trailing whitespace/newlines from before
        before_stripped = before_str.rstrip(" \t")
        if before_stripped.endswith("\n\n"):
            before_str = before_stripped
        elif before_stripped.endswith("\n"):
            before_str = before_stripped

        # Strip leading blank lines from after
        after_str = after_str.lstrip("\n")
        if after_str and not after_str.startswith("\n"):
            after_str = "\n" + after_str

        result = before_str + after_str
        Path(filepath).write_text(result, encoding="utf-8")
        return True
    except Exception:
        return False


def preview_deletion(filepath: str, deletion: DeletionRange, context_lines: int = 2) -> str:
    """Return a preview of what will be deleted."""
    try:
        lines = Path(filepath).read_text(encoding="utf-8", errors="replace").split("\n")
        start = max(0, deletion.start_line - 1)
        end = min(len(lines), deletion.end_line)
        deleted = lines[start:end]
        preview = "\n".join(f"  - {l}" for l in deleted[:8])
        if len(deleted) > 8:
            preview += f"\n  ... ({len(deleted) - 8} more lines)"
        return preview
    except Exception:
        return "(preview unavailable)"
