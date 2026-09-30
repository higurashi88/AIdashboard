import logging
from time import perf_counter
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.db import connections

from apps.mcp.registry import mcp_server
from apps.services import domain


logger = logging.getLogger(__name__)


def _summarize_value(value):
    if isinstance(value, str):
        return value if len(value) <= 80 else f"{value[:77]}..."
    if isinstance(value, (list, tuple)):
        items = [_summarize_value(item) for item in value[:10]]
        if len(value) > 10:
            items.append(f"...ほか{len(value) - 10}件")
        return items
    if isinstance(value, dict):
        return {
            str(key): _summarize_value(item)
            for key, item in list(value.items())[:10]
        }
    return value


def _summarize_arguments(arguments):
    return {key: _summarize_value(value) for key, value in arguments.items()}


def _validation_error_message(exc):
    if hasattr(exc, "message_dict"):
        details = "; ".join(
            f"{field}: {', '.join(str(message) for message in messages)}"
            for field, messages in exc.message_dict.items()
        )
    else:
        details = "; ".join(str(message) for message in exc.messages)
    return f"入力内容を確認してください。{details}"


def _domain_error_message(exc):
    if isinstance(exc, domain.ProjectResolutionError):
        candidates = ", ".join(exc.candidates) if exc.candidates else "なし"
        return (
            "プロジェクトを特定できませんでした。"
            "list_projects() で一覧を確認してください。"
            f"候補: {candidates}"
        )
    if isinstance(exc, domain.TaskResolutionError):
        return (
            "タスクを特定できませんでした。"
            "list_tasks() でキーを確認してから、もう一度呼んでください。"
        )
    if isinstance(exc, ValidationError):
        return _validation_error_message(exc)
    if isinstance(exc, domain.DomainServiceError):
        return f"処理を完了できませんでした。入力値を確認してください。詳細: {exc}"
    return "ダッシュボード内部でエラーが発生しました。作業は継続し、後で再確認してください。"


async def _invoke(tool_name, function, arguments):
    started = perf_counter()
    summarized = _summarize_arguments(arguments)

    def call_domain():
        try:
            return function(**arguments)
        finally:
            # Django's ASGI request cleanup does not surround MCP tool handlers.
            connections.close_all()

    try:
        result = await sync_to_async(call_domain, thread_sensitive=True)()
    except (
        domain.DomainServiceError,
        ValidationError,
    ) as exc:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        message = _domain_error_message(exc)
        logger.warning(
            "mcp_tool_call",
            extra={
                "mcp_tool": tool_name,
                "mcp_arguments": summarized,
                "mcp_success": False,
                "mcp_duration_ms": duration_ms,
                "mcp_error": message,
            },
        )
        return {"ok": False, "error": message}
    except Exception:
        duration_ms = round((perf_counter() - started) * 1000, 2)
        message = _domain_error_message(None)
        logger.exception(
            "mcp_tool_call",
            extra={
                "mcp_tool": tool_name,
                "mcp_arguments": summarized,
                "mcp_success": False,
                "mcp_duration_ms": duration_ms,
                "mcp_error": message,
            },
        )
        return {"ok": False, "error": message}

    duration_ms = round((perf_counter() - started) * 1000, 2)
    logger.info(
        "mcp_tool_call",
        extra={
            "mcp_tool": tool_name,
            "mcp_arguments": summarized,
            "mcp_success": True,
            "mcp_duration_ms": duration_ms,
        },
    )
    return result


@mcp_server.tool(
    description=(
        "稼働中のプロジェクトと未処理件数を一覧にする。"
        "対象プロジェクトが曖昧なとき、またはget_projectで特定できなかったときに呼ぶこと。"
    )
)
async def list_projects() -> Any:
    return await _invoke("list_projects", domain.list_projects, {})


@mcp_server.tool(
    description=(
        "プロジェクトの未処理タスク、本人待ち、直近活動、自動実行状況をまとめて取得する。"
        "作業を始める前に必ず最初に呼ぶこと。cwdを渡すとプロジェクトを自動判定する。"
        'actor_type="human"は人間が主体で進めるため着手せず、human_tasksに分離して返す。'
    )
)
async def get_project(slug: str | None = None, cwd: str | None = None) -> Any:
    return await _invoke(
        "get_project",
        domain.get_project,
        {"slug": slug, "cwd": cwd},
    )


@mcp_server.tool(
    description=(
        "プロジェクト横断でタスクを絞り込み・検索する。"
        "既存タスクを探すときと、create_taskの前に重複がないか確認するときに呼ぶこと。"
    )
)
async def list_tasks(
    project: str | None = None,
    status: str | None = None,
    query: str | None = None,
    limit: int = 50,
) -> Any:
    return await _invoke(
        "list_tasks",
        domain.list_tasks,
        {
            "project": project,
            "status": status,
            "query": query,
            "limit": limit,
        },
    )


@mcp_server.tool(
    description=(
        "新しいタスクを採番して登録する。"
        "依頼が既存タスクに該当しないことをlist_tasksで確認した後に呼び、返されたkeyを以後使うこと。"
    )
)
async def create_task(
    project: str,
    title: str,
    detail: str | None = None,
    priority: int = 0,
    status: str = "todo",
    actor_type: str = "agent",
    parent: str | None = None,
    agent: str = "claude_code",
) -> Any:
    return await _invoke(
        "create_task",
        domain.create_task,
        {
            "project": project,
            "title": title,
            "detail": detail,
            "priority": priority,
            "status": status,
            "actor_type": actor_type,
            "parent": parent,
            "created_by": agent,
        },
    )


@mcp_server.tool(
    description=(
        "既存タスクの状態・内容を更新し、必要なら進捗メモを追記する。"
        "着手・完了・ブロック・本人判断待ちが発生した時点で直ちに呼ぶこと。"
        "本人の判断が必要ならstatus=awaiting_userとnoteに判断事項を指定する。"
        'actor_type="human"は人間が主体で進めるタスクなので、エージェントは着手しない。'
    )
)
async def update_task(
    key: str,
    status: str | None = None,
    title: str | None = None,
    detail: str | None = None,
    priority: int | None = None,
    actor_type: str | None = None,
    note: str | None = None,
    agent: str = "claude_code",
) -> Any:
    return await _invoke(
        "update_task",
        domain.update_task,
        {
            "key": key,
            "status": status,
            "title": title,
            "detail": detail,
            "priority": priority,
            "actor_type": actor_type,
            "note": note,
            "actor": agent,
        },
    )


@mcp_server.tool(
    description=(
        "セッションで実施した内容と扱ったタスクを記録する。"
        "作業を終えてユーザーへ最終報告する直前に必ず呼ぶこと。summaryは1〜3行で簡潔に書く。"
    )
)
async def report_session(
    project: str,
    summary: str,
    task_keys: list[str] | None = None,
    agent: str = "claude_code",
) -> Any:
    return await _invoke(
        "report_session",
        domain.report_session,
        {
            "project": project,
            "summary": summary,
            "task_keys": task_keys,
            "agent": agent,
        },
    )
