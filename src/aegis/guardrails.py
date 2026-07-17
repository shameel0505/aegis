import ast
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .schema import FindingDetail


@dataclass
class SafeRegion:
    start_line: int
    end_line: int
    tag: str


def detect_framework(repo_path: str, code_content: str = "") -> str:
    """
    Detect the dominant Python web framework from common project files/imports.
    Returns one of: fastapi, django, flask, generic.
    """
    haystack_parts: List[str] = []
    if code_content:
        haystack_parts.append(code_content.lower())

    candidates = [
        os.path.join(repo_path, "requirements.txt"),
        os.path.join(repo_path, "pyproject.toml"),
        os.path.join(repo_path, "setup.cfg"),
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    haystack_parts.append(f.read().lower())
        except OSError:
            continue

    haystack = "\n".join(haystack_parts)
    if "fastapi" in haystack or re.search(r"\bfrom\s+fastapi\s+import\b", haystack):
        return "fastapi"
    if "django" in haystack or re.search(r"\bfrom\s+django\s+import\b", haystack):
        return "django"
    if "flask" in haystack or re.search(r"\bfrom\s+flask\s+import\b", haystack):
        return "flask"
    return "generic"


def framework_semantic_contract(framework: str) -> str:
    contracts: Dict[str, List[str]] = {
        "generic": [
            "Assume standard framework/runtime contracts are valid unless explicit contradictory evidence exists in this file.",
            "If uncertain, return empty findings [].",
            "Never suggest changes that weaken authentication, authorization, validation, or explicit error handling.",
            "Do not report claims without exact code evidence from this file.",
        ],
        "fastapi": [
            "FastAPI Depends(...) dependency injection is framework-managed control flow.",
            "raise HTTPException(...) is a valid and intentional request-failure path.",
            "Do not flag dependency-injected parameters as missing null checks without explicit evidence of None assignment in this file.",
        ],
        "django": [
            "Django request lifecycle, middleware, and model validation are framework-managed.",
            "Do not flag standard get_object_or_404 / validation pathways as missing checks unless explicit contradictory evidence exists in this file.",
        ],
        "flask": [
            "Flask request context and abort(...) patterns are framework-managed paths.",
            "Do not flag explicit abort/error-handler paths as missing guards without direct contradictory evidence.",
        ],
    }
    selected = contracts.get(framework, contracts["generic"])
    generic = contracts["generic"]
    merged = generic + [r for r in selected if r not in generic]
    return "\n".join(f"- {rule}" for rule in merged)


def analyze_safe_regions(file_path: str, code_content: str, framework: str) -> List[SafeRegion]:
    if not file_path.endswith(".py"):
        return []
    try:
        tree = ast.parse(code_content)
    except SyntaxError:
        return []

    regions: List[SafeRegion] = []
    for node in ast.walk(tree):
        if framework == "fastapi":
            if isinstance(node, ast.arg):
                if _is_depends_arg(node, tree):
                    regions.append(SafeRegion(node.lineno, node.lineno, "FRAMEWORK_DEPENDS"))
            if isinstance(node, ast.Raise) and _raises_http_exception(node):
                end_line = getattr(node, "end_lineno", node.lineno)
                regions.append(SafeRegion(node.lineno, end_line, "FRAMEWORK_ERROR_PATH"))

        if isinstance(node, ast.ExceptHandler):
            if _except_handler_rethrows(node):
                end_line = getattr(node, "end_lineno", node.lineno)
                regions.append(SafeRegion(node.lineno, end_line, "HANDLED_ERROR_PATH"))

    return _dedupe_regions(regions)


def annotate_code_with_safe_regions(code_content: str, safe_regions: List[SafeRegion]) -> str:
    if not safe_regions:
        return code_content
    line_tags: Dict[int, List[str]] = {}
    for region in safe_regions:
        for line_no in range(region.start_line, region.end_line + 1):
            line_tags.setdefault(line_no, [])
            if region.tag not in line_tags[line_no]:
                line_tags[line_no].append(region.tag)

    output_lines: List[str] = []
    for i, line in enumerate(code_content.splitlines(), start=1):
        tags = line_tags.get(i, [])
        if tags:
            output_lines.append(f"{line}  # [AEGIS: {', '.join(tags)}]")
        else:
            output_lines.append(line)
    return "\n".join(output_lines)


def filter_findings(
    findings: List[FindingDetail],
    code_content: str,
    safe_regions: List[SafeRegion],
) -> List[FindingDetail]:
    accepted: List[FindingDetail] = []
    line_index = _line_offsets(code_content)
    for finding in findings:
        snippet = finding.faulty_snippet.strip()
        if not snippet:
            continue

        # No evidence -> no trust.
        if not finding.evidence_graph:
            continue

        # Snippet must exist verbatim in source.
        at = code_content.find(snippet)
        if at == -1:
            continue

        span = _char_span_to_lines(line_index, at, at + len(snippet))
        in_safe_region = _lines_intersect_safe_regions(span[0], span[1], safe_regions)
        desc = (finding.description or "").lower()
        category = (finding.category or "").upper()

        # Drop common hallucination shape: null-guard claims on framework-managed paths.
        if in_safe_region and ("none" in desc or "null" in desc):
            continue

        # Reject recommendations that weaken guarantees.
        if _weakening_recommendation(desc):
            continue

        # Conservative severity: CRITICAL only when the snippet/description contains
        # known high-risk execution or deserialization sinks.
        if finding.severity == "CRITICAL" and not _critical_signal(snippet.lower(), desc):
            finding.severity = "WARNING"

        # Security findings in framework-managed safe regions require stronger proof.
        if in_safe_region and category == "SECURITY" and not _critical_signal(snippet.lower(), desc):
            continue

        accepted.append(finding)
    return accepted


def _is_depends_arg(node: ast.arg, tree: ast.AST) -> bool:
    parent_func = None
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node in candidate.args.args:
                parent_func = candidate
                break
    if parent_func is None:
        return False

    args = list(parent_func.args.args)
    defaults = list(parent_func.args.defaults)
    if not defaults:
        return False

    first_default_arg_index = len(args) - len(defaults)
    try:
        arg_index = args.index(node)
    except ValueError:
        return False
    if arg_index < first_default_arg_index:
        return False

    default = defaults[arg_index - first_default_arg_index]
    if isinstance(default, ast.Call):
        if isinstance(default.func, ast.Name) and default.func.id == "Depends":
            return True
        if isinstance(default.func, ast.Attribute) and default.func.attr == "Depends":
            return True
    return False


def _raises_http_exception(node: ast.Raise) -> bool:
    exc = node.exc
    if not isinstance(exc, ast.Call):
        return False
    func = exc.func
    if isinstance(func, ast.Name):
        return func.id == "HTTPException"
    if isinstance(func, ast.Attribute):
        return func.attr == "HTTPException"
    return False


def _except_handler_rethrows(node: ast.ExceptHandler) -> bool:
    for stmt in node.body:
        if isinstance(stmt, ast.Raise):
            return True
    return False


def _dedupe_regions(regions: List[SafeRegion]) -> List[SafeRegion]:
    uniq = {}
    for region in regions:
        key = (region.start_line, region.end_line, region.tag)
        uniq[key] = region
    return list(uniq.values())


def _line_offsets(text: str) -> List[int]:
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _char_span_to_lines(line_index: List[int], start: int, end: int) -> Tuple[int, int]:
    start_line = 1
    end_line = 1
    for i, off in enumerate(line_index, start=1):
        if off <= start:
            start_line = i
        if off <= end:
            end_line = i
        else:
            break
    return start_line, end_line


def _lines_intersect_safe_regions(start_line: int, end_line: int, safe_regions: List[SafeRegion]) -> bool:
    for region in safe_regions:
        if start_line <= region.end_line and end_line >= region.start_line:
            return True
    return False


def _weakening_recommendation(description: str) -> bool:
    bad_patterns = [
        "return empty string",
        "return ''",
        'return ""',
        "remove authentication",
        "skip authentication",
        "ignore exception",
        "swallow exception",
        "do not raise",
    ]
    return any(p in description for p in bad_patterns)


def _critical_signal(snippet: str, description: str) -> bool:
    high_risk_markers = [
        "eval(",
        "exec(",
        "pickle.loads(",
        "yaml.load(",
        "shell=true",
        "os.system(",
        "subprocess.popen(",
    ]
    text = f"{snippet}\n{description}".lower()
    return any(marker in text for marker in high_risk_markers)
