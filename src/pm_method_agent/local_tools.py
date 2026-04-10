from __future__ import annotations

from typing import Dict, List, Optional

from pm_method_agent.command_executor import LOCAL_COMMAND_TOOL_NAME, LocalCommandExecutor
from pm_method_agent.directory_list_tool import LOCAL_DIRECTORY_LIST_TOOL_NAME, LocalDirectoryLister
from pm_method_agent.text_file_read_tool import LOCAL_TEXT_FILE_READ_TOOL_NAME, LocalTextFileReader
from pm_method_agent.text_search_tool import LOCAL_TEXT_SEARCH_TOOL_NAME, LocalTextSearcher
from pm_method_agent.text_file_tool import LOCAL_TEXT_FILE_WRITE_TOOL_NAME, LocalTextFileWriter
from pm_method_agent.tool_catalog import ToolDescriptor


LOCAL_TOOL_DESCRIPTORS = [
    ToolDescriptor(
        tool_name=LOCAL_COMMAND_TOOL_NAME,
        kind="command",
        summary="执行本地命令，并经过 hook、策略和执行账本。",
        execution_scope="local",
        input_schema={
            "required": ["command_args"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
                "cwd": {"type": "string", "description": "命令执行目录。"},
                "command_args": {"type": "array", "description": "命令参数数组。"},
                "write_paths": {"type": "array", "description": "预期写入路径，用于运行前校验。"},
                "timeout_seconds": {"type": "number", "description": "命令超时时间，默认 15 秒。"},
            },
        },
        supports_read_paths=False,
        supports_write_paths=True,
        supports_command_args=True,
        default_timeout_seconds=15.0,
    ),
    ToolDescriptor(
        tool_name=LOCAL_DIRECTORY_LIST_TOOL_NAME,
        kind="directory-list",
        summary="列出本地目录中的文件和子目录，并经过读取路径策略与执行账本。",
        execution_scope="local",
        input_schema={
            "required": ["path"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
                "cwd": {"type": "string", "description": "相对路径解析起点。"},
                "path": {"type": "string", "description": "要列出的目录路径。"},
                "recursive": {"type": "boolean", "description": "是否递归列出子目录内容。"},
                "include_hidden": {"type": "boolean", "description": "是否包含隐藏文件和隐藏目录。"},
                "max_entries": {"type": "integer", "description": "最多返回多少条目录项，默认 200。"},
            },
        },
        supports_read_paths=True,
    ),
    ToolDescriptor(
        tool_name=LOCAL_TEXT_SEARCH_TOOL_NAME,
        kind="text-search",
        summary="在本地文件或目录中搜索关键词，并返回命中的文件、行号和片段。",
        execution_scope="local",
        input_schema={
            "required": ["path", "query"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
                "cwd": {"type": "string", "description": "相对路径解析起点。"},
                "path": {"type": "string", "description": "要搜索的文件或目录路径。"},
                "query": {"type": "string", "description": "要搜索的关键词。"},
                "recursive": {"type": "boolean", "description": "目录场景下是否递归搜索，默认 true。"},
                "include_hidden": {"type": "boolean", "description": "是否包含隐藏文件和隐藏目录。"},
                "case_sensitive": {"type": "boolean", "description": "是否区分大小写。"},
                "max_results": {"type": "integer", "description": "最多返回多少条命中结果，默认 100。"},
                "encoding": {"type": "string", "description": "文本编码，默认 utf-8。"},
            },
        },
        supports_read_paths=True,
    ),
    ToolDescriptor(
        tool_name=LOCAL_TEXT_FILE_WRITE_TOOL_NAME,
        kind="file-write",
        summary="写入本地文本文件，并经过写入路径策略与执行账本。",
        execution_scope="local",
        input_schema={
            "required": ["path", "content"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
                "cwd": {"type": "string", "description": "相对路径解析起点。"},
                "path": {"type": "string", "description": "要写入的目标路径。"},
                "content": {"type": "string", "description": "要写入的文本内容。"},
                "append": {"type": "boolean", "description": "是否追加写入。"},
                "create_dirs": {"type": "boolean", "description": "是否自动创建父目录。"},
                "encoding": {"type": "string", "description": "文本编码，默认 utf-8。"},
            },
        },
        supports_read_paths=False,
        supports_write_paths=True,
    ),
    ToolDescriptor(
        tool_name=LOCAL_TEXT_FILE_READ_TOOL_NAME,
        kind="file-read",
        summary="读取本地文本文件，并经过统一的 hook、执行账本和终止语义。",
        execution_scope="local",
        input_schema={
            "required": ["path"],
            "properties": {
                "workspace_id": {"type": "string", "description": "工作区标识。"},
                "cwd": {"type": "string", "description": "相对路径解析起点。"},
                "path": {"type": "string", "description": "要读取的目标路径。"},
                "encoding": {"type": "string", "description": "文本编码，默认 utf-8。"},
                "max_characters": {
                    "type": "integer",
                    "description": "最多返回多少字符，默认 20000，防止一次读取过大内容。",
                },
            },
        },
        supports_read_paths=True,
    ),
]


class LocalToolRegistry:
    def __init__(self, base_dir: Optional[str] = None) -> None:
        self._command_executor = LocalCommandExecutor(base_dir=base_dir)
        self._directory_lister = LocalDirectoryLister(base_dir=base_dir)
        self._text_file_reader = LocalTextFileReader(base_dir=base_dir)
        self._text_searcher = LocalTextSearcher(base_dir=base_dir)
        self._text_file_writer = LocalTextFileWriter(base_dir=base_dir)

    def list_tools(self) -> List[dict]:
        return [item.to_dict() for item in LOCAL_TOOL_DESCRIPTORS]

    def supports(self, tool_name: str) -> bool:
        return _find_descriptor(tool_name) is not None

    def describe_tool(self, tool_name: str) -> dict:
        descriptor = _find_descriptor(tool_name)
        if descriptor is None:
            raise ValueError(f"Unsupported local tool: {tool_name or 'unknown'}")
        return descriptor.to_dict()

    def execute(self, *, tool_name: str, payload: Dict[str, object]) -> object:
        if tool_name == LOCAL_COMMAND_TOOL_NAME:
            return self._command_executor.execute(
                command_args=_ensure_string_list(payload.get("command_args")),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                write_paths=_ensure_string_list(payload.get("write_paths")),
                timeout_seconds=_ensure_float(payload.get("timeout_seconds"), default=15.0),
                approval_id=_optional_string(payload.get("_approval_id")),
            )
        if tool_name == LOCAL_DIRECTORY_LIST_TOOL_NAME:
            return self._directory_lister.list_directory(
                path=_required_string(payload.get("path"), field_name="path"),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                recursive=bool(payload.get("recursive", False)),
                include_hidden=bool(payload.get("include_hidden", False)),
                max_entries=_ensure_int(payload.get("max_entries"), default=200),
                approval_id=_optional_string(payload.get("_approval_id")),
            )
        if tool_name == LOCAL_TEXT_SEARCH_TOOL_NAME:
            return self._text_searcher.search_text(
                path=_required_string(payload.get("path"), field_name="path"),
                query=_required_string(payload.get("query"), field_name="query"),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                recursive=_ensure_bool(payload.get("recursive"), default=True),
                include_hidden=bool(payload.get("include_hidden", False)),
                case_sensitive=bool(payload.get("case_sensitive", False)),
                max_results=_ensure_int(payload.get("max_results"), default=100),
                encoding=_optional_string(payload.get("encoding")) or "utf-8",
                approval_id=_optional_string(payload.get("_approval_id")),
            )
        if tool_name == LOCAL_TEXT_FILE_WRITE_TOOL_NAME:
            return self._text_file_writer.write_text(
                path=_required_string(payload.get("path"), field_name="path"),
                content=_required_string(payload.get("content"), field_name="content"),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                append=bool(payload.get("append", False)),
                create_dirs=bool(payload.get("create_dirs", True)),
                encoding=_optional_string(payload.get("encoding")) or "utf-8",
                approval_id=_optional_string(payload.get("_approval_id")),
            )
        if tool_name == LOCAL_TEXT_FILE_READ_TOOL_NAME:
            return self._text_file_reader.read_text(
                path=_required_string(payload.get("path"), field_name="path"),
                workspace_id=_optional_string(payload.get("workspace_id")) or "default",
                cwd=_optional_string(payload.get("cwd")),
                encoding=_optional_string(payload.get("encoding")) or "utf-8",
                max_characters=_ensure_int(payload.get("max_characters"), default=20000),
                approval_id=_optional_string(payload.get("_approval_id")),
            )
        raise ValueError(f"Unsupported local tool: {tool_name or 'unknown'}")


def _ensure_string_list(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required_string(value: object, *, field_name: str) -> str:
    rendered = _optional_string(value)
    if not rendered:
        raise ValueError(f"Missing {field_name}.")
    return rendered


def _ensure_float(value: object, *, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _ensure_int(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _ensure_bool(value: object, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    rendered = str(value).strip().lower()
    if rendered in {"1", "true", "yes", "on"}:
        return True
    if rendered in {"0", "false", "no", "off"}:
        return False
    return default


def _find_descriptor(tool_name: str) -> Optional[ToolDescriptor]:
    normalized = str(tool_name).strip()
    for descriptor in LOCAL_TOOL_DESCRIPTORS:
        if descriptor.tool_name == normalized:
            return descriptor
    return None
