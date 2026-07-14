#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信聊天记录导出工具
===================

使用方法:
    python export.py                          # 导出全部 (CSV+TXT)
    python export.py --csv                    # 仅导出 CSV
    python export.py --txt                    # 仅导出 TXT
    python export.py --json                   # 仅导出 JSON
    python export.py --db                     # 导出到 SQLite 数据库
    python export.py --contact wxid_xxx       # 只导出某个联系人
    python export.py --days 7                 # 最近 N 天
    python export.py --date 2026-07-14        # 指定日期
    python export.py --output ./my_data       # 输出目录
    python export.py --id-list                # 导出微信ID列表(每行一个)
"""

from __future__ import annotations

import csv as _csv
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from wx_common import (
    MSG_TYPE_NAMES,
    ensure_db,
    get_contact_map,
    get_db_paths,
)
from wxManager.model.contact import Person as Contact

ROOT = Path(__file__).resolve().parent


# ============================================================
# 数据查询
# ============================================================


class _MsgDB:
    """轻量封装，按联系人查询消息。"""

    def __init__(self):
        self.paths = get_db_paths()
        self.cmap = get_contact_map()

    def get_messages(self, wxid: str, time_range: tuple = None) -> list[dict]:
        paths = self.paths
        if not paths:
            return []

        conn = sqlite3.connect(paths["msg0_dec"])
        conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
        c = conn.cursor()

        wheres, params = ["StrTalker=?"], [wxid]
        if time_range:
            if time_range[0]:
                ts = int(datetime.strptime(str(time_range[0]), "%Y-%m-%d").timestamp())
                wheres.append("CreateTime>=?")
                params.append(ts)
            if time_range[1]:
                ts = (
                    int(datetime.strptime(str(time_range[1]), "%Y-%m-%d").timestamp())
                    + 86400
                )
                wheres.append("CreateTime<?")
                params.append(ts)

        sql = (
            "SELECT localId,StrTalker,IsSender,Type,SubType,CreateTime,"
            "Status,StrContent,DisplayContent FROM MSG"
            f" WHERE {' AND '.join(wheres)} ORDER BY CreateTime ASC"
        )
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()

        msgs = []
        for r in rows:
            lid, talker, send, typ, sub, ts, _st, content, display = r
            msgs.append(
                {
                    "local_id": lid,
                    "talker": talker,
                    "is_sender": bool(send),
                    "msg_type": typ,
                    "sub_type": sub,
                    "timestamp": ts,
                    "content": (display or content or ""),
                    "str_time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    if ts
                    else "",
                }
            )
        return msgs


def _get_sessions() -> list[dict[str, Any]]:
    """列出所有有聊天记录的会话。"""
    paths = get_db_paths()
    if not paths:
        return []
    conn = sqlite3.connect(paths["msg0_dec"])
    conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
    c = conn.cursor()
    c.execute(
        "SELECT StrTalker, COUNT(*) AS cnt, MAX(CreateTime) AS last_ts "
        "FROM MSG GROUP BY StrTalker ORDER BY last_ts DESC"
    )
    rows = c.fetchall()
    conn.close()

    cmap = get_contact_map()
    sessions = []
    for talker, cnt, last_ts in rows:
        info = cmap.get(talker, {})
        sessions.append(
            {
                "wxid": talker,
                "remark": info.get("remark") or info.get("nickname") or talker,
                "nickname": info.get("nickname", ""),
                "msg_count": cnt,
                "last_time": datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
                if last_ts
                else "",
            }
        )
    return sessions


def _build_contact(wxid: str, cmap: dict) -> Contact:
    info = cmap.get(wxid, {})
    return Contact(
        wxid=wxid,
        remark=info.get("remark") or info.get("nickname") or wxid,
        nickname=info.get("nickname") or wxid,
    )


# ============================================================
# 导出器
# ============================================================


def _type_name(t: int, sub: int = 0) -> str:
    n = MSG_TYPE_NAMES.get(t, f"未知({t})")
    return f"{n}({sub})" if t == 49 and sub else n


def _simplify(text: str, typ: int) -> str:
    if typ == 3:
        return "[图片]"
    if typ == 34:
        return "[语音]"
    if typ == 43:
        return "[视频]"
    if typ == 47:
        return "[表情]"
    if typ == 49 and text:
        m = re.search(r"<title>(.*?)</title>", text)
        return f"[分享] {m.group(1)}" if m else f"[分享] {text[:80]}"
    return text or ""


def _safe_filename(remark: str, wxid: str) -> str:
    """清理文件名：去掉 emoji 和特殊字符。"""
    safe = re.sub(r"[^\w\s\u4e00-\u9fff\-]", "", remark)
    safe = safe.strip().replace(" ", "_")[:60]
    return safe or wxid


def _export_contact(contact: Contact, msgs: list[dict], fmt: str, out_dir: Path):
    """为一个联系人导出指定格式的文件。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = _safe_filename(contact.remark, contact.wxid)

    if fmt == "csv":
        path = out_dir / f"{safe}.csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f)
            w.writerow(["消息ID", "类型", "方向", "时间", "内容"])
            for m in msgs:
                w.writerow(
                    [
                        m["local_id"],
                        _type_name(m["msg_type"], m["sub_type"]),
                        "发送" if m["is_sender"] else "接收",
                        m["str_time"],
                        m["content"][:500].replace("\n", " "),
                    ]
                )

    elif fmt == "txt":
        path = out_dir / f"{safe}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"聊天记录: {contact.remark} ({contact.wxid})\n")
            f.write(f"{'=' * 60}\n\n")
            for m in msgs:
                d = "→" if m["is_sender"] else "←"
                c = _simplify(m["content"], m["msg_type"])
                f.write(
                    f"[{m['str_time']}] {d} [{_type_name(m['msg_type'], m['sub_type'])}] {c[:200]}\n"
                )

    elif fmt == "json":
        path = out_dir / f"{safe}.json"
        data = [
            {
                "id": m["local_id"],
                "time": m["str_time"],
                "direction": "send" if m["is_sender"] else "receive",
                "type": _type_name(m["msg_type"], m["sub_type"]),
                "type_code": m["msg_type"],
                "sub_type": m["sub_type"],
                "content": m["content"],
            }
            for m in msgs
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return len(msgs)


# ============================================================
# 导出到 SQLite 数据库
# ============================================================


def _export_db(db_path: Path, msg_db: _MsgDB, cmap: dict, time_range: tuple | None):
    """将所有联系人聊天记录导出到一个 SQLite 数据库。"""
    sessions = _get_sessions()
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE contacts (
            wxid TEXT PRIMARY KEY, nickname TEXT, remark TEXT,
            alias TEXT, msg_count INTEGER, last_time TEXT
        )
    """)
    c.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, wxid TEXT REFERENCES contacts(wxid),
            local_id INTEGER, is_sender INTEGER, msg_type INTEGER,
            sub_type INTEGER, timestamp INTEGER, content TEXT, str_time TEXT
        )
    """)
    c.execute("CREATE INDEX idx_messages_wxid ON messages(wxid)")
    c.execute("CREATE INDEX idx_messages_time ON messages(timestamp)")

    for s in sessions:
        alias = cmap.get(s["wxid"], {}).get("alias", "")
        c.execute(
            "INSERT OR REPLACE INTO contacts VALUES (?,?,?,?,?,?)",
            (
                s["wxid"],
                s.get("nickname"),
                s.get("remark"),
                alias,
                s["msg_count"],
                s["last_time"],
            ),
        )

    total = 0
    for s in sessions:
        msgs = msg_db.get_messages(s["wxid"], time_range)
        if not msgs:
            continue
        for m in msgs:
            c.execute(
                "INSERT INTO messages (wxid,local_id,is_sender,msg_type,"
                "sub_type,timestamp,content,str_time) VALUES (?,?,?,?,?,?,?,?)",
                (
                    m["talker"],
                    m["local_id"],
                    int(m["is_sender"]),
                    m["msg_type"],
                    m["sub_type"],
                    m["timestamp"],
                    m["content"],
                    m["str_time"],
                ),
            )
        total += len(msgs)

    conn.commit()
    conn.close()
    print(f"[+] 数据库: {db_path}")
    print(f"    联系人: {len(sessions)}, 消息: {total}")


# ============================================================
# 辅助
# ============================================================


def _parse_time(args: dict) -> tuple | None:
    if args.get("days"):
        s = (datetime.now() - timedelta(days=int(args["days"]))).strftime("%Y-%m-%d")
        return (s, None)
    if args.get("date"):
        return (args["date"], args["date"])
    return None


# ============================================================
# CLI
# ============================================================


def main():
    raw = sys.argv[1:]
    if not raw or raw[0] in ("--help", "-h"):
        print(__doc__)
        return

    want_db = "--db" in raw
    want_id_list = "--id-list" in raw
    has_fmt = (
        "--csv" in raw or "--txt" in raw or "--json" in raw or want_db or want_id_list
    )
    want_csv = "--csv" in raw or (not has_fmt)
    want_txt = "--txt" in raw or (not has_fmt)
    want_json = "--json" in raw
    contact_wxid = None
    days = None
    date_str = None
    output_dir = ROOT

    i = 0
    while i < len(raw):
        if raw[i] == "--contact" and i + 1 < len(raw):
            contact_wxid = raw[i + 1]
            i += 2
        elif raw[i] == "--days" and i + 1 < len(raw):
            days = raw[i + 1]
            i += 2
        elif raw[i] == "--date" and i + 1 < len(raw):
            date_str = raw[i + 1]
            i += 2
        elif raw[i] == "--output" and i + 1 < len(raw):
            output_dir = Path(raw[i + 1])
            i += 2
        else:
            i += 1

    if not ensure_db():
        return

    db = _MsgDB()
    cmap = get_contact_map()
    time_range = _parse_time({"days": days, "date": date_str})

    # 快捷导出：ID 列表
    if want_id_list:
        sessions = _get_sessions()
        out_path = output_dir / "send_list.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            for s in sessions:
                alias = cmap.get(s["wxid"], {}).get("alias", "")
                f.write((alias or s["wxid"]) + "\n")
        print(f"[+] ID列表: {out_path} ({len(sessions)} 个)")
        return

    # 快捷导出：SQLite 数据库
    if want_db:
        _export_db(output_dir / "wx_export.db", db, cmap, time_range)
        return

    formats = []
    if want_csv:
        formats.append("csv")
    if want_txt:
        formats.append("txt")
    if want_json:
        formats.append("json")

    # 单联系人
    if contact_wxid:
        contact = _build_contact(contact_wxid, cmap)
        msgs = db.get_messages(contact_wxid, time_range)
        print(f"[*] {contact.remark}: {len(msgs)} 条消息")
        for fmt in formats:
            out = output_dir / fmt if len(formats) > 1 else output_dir
            _export_contact(contact, msgs, fmt, out)
        print("[✓] 导出完成")
        return

    # 全部会话
    sessions = _get_sessions()
    total = 0
    print(f"[*] 共 {len(sessions)} 个会话")
    for s in sessions:
        contact = _build_contact(s["wxid"], cmap)
        msgs = db.get_messages(s["wxid"], time_range)
        if not msgs:
            continue
        for fmt in formats:
            _export_contact(contact, msgs, fmt, output_dir / fmt)
        total += len(msgs)

    print(f"[✓] 导出完成: {len(sessions)} 会话, {total} 条消息")


if __name__ == "__main__":
    main()
