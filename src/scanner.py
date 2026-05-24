import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

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

EXT_MAP = {
    ".py":   "python",
    ".js":   "javascript",
    ".ts":   "javascript",
    ".jsx":  "javascript",
    ".tsx":  "javascript",
    ".rb":   "ruby",
    ".go":   "go",
    ".java": "java",
    ".rs":   "rust",
    ".kt":   "kotlin",
    ".kts":  "kotlin",
    ".swift":"swift",
    ".dart": "dart",
}

FALSE_POSITIVE_NAMES = {
    # Python
    "__init__", "__str__", "__repr__", "__len__", "__eq__", "__hash__",
    "__enter__", "__exit__", "__iter__", "__next__", "__call__",
    "__get__", "__set__", "__delete__", "__getattr__", "__setattr__",
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "main", "cli", "app", "create_app", "application", "handler",
    "lambda_handler", "index",
    # Flutter/Dart
    "build", "initState", "dispose", "setState", "didChangeDependencies",
    "didUpdateWidget", "deactivate", "createState",
    "debugFillProperties", "reassemble", "didChangeAppLifecycleState",
    "didChangePlatformBrightness", "didChangeLocales",
    "didChangeMetrics", "didChangeTextScaleFactor",
    "performAction", "performCustomAction",
    # Flutter routing
    "generateRoute", "onGenerateRoute", "onUnknownRoute",
    # showDialog is a Flutter framework function, not user-defined dead code
    "showDialog", "showModalBottomSheet", "showBottomSheet",
    "showMenu", "showSearch", "showDatePicker", "showTimePicker",
    "showAboutDialog", "showLicensePage",
    # Go
    "init", "Main",
    # Java/Kotlin — Android lifecycle
    "onCreate", "onStart", "onResume", "onPause", "onStop", "onDestroy",
    "onCreateView", "onViewCreated", "onActivityCreated",
    "onRequestPermissionsResult", "onActivityResult",
    "onNewIntent", "onBackPressed", "onOptionsItemSelected",
    "onCreateOptionsMenu", "onPrepareOptionsMenu",
    "toString", "equals", "hashCode", "compareTo",
    # Flutter Android embedding
    "attachBaseContext", "registerWith", "configureFlutterEngine",
    "cleanUpFlutterEngine", "provideFlutterEngine",
    # Swift / macOS
    "viewDidLoad", "viewWillAppear", "viewDidAppear",
    "viewWillDisappear", "viewDidDisappear",
    "awakeFromNib", "prepareForSegue",
    "applicationDidFinishLaunching", "applicationWillTerminate",
    "applicationShouldTerminate", "applicationSupportsSecureRestorableState",
    "applicationWillBecomeActive", "applicationDidBecomeActive",
    "applicationWillResignActive", "applicationDidResignActive",
    "applicationDidHide", "applicationWillUnhide",
    "windowWillClose", "windowDidBecomeKey", "windowDidResignKey",
    # LLDB / debug helpers
    "__lldb_init_module", "__lldb_typesummary_impl",
    # Rust
    "new", "fmt", "from", "into", "default",
}

FALSE_POSITIVE_DECORATORS = {
    "route", "get", "post", "put", "delete", "patch",
    "app.route", "blueprint.route",
    "pytest.fixture", "fixture",
    "property", "staticmethod", "classmethod",
    "task", "celery.task", "shared_task",
    "signal", "receiver",
    "click.command", "command", "cli.command",
    "abstractmethod", "override", "Override",
    "Test", "test", "Before", "After", "BeforeEach", "AfterEach",
}


@dataclass
class FunctionDef:
    name: str
    file: str
    line: int
    language: str
    decorators: list = field(default_factory=list)
    is_test: bool = False
    is_entry_point: bool = False


@dataclass
class ScanResult:
    definitions: dict = field(default_factory=dict)
    calls: dict = field(default_factory=dict)
    all_called_names: set = field(default_factory=set)


def _is_test_file(path: str) -> bool:
    p = Path(path)
    parts_lower = [x.lower() for x in p.parts]
    name_lower = p.name.lower()
    return (
        name_lower.startswith("test_") or
        name_lower.endswith("_test.py") or
        name_lower.endswith("_test.dart") or
        name_lower.endswith("_test.go") or
        name_lower.endswith("_spec.rb") or
        name_lower.endswith("test.kt") or
        name_lower.endswith("tests.swift") or
        "test" in parts_lower or
        "tests" in parts_lower or
        "spec" in parts_lower or
        "__tests__" in parts_lower
    )


def _make_parser(lang_name: str) -> Parser:
    return Parser(LANGUAGES[lang_name])


# ── tree-sitter helpers ───────────────────────────────────────────────────────

def _text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _child_field(node, field_name):
    return node.child_by_field_name(field_name)


def _extract_py_decorators(node, source: bytes) -> list:
    decorators = []
    parent = node.parent
    if parent is None:
        return decorators
    for sib in parent.children:
        if sib.end_byte <= node.start_byte and sib.type == "decorator":
            dec = _text(sib, source).lstrip("@").strip().split("(")[0].strip()
            decorators.append(dec)
    return decorators


# ── Python ────────────────────────────────────────────────────────────────────

def scan_python_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("python")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type in ("function_definition", "async_function_definition"):
            name_node = _child_field(node, "name")
            if name_node:
                name = _text(name_node, source)
                decorators = _extract_py_decorators(node, source)
                dec_bases = {d.split(".")[-1] for d in decorators}
                entry = (
                    name in FALSE_POSITIVE_NAMES or
                    bool(dec_bases & FALSE_POSITIVE_DECORATORS) or
                    is_test or name.startswith("test_")
                )
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="python",
                    decorators=decorators,
                    is_test=is_test or name.startswith("test_"),
                    is_entry_point=entry,
                ))
        if node.type == "call":
            fn = _child_field(node, "function")
            if fn:
                if fn.type == "identifier":
                    calls.add(_text(fn, source))
                elif fn.type == "attribute":
                    attr = _child_field(fn, "attribute")
                    if attr:
                        calls.add(_text(attr, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── JavaScript / TypeScript ───────────────────────────────────────────────────

def scan_js_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("javascript")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "function_declaration":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="javascript",
                    is_test=is_test or name.startswith("test") or name in ("it", "describe"),
                    is_entry_point=name in FALSE_POSITIVE_NAMES,
                ))
        if node.type in ("variable_declarator", "assignment_expression"):
            vf = "value" if node.type == "variable_declarator" else "right"
            val = _child_field(node, vf)
            if val and val.type in ("arrow_function", "function"):
                nf = "name" if node.type == "variable_declarator" else "left"
                nn = _child_field(node, nf)
                if nn and nn.type == "identifier":
                    name = _text(nn, source)
                    defs.append(FunctionDef(
                        name=name, file=filepath,
                        line=node.start_point[0] + 1,
                        language="javascript",
                        is_test=is_test,
                        is_entry_point=name in FALSE_POSITIVE_NAMES,
                    ))
        if node.type == "call_expression":
            fn = _child_field(node, "function")
            if fn:
                if fn.type == "identifier":
                    calls.add(_text(fn, source))
                elif fn.type == "member_expression":
                    prop = _child_field(fn, "property")
                    if prop:
                        calls.add(_text(prop, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Ruby ──────────────────────────────────────────────────────────────────────

def scan_ruby_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("ruby")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "method":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                entry = name in FALSE_POSITIVE_NAMES or is_test
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="ruby",
                    is_test=is_test,
                    is_entry_point=entry,
                ))
        if node.type == "call":
            meth = _child_field(node, "method")
            if meth:
                calls.add(_text(meth, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Go ────────────────────────────────────────────────────────────────────────

def scan_go_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("go")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "function_declaration":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                entry = name in FALSE_POSITIVE_NAMES or name in ("main", "init") or (is_test and name.startswith("Test"))
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="go",
                    is_test=is_test or name.startswith("Test") or name.startswith("Benchmark"),
                    is_entry_point=entry,
                ))
        if node.type == "method_declaration":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="go",
                    is_test=is_test,
                    is_entry_point=name in FALSE_POSITIVE_NAMES,
                ))
        if node.type == "call_expression":
            fn = _child_field(node, "function")
            if fn:
                if fn.type == "identifier":
                    calls.add(_text(fn, source))
                elif fn.type == "selector_expression":
                    sel = _child_field(fn, "field")
                    if sel:
                        calls.add(_text(sel, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Java ──────────────────────────────────────────────────────────────────────

def scan_java_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("java")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "method_declaration":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                # check for @Override, @Test annotations on parent
                annots = []
                if node.parent:
                    for sib in node.parent.children:
                        if sib.end_byte <= node.start_byte and sib.type == "modifiers":
                            annots = [_text(a, source).lstrip("@") for a in sib.children if a.type == "marker_annotation"]
                entry = (
                    name in FALSE_POSITIVE_NAMES or
                    is_test or
                    "Override" in annots or
                    name.startswith("test") or
                    "Test" in annots
                )
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="java",
                    decorators=annots,
                    is_test=is_test or "Test" in annots or name.startswith("test"),
                    is_entry_point=entry,
                ))
        if node.type == "method_invocation":
            nn = _child_field(node, "name")
            if nn:
                calls.add(_text(nn, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Rust ──────────────────────────────────────────────────────────────────────

def scan_rust_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("rust")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "function_item":
            nn = _child_field(node, "name")
            if nn:
                name = _text(nn, source)
                # check #[test], #[cfg(test)] attributes
                attrs = []
                if node.parent:
                    for sib in node.parent.children:
                        if sib.end_byte <= node.start_byte and sib.type == "attribute_item":
                            attrs.append(_text(sib, source))
                is_t = is_test or any("test" in a for a in attrs)
                entry = name in FALSE_POSITIVE_NAMES or is_t or name == "main"
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="rust",
                    decorators=attrs,
                    is_test=is_t,
                    is_entry_point=entry,
                ))
        if node.type == "call_expression":
            fn = node.children[0] if node.children else None
            if fn and fn.type == "identifier":
                calls.add(_text(fn, source))
            elif fn and fn.type == "field_expression":
                field = _child_field(fn, "field")
                if field:
                    calls.add(_text(field, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Kotlin ────────────────────────────────────────────────────────────────────

def scan_kotlin_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("kotlin")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type == "function_declaration":
            nn = _child_field(node, "simple_identifier") or _child_field(node, "name")
            # fallback: find first simple_identifier child
            if nn is None:
                for c in node.children:
                    if c.type == "simple_identifier":
                        nn = c
                        break
            if nn:
                name = _text(nn, source)
                entry = name in FALSE_POSITIVE_NAMES or is_test or name.startswith("test")
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="kotlin",
                    is_test=is_test or name.startswith("test"),
                    is_entry_point=entry,
                ))
        if node.type == "call_expression":
            fn = node.children[0] if node.children else None
            if fn:
                if fn.type == "simple_identifier":
                    calls.add(_text(fn, source))
                elif fn.type == "navigation_expression":
                    for c in fn.children:
                        if c.type == "simple_identifier":
                            calls.add(_text(c, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Swift ─────────────────────────────────────────────────────────────────────

def scan_swift_file(filepath: str):
    source = Path(filepath).read_bytes()
    parser = _make_parser("swift")
    tree = parser.parse(source)
    defs, calls = [], set()
    is_test = _is_test_file(filepath)

    def walk(node):
        if node.type in ("function_declaration", "protocol_function_declaration"):
            nn = None
            for c in node.children:
                if c.type == "simple_identifier":
                    nn = c
                    break
            if nn:
                name = _text(nn, source)
                entry = name in FALSE_POSITIVE_NAMES or is_test or name.startswith("test")
                defs.append(FunctionDef(
                    name=name, file=filepath,
                    line=node.start_point[0] + 1,
                    language="swift",
                    is_test=is_test or name.startswith("test"),
                    is_entry_point=entry,
                ))
        if node.type == "call_expression":
            fn = node.children[0] if node.children else None
            if fn and fn.type == "simple_identifier":
                calls.add(_text(fn, source))
        for c in node.children:
            walk(c)

    walk(tree.root_node)
    return defs, calls


# ── Dart (regex-based — no PyPI package available) ────────────────────────────

# Match function definitions: return_type? name(params) { or =>
_DART_FUNC_RE = re.compile(
    r'(?m)^[ 	]*'
    r'(?:(?:static|async|external|abstract|@override)\s+)*'
    r'(?:(?:void|bool|int|double|String|dynamic|Future|Stream|List|Map|Set|Widget|'
    r'BuildContext|State|[\w<>\[\]?,\s]+?)\s+)?'
    r'([a-z_][a-zA-Z0-9_]*)\s*'   # name — must start lowercase
    r'(?:<[^>]*>)?\s*'
    r'\([^)]*\)'
    r'(?:\s*(?:async|sync\*))?'
    r'\s*(?:\{|=>)',
)

# Match only lowercase function calls — excludes constructors (UpperCase)
_DART_CALL_RE = re.compile(r'\b([a-z_][a-zA-Z0-9_]*)\s*\(')

_DART_SKIP_KEYWORDS = {
    "if", "for", "while", "switch", "return", "assert", "await",
    "void", "int", "bool", "double", "var", "final", "const",
    "super", "this", "new", "catch", "else",
}

DART_ENTRY_POINTS = FALSE_POSITIVE_NAMES | {
    "build", "createState", "initState", "dispose",
    "didChangeDependencies", "didUpdateWidget", "deactivate",
    "debugFillProperties", "noSuchMethod", "toString",
    "main", "setUp", "tearDown",
}


def scan_dart_file(filepath: str):
    source_text = Path(filepath).read_text(encoding="utf-8", errors="replace")
    is_test = _is_test_file(filepath)
    defs, calls = [], set()

    for m in _DART_FUNC_RE.finditer(source_text):
        name = m.group(1)
        if not name or name in _DART_SKIP_KEYWORDS:
            continue
        line = source_text[:m.start()].count("\n") + 1
        snippet = source_text[max(0, m.start() - 120):m.start()]
        has_override = "@override" in snippet.lower()
        entry = name in DART_ENTRY_POINTS or has_override or is_test or name.startswith("test")
        defs.append(FunctionDef(
            name=name, file=filepath,
            line=line,
            language="dart",
            is_test=is_test or name.startswith("test"),
            is_entry_point=entry,
        ))

    for m in _DART_CALL_RE.finditer(source_text):
        name = m.group(1)
        if name not in _DART_SKIP_KEYWORDS:
            calls.add(name)

    return defs, calls


# ── Directory scanner ─────────────────────────────────────────────────────────

SCANNER_MAP = {
    "python":     scan_python_file,
    "javascript": scan_js_file,
    "ruby":       scan_ruby_file,
    "go":         scan_go_file,
    "java":       scan_java_file,
    "rust":       scan_rust_file,
    "kotlin":     scan_kotlin_file,
    "swift":      scan_swift_file,
    "dart":       scan_dart_file,
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", "migrations",
    ".next", "coverage", ".dart_tool", ".pub-cache", ".pub",
    "Pods", ".gradle", ".idea", "target", "out", "bin", "obj",
    ".build", "DerivedData", "Carthage", "vendor", "third_party",
    # Flutter generated/ephemeral dirs — never user code
    "ephemeral", "generated", "generated_plugin_registrant",
    "flutter_export_environment", ".plugin_symlinks",
    "GeneratedPluginRegistrant",
}

# File patterns to skip entirely (generated files)
SKIP_FILE_PATTERNS = {
    "generated_plugin_registrant.dart",
    "generated_plugin_registrant.swift",
    "generated_plugin_registrant.java",
    "GeneratedPluginRegistrant.java",
    "GeneratedPluginRegistrant.m",
    "flutter_export_environment.sh",
    "AppFrameworkInfo.plist",
}


def scan_directory(root_dir: str) -> ScanResult:
    result = ScanResult()

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            ext = Path(filename).suffix.lower()
            lang = EXT_MAP.get(ext)
            if not lang:
                continue

            scanner = SCANNER_MAP.get(lang)
            if not scanner:
                continue

            try:
                fn_defs, calls = scanner(filepath)
                for d in fn_defs:
                    result.definitions.setdefault(d.name, []).append(d)
                result.calls[filepath] = calls
                result.all_called_names.update(calls)
            except Exception:
                pass

    return result
