#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信聊天记录查询工具
===================

使用方法:
    python messages.py                         # 最近 24 小时消息
    python messages.py wxid_xxx                # 查某个联系人的聊天
    python messages.py --search "关键词"       # 搜索消息内容
    python messages.py --date 2026-07-14       # 查某天的消息
    python messages.py --days 7                # 最近 7 天
    python messages.py wxid_xxx -n 50          # 指定显示条数
    python messages.py --list                  # 列出最近有消息的联系人
    python messages.py --sql "SELECT ..."      # 执行原始 SQL
    python messages.py --refresh               # 重新解密数据库
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from wx_common import (
    MSG_TYPE_NAMES,
    contact_display_name,
    ensure_db,
    get_contact_map,
    get_db_paths,
)


def _ensure_msg_db() -> bool:
    """确保 MSG0 数据库已解密。"""
    return ensure_db()


def _connect_msg():
    """连接已解密的 MSG0 数据库。"""
    paths = get_db_paths()
    if not paths or not Path(paths["msg0_dec"]).exists():
        if not _ensure_msg_db():
            return None
    conn = sqlite3.connect(paths["msg0_dec"])
    conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
    conn.row_factory = sqlite3.Row
    return conn


def _query(sql: str, params: list | None = None) -> list[sqlite3.Row]:
    """执行 SQL 查询，返回命名元组风格的行。"""
    conn = _connect_msg()
    if not conn:
        return []
    cur = conn.cursor()
    cur.execute(sql, params or [])
    rows = cur.fetchall()
    conn.close()
    return rows


def _fmt(row: sqlite3.Row, cmap: dict[str, Any] | None = None) -> str:
    """格式化单条消息为可读文本。"""
    if cmap is None:
        cmap = get_contact_map()

    talker = row["StrTalker"]
    is_sender = row["IsSender"]
    msg_type = row["Type"]
    sub_type = row["SubType"]
    timestamp = row["CreateTime"]
    content = row["StrContent"] or row["DisplayContent"] or ""

    name = contact_display_name(talker, cmap)
    direction = "→" if is_sender else "←"
    type_name = MSG_TYPE_NAMES.get(msg_type, f"类型{msg_type}")
    if msg_type == 49 and sub_type:
        type_name = f"{type_name}({sub_type})"

    try:
        t = datetime.fromtimestamp(int(timestamp)).strftime("%m-%d %H:%M")
    except Exception:
        t = str(timestamp)

    text = str(content)[:200].replace("\n", " | ")
    return f"[{t}] {direction} {name} [{type_name}] {text}"


def _show(rows: list[sqlite3.Row], limit: int = 30) -> None:
    """显示消息列表。"""
    if not rows:
        print("(无结果)")
        return
    cmap = get_contact_map()
    for row in rows[:limit]:
        print(_fmt(row, cmap))
    if len(rows) > limit:
        print(f"\n... 还有 {len(rows) - limit} 条，可用 -n N 显示更多")
    print(f"\n共 {len(rows)} 条")


# ============================================================


def cmd_list_contacts(args: list[str]) -> None:
    """列出最近有消息的联系人。"""
    rows = _query(
        "SELECT StrTalker, COUNT(*) AS cnt, MAX(CreateTime) AS last_ts "
        "FROM MSG GROUP BY StrTalker ORDER BY last_ts DESC LIMIT 50"
    )
    cmap = get_contact_map()
    print(f"\n{'名称':<30} {'微信号':<35} {'条数':<6} {'最后时间'}")
    print("-" * 85)
    for r in rows:
        name = contact_display_name(r["StrTalker"], cmap)
        try:
            t = datetime.fromtimestamp(int(r["last_ts"])).strftime("%m-%d %H:%M")
        except Exception:
            t = str(r["last_ts"])
        wid = r["StrTalker"]
        dw = wid if len(wid) < 34 else wid[:15] + "..."
        dn = name[:28] if len(name) > 28 else name
        print(f"{dn:<30} {dw:<35} {r['cnt']:<6} {t}")
    print(f"\n共 {len(rows)} 个对话对象")


def cmd_search(args: list[str]) -> None:
    """搜索消息内容。"""
    keyword = args[0] if args else input("搜索关键词: ")
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
    # 转义 SQL 通配符
    safe = keyword.replace("%", r"\%").replace("_", r"\_")
    rows = _query(
        "SELECT * FROM MSG WHERE StrContent LIKE ? ESCAPE '\\' "
        "ORDER BY CreateTime DESC LIMIT ?",
        [f"%{safe}%", limit],
    )
    print(f"搜索 [{keyword}] 的结果:")
    print("-" * 60)
    _show(rows, limit)


def cmd_user(args: list[str]) -> None:
    """查询指定联系人的聊天记录。"""
    wxid = args[0]
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20

    rows = _query(
        "SELECT * FROM MSG WHERE StrTalker=? ORDER BY CreateTime DESC LIMIT ?",
        [wxid, limit],
    )
    name = contact_display_name(wxid)
    print(f"与 [{name}] ({wxid}) 的聊天记录 (最近{limit}条):")
    print("-" * 60)
    _show(rows, limit)


def cmd_date(args: list[str]) -> None:
    """查询某天的消息。"""
    date_str = args[0]
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        ts1, ts2 = int(dt.timestamp()), int(dt.timestamp()) + 86400
    except ValueError:
        print("日期格式: YYYY-MM-DD")
        return
    rows = _query(
        "SELECT * FROM MSG WHERE CreateTime BETWEEN ? AND ? ORDER BY CreateTime DESC LIMIT ?",
        [ts1, ts2, limit],
    )
    print(f"{date_str} 的消息:")
    print("-" * 60)
    _show(rows, limit)


def cmd_days(args: list[str]) -> None:
    """查询最近 N 天的消息。"""
    n = int(args[0]) if args else 7
    limit = int(args[1]) if len(args) > 1 and args[1].isdigit() else 50
    ts = int((datetime.now() - timedelta(days=n)).timestamp())
    rows = _query(
        "SELECT * FROM MSG WHERE CreateTime>=? ORDER BY CreateTime DESC LIMIT ?",
        [ts, limit],
    )
    print(f"最近 {n} 天的消息:")
    print("-" * 60)
    _show(rows, limit)


def cmd_recent(args: list[str]) -> None:
    """最近 24 小时消息。"""
    ts = int((datetime.now() - timedelta(hours=24)).timestamp())
    rows = _query(
        "SELECT * FROM MSG WHERE CreateTime>=? ORDER BY CreateTime DESC LIMIT 20",
        [ts],
    )
    print("=== 最近 24 小时消息 ===")
    _show(rows, 20)


def cmd_sql(args: list[str]) -> None:
    """执行原始 SQL 查询。"""
    sql = " ".join(args) if args else input("SQL> ")
    conn = _connect_msg()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute(sql)
        if sql.strip().upper().startswith("SELECT"):
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            print(" | ".join(cols))
            print("-" * 80)
            for r in rows[:100]:
                print(" | ".join(str(c)[:40] for c in r))
            print(f"\n共 {len(rows)} 行")
        else:
            conn.commit()
            print(f"影响行数: {cur.rowcount}")
    except Exception as e:
        print(f"SQL错误: {e}")
    finally:
        conn.close()


def cmd_refresh(args: list[str]) -> None:
    """清除缓存，强制重新解密。"""
    paths = get_db_paths()
    if paths:
        for key in ("msg0_dec", "contact_dec"):
            p = Path(paths[key])
            if p.exists():
                p.unlink()
                print(f"[*] 已清除: {p.name}")
    print("[*] 重新解密数据库...")
    if ensure_db():
        print("[+] 完成")


def _parse_global_opts(args: list[str]) -> tuple[list[str], int]:
    """解析全局选项（如 -n N），返回 (剩余参数, limit)。"""
    limit = 30
    remaining = []
    i = 0
    while i < len(args):
        if args[i] in ("-n", "-l") and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    return remaining, limit


def main():
    raw_args = sys.argv[1:]
    if not raw_args or raw_args[0] in ("--help", "-h"):
        print(__doc__)
        return

    args, global_limit = _parse_global_opts(raw_args)
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    cmd_args = args[1:]
    if global_limit != 30:
        cmd_args = cmd_args + [str(global_limit)]

    commands = {
        "--list": cmd_list_contacts,
        "--contacts": cmd_list_contacts,
        "--search": cmd_search,
        "--date": cmd_date,
        "--days": cmd_days,
        "--sql": cmd_sql,
        "--refresh": cmd_refresh,
    }

    if cmd in commands:
        commands[cmd](cmd_args)
    elif cmd.startswith("-"):
        print(f"未知选项: {cmd}")
        print(__doc__)
    else:
        cmd_user([cmd] + cmd_args)


if __name__ == "__main__":
    main()
