from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from pm_method_agent.orchestrator import run_analysis_with_context
from pm_method_agent.renderers import render_case_history, render_case_state
from pm_method_agent.session_service import create_case, default_store, get_case, reply_to_case


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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
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
    print(render_case_state(case_state, output_format=args.format))
    return 0


def _run_session_command(argv: List[str]) -> int:
    parser = build_session_parser()
    args = parser.parse_args(argv)
    store = default_store(args.store_dir)

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
        else:
            case_state = get_case(case_id=args.case_id, store=store)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "history":
        print(render_case_history(case_state, output_format=args.format))
    else:
        print(render_case_state(case_state, output_format=args.format))
    return 0


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
    session_commands = {"start", "reply", "show", "history"}
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
