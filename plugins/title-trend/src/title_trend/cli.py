from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import sys
from importlib.resources import files
from pathlib import Path

from .config import load_settings, save_settings
from .credentials import (
    credential_status,
    delete_credentials,
    get_secret,
    secure_backend,
    set_secret,
)
from .errors import SafeError
from .service import Analyzer, simulated_report


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown command arguments, which might be a pasted password.
        self.exit(
            2, "参数无效。运行 title-trend --help 查看用法；凭证只通过 configure 隐藏输入。\n"
        )


def hidden(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise SafeError("interactive", "凭证配置须在交互式本地终端执行，禁止管道或命令行传入密码。")
    value = getpass.getpass(prompt).strip()
    if not value:
        raise SafeError("credential_value", "凭证不能为空。")
    return value


def configure():
    if not sys.stdin.isatty():
        raise SafeError("interactive", "请在交互式本地终端配置凭证，禁止管道输入密码。")
    secure_backend()
    existing = load_settings()
    settings = existing
    print("标题理解与建议由 Codex 等当前 Agent 提供，仅配置 DataForSEO 凭证。")
    for slot, prompt in (
        ("dataforseo-login", "DataForSEO API login（隐藏输入）: "),
        ("dataforseo-password", "DataForSEO API password（隐藏输入）: "),
    ):
        if (
            get_secret(slot, False)
            and input(f"{slot} 已配置，替换？[y/N]: ").strip().lower() != "y"
        ):
            continue
        set_secret(slot, hidden(prompt))
    save_settings(settings)
    print("配置完成。凭证仅保存至系统凭证库；普通配置不含凭证。")


async def verify_coverage(output: Path):
    # One bounded batch, exactly ten representative Chinese queries; no model service.
    from .models import MARKETS

    keywords = [
        "人工智能",
        "Python 自动化",
        "新能源车",
        "育儿",
        "失眠",
        "退休养老",
        "考研",
        "露营",
        "情绪价值",
        "微信排版",
    ]
    analyzer = Analyzer()
    data, status, calls, fetched = await analyzer.provider.query(keywords, MARKETS["CN"])
    body = {
        "simulated": False,
        "market": MARKETS["CN"].model_dump(),
        "keywords": [d.model_dump(mode="json") for d in data],
        "source_status": status,
        "status_fetched_at": fetched.isoformat() if fetched else None,
        "requests": calls,
    }
    output.write_text(json.dumps(body, ensure_ascii=False, indent=2))
    print(f"覆盖验证结果已写入 {output}；最多1个付费POST，缓存命中时不请求。")
    if any(d.status in {"request_failed", "unsupported", "stale"} for d in data):
        raise SafeError("coverage_incomplete", "真实覆盖验证未完成或存在失败，详细原因见输出。")


def main():
    logging.disable(logging.CRITICAL)
    parser = SafeArgumentParser(prog="title-trend", description="公众号标题的外部搜索趋势参考")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("configure")
    sub.add_parser("config-path")
    credentials = sub.add_parser("credentials")
    credentials.add_argument("action", choices=["status", "delete"])
    serve = sub.add_parser("serve")
    serve.add_argument("--demo", action="store_true", help="显式模拟模式，不访问凭证或API")
    prepare = sub.add_parser("prepare", help="返回jieba分词供当前Agent选词，不请求外部API")
    prepare.add_argument("title")
    prepare.add_argument("--market", default="CN", choices=["CN", "HK", "TW"])
    analyze = sub.add_parser("analyze", help="查询Agent提供的候选词并评分；不调用模型API")
    analyze.add_argument("title")
    analyze.add_argument("--market", default="CN", choices=["CN", "HK", "TW"])
    analyze.add_argument("--demo", action="store_true")
    analyze.add_argument("--json", action="store_true")
    analyze.add_argument("--selection-file", type=Path, help="当前Agent生成的候选词JSON")
    analyze.add_argument("--advice-file", type=Path, help="当前Agent基于已返回数据生成的建议JSON")
    preview = sub.add_parser("preview")
    preview.add_argument("--output", type=Path, default=Path("title-trend-preview.html"))
    verify = sub.add_parser("verify-coverage")
    verify.add_argument("--output", type=Path, default=Path("coverage-real.json"))
    args = parser.parse_args()
    try:
        if args.command == "configure":
            configure()
        elif args.command == "config-path":
            from .config import config_dir

            print(config_dir() / "config.json")
        elif args.command == "credentials":
            if args.action == "status":
                print(json.dumps(credential_status(), ensure_ascii=False, indent=2))
            else:
                delete_credentials()
                print("已删除 title-trend 的 DataForSEO 凭证及旧版遗留模型凭证（如有）。")
        elif args.command == "serve":
            from .server import run_stdio

            asyncio.run(run_stdio(args.demo))
        elif args.command == "prepare":
            print(
                json.dumps(
                    Analyzer().prepare(args.title, args.market), ensure_ascii=False, indent=2
                )
            )
        elif args.command == "analyze":
            from .agent import validate_advice
            from .server import text_report

            if args.demo:
                if args.selection_file or args.advice_file:
                    raise SafeError(
                        "demo",
                        "CLI固定模拟预览不接受候选词或建议文件；MCP模拟服务可验证完整Agent流程。",
                    )
                report = simulated_report(args.title, args.market)
            else:
                if args.selection_file is None:
                    raise SafeError(
                        "selection_required",
                        "请先由当前 Agent 选词，再用 --selection-file 传入JSON；Python不调用模型。可先运行 title-trend prepare。",
                    )
                try:
                    selected = json.loads(args.selection_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    raise SafeError("selection_file", "无法读取候选词JSON文件。") from None
                report, selection = asyncio.run(
                    Analyzer().analyze(args.title, selected, args.market)
                )
                if args.advice_file:
                    try:
                        raw = json.loads(args.advice_file.read_text(encoding="utf-8"))
                        report.advice = validate_advice(raw, report.title, selection)
                    except (OSError, ValueError, TypeError, AttributeError):
                        raise SafeError(
                            "advice_file", "建议JSON未通过主题/事实/结构校验。"
                        ) from None
                    report.stage = "complete"
            print(report.model_dump_json(indent=2) if args.json else text_report(report))
        elif args.command == "preview":
            report = simulated_report()
            html = files("title_trend").joinpath("ui/report.html").read_text(encoding="utf-8")
            data = (
                report.model_dump_json()
                .replace("<", "\\u003c")
                .replace(">", "\\u003e")
                .replace("&", "\\u0026")
            )
            html = html.replace(
                "<!-- PREVIEW_DATA -->",
                f'<script type="application/json" id="preview-data">{data}</script>',
            )
            args.output.write_text(html, encoding="utf-8")
            print(f"模拟预览已生成：{args.output.resolve()}；此预览不能代替 MCP Apps 宿主联调。")
        elif args.command == "verify-coverage":
            asyncio.run(verify_coverage(args.output))
    except SafeError as error:
        print(error.message, file=sys.stderr)
        raise SystemExit(1) from None
    except (Exception, KeyboardInterrupt):
        print("操作未完成。请检查本地配置与目录权限；未输出敏感错误详情。", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
