from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pm_method_agent.tool_runtime import (
    LocalToolExecutionOutcome,
    LocalToolExecutionResult,
    LocalToolHandler,
    LocalToolRequest,
    LocalToolRuntime,
)


LOCAL_TEXT_SEARCH_TOOL_NAME = "local-text-search"
TEXT_SEARCH_ACTION = "text-search.search"


@dataclass
class TextSearchResult(LocalToolExecutionResult):
    pass


class LocalTextSearchHandler(LocalToolHandler):
    name = LOCAL_TEXT_SEARCH_TOOL_NAME

    def execute(self, request: LocalToolRequest) -> LocalToolExecutionOutcome:
        path = str(request.request_payload.get("path", "")).strip()
        query = str(request.request_payload.get("query", "")).strip()
        if not path:
            return LocalToolExecutionOutcome(
                action="text-search-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "InvalidRequest",
                    "message": "Missing path.",
                },
            )
        if not query:
            return LocalToolExecutionOutcome(
                action="text-search-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "InvalidRequest",
                    "message": "Missing query.",
                },
            )

        encoding = str(request.request_payload.get("encoding", "utf-8")).strip() or "utf-8"
        recursive = bool(request.request_payload.get("recursive", True))
        include_hidden = bool(request.request_payload.get("include_hidden", False))
        case_sensitive = bool(request.request_payload.get("case_sensitive", False))
        max_results = int(request.request_payload.get("max_results", 100))

        target_path = Path(path)
        if not target_path.is_absolute():
            base_dir = Path(request.cwd or ".")
            target_path = (base_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()

        if not target_path.exists():
            return LocalToolExecutionOutcome(
                action="text-search-failed",
                terminal_state="failed",
                success=False,
                error={
                    "type": "FileNotFoundError",
                    "message": f"Path not found: {target_path}",
                },
            )

        candidates = _build_candidate_files(
            target_path,
            recursive=recursive,
            include_hidden=include_hidden,
        )
        normalized_query = query if case_sensitive else query.lower()
        matches: list[dict[str, object]] = []
        truncated = False
        searched_file_count = 0

        for file_path in candidates:
            searched_file_count += 1
            try:
                content = file_path.read_text(encoding=encoding)
            except (UnicodeDecodeError, OSError):
                continue

            for line_number, line in enumerate(content.splitlines(), start=1):
                haystack = line if case_sensitive else line.lower()
                if normalized_query not in haystack:
                    continue
                if max_results >= 0 and len(matches) >= max_results:
                    truncated = True
                    break
                matches.append(
                    {
                        "path": str(file_path),
                        "relative_path": _relative_to_anchor(file_path, target_path),
                        "line_number": line_number,
                        "line_text": line,
                    }
                )
            if truncated:
                break

        return LocalToolExecutionOutcome(
            action="text-searched",
            terminal_state="completed",
            success=True,
            result_ref=f"search:{target_path}",
            output_payload={
                "path": str(target_path),
                "query": query,
                "matches": matches,
                "match_count": len(matches),
                "searched_file_count": searched_file_count,
                "recursive": recursive,
                "include_hidden": include_hidden,
                "case_sensitive": case_sensitive,
                "truncated": truncated,
                "max_results": max_results,
                "encoding": encoding,
            },
        )


class LocalTextSearcher:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._base_dir = str(Path(base_dir or ".").resolve())
        self._runtime = LocalToolRuntime(base_dir=self._base_dir)
        self._handler = LocalTextSearchHandler()

    def search_text(
        self,
        *,
        path: str,
        query: str,
        workspace_id: str = "default",
        cwd: Optional[str] = None,
        recursive: bool = True,
        include_hidden: bool = False,
        case_sensitive: bool = False,
        max_results: int = 100,
        encoding: str = "utf-8",
        approval_id: str = "",
    ) -> TextSearchResult:
        resolved_cwd = str(Path(cwd or self._base_dir).resolve())
        resolved_path = Path(path)
        if not resolved_path.is_absolute():
            resolved_path = (Path(resolved_cwd) / resolved_path).resolve()
        else:
            resolved_path = resolved_path.resolve()

        request = LocalToolRequest(
            tool_name=self._handler.name,
            action_name=TEXT_SEARCH_ACTION,
            workspace_id=workspace_id,
            summary=f"搜索文本：{resolved_path} / {query}",
            request_payload={
                "path": str(resolved_path),
                "query": query,
                "recursive": recursive,
                "include_hidden": include_hidden,
                "case_sensitive": case_sensitive,
                "max_results": max_results,
                "encoding": encoding,
            },
            read_paths=[str(resolved_path)],
            cwd=resolved_cwd,
            blocked_action="text-search-blocked",
            resume_from=TEXT_SEARCH_ACTION,
            approval_id=approval_id,
        )
        result = self._runtime.execute_tool(request, handler=self._handler)
        return TextSearchResult(
            allowed=result.allowed,
            tool_name=result.tool_name,
            action=result.action,
            command_args=list(result.command_args),
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            cwd=result.cwd,
            output_payload=dict(result.output_payload),
            runtime_session=result.runtime_session,
            reason=result.reason,
            terminal_state=result.terminal_state,
            violation_kind=result.violation_kind,
        )


def _build_candidate_files(
    target_path: Path,
    *,
    recursive: bool,
    include_hidden: bool,
) -> list[Path]:
    if target_path.is_file():
        return [target_path]

    candidates = (
        sorted(target_path.rglob("*"), key=lambda item: str(item.relative_to(target_path)))
        if recursive
        else sorted(target_path.iterdir(), key=lambda item: item.name)
    )
    files: list[Path] = []
    for item in candidates:
        if not item.is_file():
            continue
        relative_name = str(item.relative_to(target_path))
        if not include_hidden and any(part.startswith(".") for part in Path(relative_name).parts):
            continue
        files.append(item)
    return files


def _relative_to_anchor(file_path: Path, anchor: Path) -> str:
    if anchor.is_dir():
        return str(file_path.relative_to(anchor))
    return file_path.name
