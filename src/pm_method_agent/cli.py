from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from pm_method_agent.http_service import run_http_server
from pm_method_agent.orchestrator import run_analysis_with_context
from pm_method_agent.prompting import build_prompt_composition
from pm_method_agent.renderers import (
    build_case_history_payload,
    build_case_runtime_payload,
    build_runtime_session_payload,
    build_workspace_cases_payload,
    render_case_history,
    render_rule_diagnostics,
    render_runtime_session,
    render_case_state,
    render_workspace_overview,
)
from pm_method_agent.runtime_tools import RuntimeToolRegistry
from pm_method_agent.rule_loader import load_rule_set
from pm_method_agent.runtime_config import ensure_local_env_loaded
from pm_method_agent.runtime_policy import load_runtime_policy
from pm_method_agent.runtime_session_service import default_runtime_session_store, get_or_create_runtime_session
from pm_method_agent.agent_shell import PMMethodAgentShell
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case
from pm_method_agent.workspace_service import (
    activate_workspace_case,
    default_workspace_store,
    get_or_create_workspace,
    get_workspace_approval_preferences,
    save_workspace,
    update_workspace_approval_preferences,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pm-method-agent",
        description="PM Method Agent 的轻量命令行运行时。",
    )
    parser.add_argument(
        "input",
        help="待分析的需求或问题描述。",
    )
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "problem-framing", "decision-challenge", "validation-design"],
        help="分析模式。默认 auto，会顺序执行三个内部模块。",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="输出格式。默认 markdown。",
    )
    parser.add_argument(
        "--case-id",
        help="可选的案例标识。传入后会在卡片中展示。",
    )
    parser.add_argument(
        "--business-model",
        choices=["tob", "toc", "internal"],
        help="产品业务类型。",
    )
    parser.add_argument(
        "--primary-platform",
        choices=["pc", "mobile-web", "native-app", "mini-program", "multi-platform"],
        help="主要使用平台。",
    )
    parser.add_argument(
        "--distribution-channel",
        help="产品主要分发或交付渠道。",
    )
    parser.add_argument(
        "--product-domain",
        help="产品所属业务域。",
    )
    parser.add_argument(
        "--target-user-role",
        action="append",
        default=[],
        help="关键用户角色。可重复传入多次。",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="限制条件。可重复传入多次。",
    )
    parser.add_argument(
        "--context-json",
        help="以 JSON 字符串形式传入场景基础信息，用于覆盖或补充前面的上下文字段。",
    )
    return parser


def build_session_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pm-method-agent",
        description="PM Method Agent 的会话模式命令行运行时。",
    )
    parser.add_argument(
        "--store-dir",
        help="会话存储目录。默认保存在当前目录下的 .pm_method_agent/cases。",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="输出格式。默认 markdown。",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start", help="创建一个新的多轮分析会话。")
    _add_context_arguments(start_parser)
    start_parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "problem-framing", "decision-challenge", "validation-design"],
        help="分析模式。默认 auto。",
    )
    start_parser.add_argument(
        "--case-id",
        help="可选的案例标识。默认自动生成。",
    )
    start_parser.add_argument(
        "input",
        help="待分析的需求或问题描述。",
    )

    reply_parser = subparsers.add_parser("reply", help="在已有会话上补充回答。")
    _add_context_arguments(reply_parser)
    reply_parser.add_argument("case_id", help="会话案例编号。")
    reply_parser.add_argument("reply", help="本轮补充回答。")

    show_parser = subparsers.add_parser("show", help="查看当前会话的最新卡片。")
    show_parser.add_argument("case_id", help="会话案例编号。")

    history_parser = subparsers.add_parser("history", help="查看当前会话的历史和状态变化。")
    history_parser.add_argument("case_id", help="会话案例编号。")

    workspace_parser = subparsers.add_parser("workspace", help="查看或切换当前工作区。")
    workspace_parser.add_argument("workspace_id", help="工作区标识。")
    workspace_parser.add_argument("--switch-case-id", help="切换当前活跃案例。")
    workspace_parser.add_argument(
        "--approval-preferences-json",
        help="以 JSON 字符串更新工作区审批偏好，例如 auto_approve_actions。",
    )

    serve_parser = subparsers.add_parser("serve", help="启动本地 HTTP 服务。")
    serve_parser.add_argument("--host", default="127.0.0.1", help="监听地址。默认 127.0.0.1。")
    serve_parser.add_argument("--port", type=int, default=8000, help="监听端口。默认 8000。")

    agent_parser = subparsers.add_parser("agent", help="通过统一入口模拟 agent/skill 交互。")
    agent_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")
    agent_parser.add_argument("message", help="用户当前输入。")

    approvals_parser = subparsers.add_parser("approvals", help="查看当前工作区待确认的运行时操作。")
    approvals_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")

    runtime_parser = subparsers.add_parser("runtime", help="查看当前工作区的运行时状态与压缩记忆。")
    runtime_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")

    approve_parser = subparsers.add_parser("approve", help="批准一个待确认操作并继续执行。")
    approve_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")
    approve_parser.add_argument("approval_id", help="待确认操作编号。")

    reject_parser = subparsers.add_parser("reject", help="拒绝一个待确认操作。")
    reject_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")
    reject_parser.add_argument("--reason", default="", help="拒绝原因。")
    reject_parser.add_argument("approval_id", help="待确认操作编号。")

    expire_parser = subparsers.add_parser("expire", help="将一个待确认操作标记为过期。")
    expire_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")
    expire_parser.add_argument("--reason", default="", help="过期原因。")
    expire_parser.add_argument("approval_id", help="待确认操作编号。")

    rules_parser = subparsers.add_parser("rules", help="查看当前目录生效的规则和运行时策略。")
    rules_parser.add_argument(
        "--base-dir",
        default=".",
        help="规则解析起点目录。默认当前目录。",
    )
    rules_parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="同时输出拼装后的 prompt 预览。",
    )

    command_parser = subparsers.add_parser("command", help="通过统一执行壳运行本地命令并经过 hook 校验。")
    command_parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="输出格式。默认 markdown。",
    )
    command_parser.add_argument("--workspace-id", default="default", help="工作区标识。默认 default。")
    command_parser.add_argument("--cwd", help="命令执行目录。默认当前仓库根目录。")
    command_parser.add_argument(
        "--write-path",
        action="append",
        default=[],
        help="预期写入路径，可重复传入，用于运行前校验。",
    )
    command_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=15.0,
        help="命令超时时间，默认 15 秒。",
    )
    command_parser.add_argument(
        "command_args",
        nargs=argparse.REMAINDER,
        help="要执行的命令参数。建议在子命令后用 -- 开始。",
    )

    tool_parser = subparsers.add_parser("tool", help="查看或执行已注册的本地工具。")
    tool_parser.add_argument(
        "--format",
        default="markdown",
        choices=["markdown", "json"],
        help="输出格式。默认 markdown。",
    )
    tool_mode_group = tool_parser.add_mutually_exclusive_group(required=True)
    tool_mode_group.add_argument(
        "--list",
        action="store_true",
        help="列出当前已经注册的本地工具。",
    )
    tool_mode_group.add_argument(
        "--describe",
        metavar="TOOL_NAME",
        help="查看指定工具的元数据说明。",
    )
    tool_mode_group.add_argument(
        "--tool-name",
        help="工具名称，例如 local-command。与 --payload-json 一起用于执行工具。",
    )
    tool_parser.add_argument(
        "--payload-json",
        help="工具请求体，使用 JSON 字符串传入。",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    ensure_local_env_loaded()
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if _is_session_command(args_list):
        return _run_session_command(args_list)

    parser = build_parser()
    args = parser.parse_args(args_list)

    context_profile = _build_context_profile(args)

    case_state = run_analysis_with_context(
        raw_input=args.input,
        mode=args.mode,
        case_id=args.case_id or "case-001",
        context_profile=context_profile,
        show_case_id=bool(args.case_id),
    )
    if args.format == "json":
        print(json.dumps(_build_case_cli_payload(case_state), ensure_ascii=False, indent=2))
    else:
        print(render_case_state(case_state, output_format=args.format))
    return 0


def _run_session_command(argv: List[str]) -> int:
    parser = build_session_parser()
    args = parser.parse_args(argv)
    store = default_store(args.store_dir)
    workspace_store = default_workspace_store(args.store_dir)
    agent_shell = PMMethodAgentShell(base_dir=args.store_dir)
    local_tools = RuntimeToolRegistry(base_dir=args.store_dir)
    runtime_store = default_runtime_session_store(args.store_dir)

    try:
        if args.command == "start":
            case_state = create_case(
                raw_input=args.input,
                context_profile=_build_context_profile(args),
                mode=args.mode,
                case_id=args.case_id,
                store=store,
            )
        elif args.command == "reply":
            case_state = reply_to_case(
                case_id=args.case_id,
                reply_text=args.reply,
                context_profile_updates=_build_context_profile(args),
                store=store,
            )
        elif args.command == "show":
            case_state = get_case(case_id=args.case_id, store=store)
        elif args.command == "workspace":
            workspace = get_or_create_workspace(args.workspace_id, store=workspace_store)
            if args.approval_preferences_json:
                preferences_payload = json.loads(args.approval_preferences_json)
                if not isinstance(preferences_payload, dict):
                    raise ValueError("approval-preferences-json must be a JSON object.")
                update_workspace_approval_preferences(
                    workspace,
                    auto_approve_actions=_ensure_string_list_or_empty(
                        preferences_payload.get("auto_approve_actions")
                    ),
                )
                save_workspace(workspace, store=workspace_store)
                if args.format == "json":
                    print(
                        json.dumps(
                            {
                                "workspace": workspace.to_dict(),
                                "approval_preferences": get_workspace_approval_preferences(workspace),
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print(f"已更新工作区 {workspace.workspace_id} 的审批偏好。")
                return 0
            if args.switch_case_id:
                case_state = get_case(case_id=args.switch_case_id, store=store)
                activate_workspace_case(workspace, case_state.case_id)
                save_workspace(workspace, store=workspace_store)
                if args.format == "json":
                    print(
                        json.dumps(
                            {
                                "workspace": workspace.to_dict(),
                                "case": case_state.to_dict(),
                                "case_runtime": build_case_runtime_payload(case_state),
                                "rendered_card": render_case_state(case_state),
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    print(f"已切换到案例 {case_state.case_id}。")
                    print("")
                    print(render_case_state(case_state))
                return 0
            recent_cases = []
            for case_id in workspace.recent_case_ids:
                try:
                    recent_cases.append(get_case(case_id=case_id, store=store))
                except FileNotFoundError:
                    continue
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "workspace": workspace.to_dict(),
                            "cases": build_workspace_cases_payload(workspace, recent_cases),
                            "approval_preferences": get_workspace_approval_preferences(workspace),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(render_workspace_overview(workspace, recent_cases))
            return 0
        elif args.command == "serve":
            run_http_server(host=args.host, port=args.port, store_dir=args.store_dir)
            return 0
        elif args.command == "agent":
            response = agent_shell.handle_message(
                message=args.message,
                workspace_id=args.workspace_id,
            )
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "action": response.action,
                            "message": response.message,
                            "workspace": response.workspace.to_dict(),
                            "runtime_session": response.runtime_session.to_dict(),
                            "case": response.case_state.to_dict() if response.case_state else None,
                            "case_runtime": (
                                build_case_runtime_payload(response.case_state) if response.case_state else None
                            ),
                            "project_profile": (
                                response.project_profile.to_dict() if response.project_profile else None
                            ),
                            "rendered_card": response.rendered_card,
                            "rendered_history": response.rendered_history,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(response.message)
                if response.rendered_history:
                    print("")
                    print(response.rendered_history)
                elif response.rendered_card:
                    print("")
                    print(response.rendered_card)
            return 0
        elif args.command == "approvals":
            approvals = local_tools.list_pending_approvals(workspace_id=args.workspace_id)
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "workspace_id": args.workspace_id,
                            "pending_approvals": approvals,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(f"工作区：{args.workspace_id}")
                if not approvals:
                    print("当前没有待确认操作。")
                else:
                    for item in approvals:
                        print(f"- {item['approval_id']} / {item['tool_name']}")
                        print(f"  动作：{item['action_name']}")
                        violation = item.get("violation") or {}
                        reason = str(violation.get("reason", "")).strip()
                        if reason:
                            print(f"  原因：{reason}")
            return 0
        elif args.command == "runtime":
            runtime_session = get_or_create_runtime_session(
                args.workspace_id,
                store=runtime_store,
            )
            if args.format == "json":
                print(json.dumps(build_runtime_session_payload(runtime_session), ensure_ascii=False, indent=2))
            else:
                print(render_runtime_session(runtime_session))
            return 0
        elif args.command == "approve":
            result = local_tools.approve_pending_approval(
                workspace_id=args.workspace_id,
                approval_id=args.approval_id,
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"已批准：{args.approval_id}")
                print(f"工具：{result.tool_name}")
                print(f"动作：{result.action}")
                print(f"终止语义：{result.terminal_state}")
                if result.reason:
                    print(f"原因：{result.reason}")
                if result.output_payload:
                    print("")
                    print("## 输出")
                    print(json.dumps(result.output_payload, ensure_ascii=False, indent=2))
            return 0
        elif args.command == "reject":
            result = local_tools.reject_pending_approval(
                workspace_id=args.workspace_id,
                approval_id=args.approval_id,
                reason=args.reason,
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"已拒绝：{args.approval_id}")
                print(f"状态：{result.status}")
                if result.reason:
                    print(f"原因：{result.reason}")
            return 0
        elif args.command == "expire":
            result = local_tools.expire_pending_approval(
                workspace_id=args.workspace_id,
                approval_id=args.approval_id,
                reason=args.reason,
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"已标记过期：{args.approval_id}")
                print(f"状态：{result.status}")
                if result.reason:
                    print(f"原因：{result.reason}")
            return 0
        elif args.command == "rules":
            base_dir = str(Path(args.base_dir).resolve())
            rule_set = load_rule_set(base_dir=base_dir)
            runtime_policy = load_runtime_policy(base_dir=base_dir)
            prompt_composition = build_prompt_composition(
                identity="你是 PM Method Agent 的受控分析模块。",
                agent_role="在规则约束下完成问题定义、决策挑战和验证设计的分析协作。",
                task_instruction="读取当前项目的规则层与运行时策略，并输出可检查的统一视图。",
                base_dir=base_dir,
            )
            print(
                render_rule_diagnostics(
                    base_dir=base_dir,
                    rule_set=rule_set,
                    prompt_composition=prompt_composition,
                    runtime_policy=runtime_policy,
                    output_format=args.format,
                    show_prompt=args.show_prompt,
                )
            )
            return 0
        elif args.command == "command":
            command_args = list(args.command_args)
            if command_args and command_args[0] == "--":
                command_args = command_args[1:]
            if not command_args:
                raise ValueError("Missing command args.")
            result = local_tools.execute(
                tool_name="local-command",
                payload={
                    "workspace_id": args.workspace_id,
                    "cwd": args.cwd,
                    "write_paths": list(args.write_path),
                    "timeout_seconds": args.timeout_seconds,
                    "command_args": command_args,
                },
            )
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"动作：{result.action}")
                print(f"命令：{' '.join(result.command_args)}")
                print(f"终止语义：{result.terminal_state}")
                if result.reason:
                    print(f"原因：{result.reason}")
                print(f"退出码：{result.exit_code}")
                if result.stdout:
                    print("")
                    print("## stdout")
                    print(result.stdout.rstrip())
                if result.stderr:
                    print("")
                    print("## stderr")
                    print(result.stderr.rstrip())
            return 0
        elif args.command == "tool":
            if args.list:
                payload = {"tools": local_tools.list_tools()}
                if args.format == "json":
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                else:
                    for item in payload["tools"]:
                        print(f"- {item['tool_name']} [{item['kind']} / {item['execution_scope']}]")
                        print(f"  {item['summary']}")
                return 0

            if args.describe:
                descriptor = local_tools.describe_tool(args.describe)
                if args.format == "json":
                    print(json.dumps(descriptor, ensure_ascii=False, indent=2))
                else:
                    print(f"工具：{descriptor['tool_name']}")
                    print(f"类型：{descriptor['kind']}")
                    print(f"执行范围：{descriptor['execution_scope']}")
                    print(f"说明：{descriptor['summary']}")
                    print(f"支持读取路径声明：{'是' if descriptor['supports_read_paths'] else '否'}")
                    print(f"支持命令参数：{'是' if descriptor['supports_command_args'] else '否'}")
                    print(f"支持写入路径声明：{'是' if descriptor['supports_write_paths'] else '否'}")
                    if descriptor["default_timeout_seconds"] is not None:
                        print(f"默认超时：{descriptor['default_timeout_seconds']} 秒")
                    schema = descriptor.get("input_schema") or {}
                    required_fields = schema.get("required") or []
                    properties = schema.get("properties") or {}
                    if required_fields:
                        print("")
                        print("必填字段：")
                        for field_name in required_fields:
                            print(f"- {field_name}")
                    if properties:
                        print("")
                        print("参数说明：")
                        for field_name, definition in properties.items():
                            description = ""
                            if isinstance(definition, dict):
                                description = str(definition.get("description", "")).strip()
                            line = f"- {field_name}"
                            if description:
                                line += f"：{description}"
                            print(line)
                return 0

            if not args.tool_name:
                raise ValueError("Missing tool-name.")
            if not args.payload_json:
                raise ValueError("Missing payload-json.")
            payload = json.loads(args.payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload-json must be a JSON object.")
            result = local_tools.execute(tool_name=args.tool_name, payload=payload)
            if args.format == "json":
                print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"工具：{result.tool_name}")
                print(f"动作：{result.action}")
                print(f"终止语义：{result.terminal_state}")
                if result.reason:
                    print(f"原因：{result.reason}")
                if result.output_payload:
                    print("")
                    print("## 输出")
                    print(json.dumps(result.output_payload, ensure_ascii=False, indent=2))
                if result.stdout:
                    print("")
                    print("## stdout")
                    print(result.stdout.rstrip())
                if result.stderr:
                    print("")
                    print("## stderr")
                    print(result.stderr.rstrip())
            return 0
        else:
            case_state = get_case(case_id=args.case_id, store=store)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "history":
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "history": build_case_history_payload(case_state),
                        "case_runtime": build_case_runtime_payload(case_state),
                        "rendered_history": render_case_history(case_state),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render_case_history(case_state, output_format=args.format))
    else:
        if args.format == "json":
            print(json.dumps(_build_case_cli_payload(case_state), ensure_ascii=False, indent=2))
        else:
            print(render_case_state(case_state, output_format=args.format))
    return 0


def _build_case_cli_payload(case_state) -> dict:
    return {
        "case": case_state.to_dict(),
        "case_runtime": build_case_runtime_payload(case_state),
        "rendered_card": render_case_state(case_state),
    }


def _build_context_profile(args: argparse.Namespace) -> dict:
    context_profile = {}
    if args.business_model:
        context_profile["business_model"] = args.business_model
    if args.primary_platform:
        context_profile["primary_platform"] = args.primary_platform
    if args.distribution_channel:
        context_profile["distribution_channel"] = args.distribution_channel
    if args.product_domain:
        context_profile["product_domain"] = args.product_domain
    if args.target_user_role:
        context_profile["target_user_roles"] = args.target_user_role
    if args.constraint:
        context_profile["constraints"] = args.constraint
    if args.context_json:
        extra_context = json.loads(args.context_json)
        context_profile.update(extra_context)
    return context_profile


def _ensure_string_list_or_empty(payload: object) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Expected a list payload.")
    normalized = []
    for item in payload:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _add_context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--business-model",
        choices=["tob", "toc", "internal"],
        help="产品业务类型。",
    )
    parser.add_argument(
        "--primary-platform",
        choices=["pc", "mobile-web", "native-app", "mini-program", "multi-platform"],
        help="主要使用平台。",
    )
    parser.add_argument(
        "--distribution-channel",
        help="产品主要分发或交付渠道。",
    )
    parser.add_argument(
        "--product-domain",
        help="产品所属业务域。",
    )
    parser.add_argument(
        "--target-user-role",
        action="append",
        default=[],
        help="关键用户角色。可重复传入多次。",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="限制条件。可重复传入多次。",
    )
    parser.add_argument(
        "--context-json",
        help="以 JSON 字符串形式传入场景基础信息，用于覆盖或补充前面的上下文字段。",
    )


def _is_session_command(args_list: List[str]) -> bool:
    session_commands = {
        "start",
        "reply",
        "show",
        "history",
        "workspace",
        "serve",
        "agent",
        "approvals",
        "runtime",
        "approve",
        "reject",
        "expire",
        "rules",
        "command",
        "tool",
    }
    index = 0
    while index < len(args_list):
        token = args_list[index]
        if token in session_commands:
            return True
        if token in {"--store-dir", "--format"}:
            index += 2
            continue
        return False
    return False


if __name__ == "__main__":
    sys.exit(main())
