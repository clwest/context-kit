"""context-kit `coverage` subcommand: verification coverage map.

This is a read-only inventory-style report. It does not claim semantic
correctness; it only maps which tracked files are covered by current
inspect/verify heuristics and which remain unknown.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from cli.hotpath import IGNORED_DIR_NAMES, IGNORED_DIR_SUFFIXES
from cli.inspect import _INSPECT_SCOPES, _inspect_path_role, _inspect_scope_matches


_COVERAGE_CLASSES = (
    "runtime/source",
    "docs-active",
    "docs-historical",
    "tests",
    "generated/artifact",
    "config/deployment",
    "unknown",
)

_SOURCE_DIR_HINTS = ("core", "app", "src", "lib", "scripts", "services", "backend", "ai_core", "frontend")
_CODE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".java",
    ".kt",
    ".kts",
    ".scala",
    ".cs",
    ".cpp",
    ".cc",
    ".c",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".sol",
}
_DOC_SUFFIXES = {".md", ".markdown", ".rst"}
_CONFIG_SUFFIXES = {".toml", ".yaml", ".yml", ".json", ".ini", ".cfg"}
_GENERATED_DIR_HINTS = {"dist", "build", "node_modules", "__pycache__", ".venv", "venv", "venv_ml", "htmlcov", "artifacts"}
_ASSET_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".avif",
    ".bmp",
    ".ico",
    ".svg",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}


@dataclass
class CoverageRow:
    classification: str
    files: int = 0
    bytes: int = 0


def run_coverage(args: argparse.Namespace) -> int:
    project = Path(args.path).resolve() if args.path else Path.cwd().resolve()
    if not project.is_dir():
        print(f"context-kit: {project} is not a directory.")
        return 2

    scope = getattr(args, "scope", None)
    if scope is not None and scope not in _INSPECT_SCOPES:
        print(f"context-kit: unknown coverage scope `{scope}`. Valid scopes: {', '.join(_INSPECT_SCOPES)}.")
        return 2

    result = _coverage(project, scope=scope)
    if getattr(args, "json", False):
        print(json.dumps(_to_json(result), indent=2, default=str))
    else:
        print(_render_text(result))
    return 0


def _coverage(project: Path, *, scope: str | None = None) -> dict:
    files = _tracked_files(project)
    if scope is not None:
        files = [path for path in files if _inspect_scope_matches(project, path, scope)]

    sized = _with_sizes(files)
    rows = {name: CoverageRow(name) for name in _COVERAGE_CLASSES}
    by_unknown_dir: dict[str, CoverageRow] = defaultdict(lambda: CoverageRow("unknown"))
    unclassified_hot_files: list[dict] = []

    for path, size in sized:
        classification = _classify_file(path)
        rows[classification].files += 1
        rows[classification].bytes += size
        if classification == "unknown":
            dir_path = _directory_key(project, path)
            by_unknown_dir[dir_path].files += 1
            by_unknown_dir[dir_path].bytes += size
            unclassified_hot_files.append({
                "path": _rel(project, path),
                "bytes": size,
            })

    total_files = len(sized)
    total_bytes = sum(size for _, size in sized)
    skipped_files = rows["generated/artifact"].files
    skipped_bytes = rows["generated/artifact"].bytes
    unknown_files = rows["unknown"].files
    unknown_bytes = rows["unknown"].bytes
    covered_files = total_files - skipped_files - unknown_files
    covered_bytes = total_bytes - skipped_bytes - unknown_bytes

    summary = {
        "total_files": total_files,
        "total_bytes": total_bytes,
        "covered_files": covered_files,
        "covered_bytes": covered_bytes,
        "skipped_files": skipped_files,
        "skipped_bytes": skipped_bytes,
        "unknown_files": unknown_files,
        "unknown_bytes": unknown_bytes,
        "coverage_files_pct": _pct(covered_files, total_files),
        "coverage_bytes_pct": _pct(covered_bytes, total_bytes),
    }

    by_classification = {
        name: {
            "files": rows[name].files,
            "bytes": rows[name].bytes,
            "files_pct": _pct(rows[name].files, total_files),
            "bytes_pct": _pct(rows[name].bytes, total_bytes),
        }
        for name in _COVERAGE_CLASSES
    }
    by_top_directory = [
        {
            "path": path,
            "files": row.files,
            "bytes": row.bytes,
        }
        for path, row in sorted(by_unknown_dir.items(), key=lambda item: (item[1].bytes, item[1].files), reverse=True)[:10]
    ]
    unclassified_hot_files = sorted(unclassified_hot_files, key=lambda item: item["bytes"], reverse=True)[:10]

    return {
        "repo": project.name,
        "path": str(project),
        "scope": scope,
        "summary": summary,
        "by_classification": by_classification,
        "by_top_directory": by_top_directory,
        "unclassified_hot_files": unclassified_hot_files,
    }


def _tracked_files(project: Path) -> list[Path]:
    if (project / ".git").exists():
        tracked = _git_ls_files(project)
        if tracked is not None:
            return [project / rel for rel in tracked if rel]
    return _walk_files(project)


def _git_ls_files(project: Path) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project), "ls-files", "-z"],
            capture_output=True,
            check=False,
            text=False,
        )
    except (OSError, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return [item.decode("utf-8", errors="replace") for item in result.stdout.split(b"\x00") if item]


def _walk_files(project: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(project):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIR_NAMES and not any(d.endswith(sfx) for sfx in IGNORED_DIR_SUFFIXES)]
        base = Path(root)
        for name in names:
            files.append(base / name)
    return files


def _with_sizes(files: list[Path]) -> list[tuple[Path, int]]:
    sized: list[tuple[Path, int]] = []
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        if path.is_file():
            sized.append((path, st.st_size))
    return sized


def _classify_file(path: Path) -> str:
    lowered = path.as_posix().lower()
    name = path.name.lower()
    role = _inspect_path_role(path)

    if role == "generated" or _is_generated_artifact(path):
        return "generated/artifact"
    if _is_test_file(path):
        return "tests"
    if _is_docs_artifact_subfolder(path):
        return "generated/artifact"
    if _is_docs_historical(path, role):
        return "docs-historical"
    if _is_docs_active(path, role):
        return "docs-active"
    if _is_config_deployment(path):
        return "config/deployment"
    if _is_runtime_source(path):
        return "runtime/source"
    if lowered.startswith(".rag/"):
        return "config/deployment"
    if name in {"readme.md", "readme.rst", "license", "license.md"}:
        return "docs-active"
    return "unknown"


def _is_generated_artifact(path: Path) -> bool:
    lowered = path.as_posix().lower()
    if any(seg in lowered for seg in ("/docs/verification/", "docs/verification/")):
        return True
    if lowered.startswith(".rag/") or "/.rag/" in lowered:
        return True
    if lowered.startswith("tests/artifacts/") or "/tests/artifacts/" in lowered:
        return True
    if lowered.startswith("mobile/assets/") or "/mobile/assets/" in lowered:
        return True
    parts = set(path.parts)
    if parts & _GENERATED_DIR_HINTS:
        return True
    if any(part.endswith(".egg-info") for part in path.parts):
        return True
    if path.suffix.lower() in _ASSET_SUFFIXES and any(part in {"assets", "asset", "images", "img", "media"} for part in path.parts[:-1]):
        return True
    return False


def _is_test_file(path: Path) -> bool:
    lowered = path.as_posix().lower()
    name = path.name.lower()
    return (
        lowered.startswith("tests/")
        or lowered.startswith("core/tests/")
        or "/tests/" in lowered
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".spec.js")
        or name.endswith(".spec.ts")
        or name.endswith(".test.js")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
    )


def _is_docs_historical(path: Path, role: str) -> bool:
    if role in {"historical", "external"}:
        return True
    tail = _docs_tail(path)
    return tail is not None and tail[:1] == ["archive"]


def _is_docs_active(path: Path, role: str) -> bool:
    tail = _docs_tail(path)
    if tail is None:
        return False
    if tail[:1] == ["archive"]:
        return False
    if tail[:2] == ["discord", "snapshots"]:
        return False
    if tail[:2] == ["code-review", "outputs"]:
        return False
    if path.name == ".gitkeep":
        return True
    suffix = path.suffix.lower()
    if suffix in _DOC_SUFFIXES:
        return True
    if tail[:1] == ["ops"] and suffix == ".json":
        return not _is_docs_artifact_filename(path.name)
    if tail[:1] == ["initiatives"] and suffix in {".yaml", ".yml"}:
        return True
    if suffix in {".yaml", ".yml"} and tail[:1] in (["ops"], ["agents"], ["topics"], ["plans"], ["architecture"], ["integrations"]):
        return True
    return False


def _is_docs_artifact_filename(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in ("report", "output", "snapshot", "generated"))


def _is_docs_artifact_subfolder(path: Path) -> bool:
    tail = _docs_tail(path)
    if tail is None:
        return False
    if tail[:2] == ["discord", "snapshots"]:
        return True
    if tail[:2] == ["code-review", "outputs"]:
        return True
    return False


def _docs_tail(path: Path) -> list[str] | None:
    parts = [part.lower() for part in path.parts]
    try:
        idx = parts.index("docs")
    except ValueError:
        return None
    return parts[idx + 1 :]


def _is_config_deployment(path: Path) -> bool:
    _lowered = path.as_posix().lower()
    name = path.name.lower()
    parts = set(path.parts)
    if name in {"dockerfile", "procfile"}:
        return True
    if name.startswith(".env"):
        return True
    if parts & {"deployment", "railway", "config"}:
        return True
    if ".github" in parts and "workflows" in parts:
        return True
    if name in {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "setup.cfg", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}:
        return True
    if path.suffix.lower() in _CONFIG_SUFFIXES and any(part in {"config", "deployment", "railway", "workflows"} for part in path.parts[:-1]):
        return True
    return False


def _is_runtime_source(path: Path) -> bool:
    lowered = path.as_posix().lower()
    suffix = path.suffix.lower()
    if suffix in _CODE_SUFFIXES:
        return True
    if any(part in _SOURCE_DIR_HINTS for part in path.parts):
        return True
    return lowered.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".rb", ".php", ".sol"))


def _directory_key(project: Path, path: Path) -> str:
    try:
        rel = path.relative_to(project)
    except ValueError:
        rel = path
    parent = rel.parent.as_posix()
    return parent or "(root)"


def _rel(project: Path, path: Path) -> str:
    try:
        return str(path.relative_to(project))
    except ValueError:
        return str(path)


def _pct(numer: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round((numer / denom) * 100, 1)


def _render_text(result: dict) -> str:
    lines: list[str] = []
    lines.append("=== CONTEXT-KIT COVERAGE ===")
    lines.append(f"Repo:           {result['repo']}")
    lines.append(f"Path:           {result['path']}")
    if result["scope"] is not None:
        lines.append(f"Scope:          {result['scope']}")
    lines.append("")

    summary = result["summary"]
    lines.append("## Summary")
    lines.append(f"  Tracked files:         {summary['total_files']:,}")
    lines.append(f"  Covered files:         {summary['covered_files']:,}")
    lines.append(f"  Skipped / ignored:     {summary['skipped_files']:,}")
    lines.append(f"  Unknown / unclassified: {summary['unknown_files']:,}")
    lines.append(f"  Coverage (files):      {summary['coverage_files_pct']:.1f}%")
    lines.append(f"  Coverage (bytes):      {summary['coverage_bytes_pct']:.1f}%")
    lines.append("")

    lines.append("## By classification")
    for name in _COVERAGE_CLASSES:
        row = result["by_classification"][name]
        lines.append(f"  {name:<20} {row['files']:>6} files  {row['bytes']:>10} bytes")
    lines.append("")

    if result["by_top_directory"]:
        lines.append("## Top unclassified directories")
        for row in result["by_top_directory"]:
            lines.append(f"  {row['path']:<32} {row['files']:>5} files  {row['bytes']:>10} bytes")
        lines.append("")

    if result["unclassified_hot_files"]:
        lines.append("## Large unclassified files")
        for item in result["unclassified_hot_files"]:
            lines.append(f"  {item['bytes']:>10}  {item['path']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _to_json(result: dict) -> dict:
    return result
