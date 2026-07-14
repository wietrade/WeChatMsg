#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信通讯录管理工具
=================

使用方法:
    python contacts.py                    # 导出全部联系人
    python contacts.py --list             # 列出所有联系人
    python contacts.py --search 张三       # 搜索联系人
    python contacts.py --groups           # 列出所有群聊
    python contacts.py --stats            # 通讯录统计
    python contacts.py --refresh          # 重新解密数据库
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path
from typing import Any

from wx_common import (
    decrypt_db,
    ensure_db,
    get_db_paths,
)

CONTACTS_CSV = Path(__file__).resolve().parent / "contacts.csv"


def _get_contacts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """从数据库读取所有联系人。"""
    c = conn.cursor()
    tables = [
        t[0]
        for t in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]

    if "Contact" not in tables:
        print("[-] 数据库中没有 Contact 表")
        return []

    actual_cols = [r[1] for r in c.execute("PRAGMA table_info(Contact)").fetchall()]
    col_str = ",".join(actual_cols)
    rows = c.execute(f"SELECT {col_str} FROM Contact ORDER BY Type ASC").fetchall()
    return [dict(zip(actual_cols, row)) for row in rows]


def _display(c: dict[str, Any], idx: int = 0) -> str:
    """格式化显示一个联系人。"""
    name = c.get("NickName", "") or ""
    remark = c.get("Remark", "") or ""
    alias = c.get("Alias", "") or ""
    wxid = c.get("UserName", "") or ""
    ctype = c.get("Type", 0)

    labels = {
        1: "[好友]",
        2: "[群聊]",
        3: "[公众号]",
        33: "[微信豆]",
        259: "[直播]",
        515: "[视频号]",
        2051: "[企业微信]",
    }
    label = labels.get(ctype, f"[类型{ctype}]")

    display_name = remark or name or wxid
    parts = [f"{idx}.", label, display_name]
    if name and name != display_name:
        parts.append(f"(昵称: {name})")
    if alias:
        parts.append(f"(微信号: {alias})")
    if wxid and not wxid.startswith("wxid_"):
        parts.append(f"({wxid})")
    return " ".join(parts)


def _open_db():
    """打开已解密的联系人数据库。"""
    paths = get_db_paths()
    if not paths:
        return None
    contact_dec = Path(paths["contact_dec"])
    if not contact_dec.exists():
        key = paths.get("key")
        if key:
            decrypt_db(key, paths["contact_src"], contact_dec)
    if not contact_dec.exists():
        print("[-] 解密联系人数据库失败")
        return None
    conn = sqlite3.connect(str(contact_dec))
    conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
    return conn


# ============================================================


def cmd_list(args: list[str]) -> None:
    """列出/搜索联系人。"""
    conn = _open_db()
    if not conn:
        return
    contacts = _get_contacts(conn)
    conn.close()

    search = args[0] if args else None
    show_groups = search == "--groups"
    if show_groups:
        search = None

    filtered = []
    for i, c in enumerate(contacts, 1):
        name = c.get("NickName", "") or ""
        remark = c.get("Remark", "") or ""
        alias = c.get("Alias", "") or ""
        ctype = c.get("Type", 0)

        if show_groups and ctype != 2:
            continue
        if (
            search
            and search not in name
            and search not in remark
            and search not in alias
        ):
            continue
        filtered.append((i, c))

    if not filtered:
        print("(无结果)")
        return
    print(f"\n{'=' * 60}")
    print(f"共 {len(filtered)} 个联系人\n")
    for idx, c in filtered:
        print(_display(c, idx))


def cmd_export(args: list[str]) -> None:
    """导出联系人到 CSV。"""
    conn = _open_db()
    if not conn:
        return

    c = conn.cursor()
    actual_cols = [r[1] for r in c.execute("PRAGMA table_info(Contact)").fetchall()]
    rows = c.execute(
        f"SELECT {','.join(actual_cols)} FROM Contact ORDER BY Type ASC"
    ).fetchall()
    conn.close()

    out_path = Path(args[0]) if args else CONTACTS_CSV
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(actual_cols)
        w.writerows(rows)

    total = len(rows)
    type_idx = actual_cols.index("Type")
    friends = sum(1 for r in rows if r[type_idx] == 1)
    groups = sum(1 for r in rows if r[type_idx] == 2)
    official = sum(1 for r in rows if r[type_idx] == 3)
    print(f"[+] 导出完成: {total} 条记录 -> {out_path}")
    print(
        f"    好友: {friends}, 群聊: {groups}, 公众号: {official}, "
        f"其他: {total - friends - groups - official}"
    )


def cmd_stats(args: list[str]) -> None:
    """通讯录统计信息。"""
    conn = _open_db()
    if not conn:
        return
    contacts = _get_contacts(conn)
    conn.close()

    total = len(contacts)
    friends = sum(1 for c in contacts if c.get("Type") == 1)
    groups = sum(1 for c in contacts if c.get("Type") == 2)
    official = sum(1 for c in contacts if c.get("Type") == 3)
    no_name = sum(1 for c in contacts if not c.get("NickName") and not c.get("Remark"))
    has_remark = sum(1 for c in contacts if c.get("Remark"))

    print(f"\n{'=' * 40}")
    print("     通讯录统计")
    print(f"{'=' * 40}")
    print(f"  总数:         {total}")
    print(f"  好友:         {friends}")
    print(f"  群聊:         {groups}")
    print(f"  公众号:       {official}")
    print(f"  有备注:       {has_remark}")
    print(f"  无名称:       {no_name}")
    print(f"{'=' * 40}")


def cmd_refresh(args: list[str]) -> None:
    """清除缓存，重新解密。"""
    paths = get_db_paths()
    if paths:
        p = Path(paths["contact_dec"])
        if p.exists():
            p.unlink()
            print("[*] 已清除解密缓存")
    if ensure_db():
        print("[+] 数据库重新解密成功")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("--help", "-h"):
        print(__doc__)
        return

    cmd = args[0]
    cmd_args = args[1:]

    if cmd in ("--list", "--search", "--groups"):
        cmd_list(cmd_args[:1] if cmd_args else [cmd])
    elif cmd == "--export":
        cmd_export(cmd_args)
    elif cmd == "--stats":
        cmd_stats(cmd_args)
    elif cmd == "--refresh":
        cmd_refresh(cmd_args)
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
