"""
微信工具共享模块
================
提供解密、密钥加载、联系人查询等公共功能。
所有工具脚本统一从这里导入，消除重复代码。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES

# ============================================================
# 常量
# ============================================================
ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)

KEY_CACHE = ROOT / "wx_cache.json"

SQLITE_HEADER = b"SQLite format 3\x00"
PAGE_SIZE = 4096
ITER = 64000
KEY_SIZE = 32

MSG_TYPE_NAMES = {
    1: "文本",
    3: "图片",
    34: "语音",
    37: "好友验证",
    40: "好友推荐",
    42: "名片",
    43: "视频",
    47: "表情",
    48: "位置",
    49: "分享/引用",
    50: "视频号",
    51: "系统消息",
    10000: "系统通知",
    436207665: "红包",
    419430449: "转账",
}


# ============================================================
# 密钥
# ============================================================


def load_key() -> str | None:
    """从缓存文件加载密钥。"""
    if KEY_CACHE.exists():
        try:
            return json.loads(KEY_CACHE.read_text(encoding="utf-8")).get("key")
        except Exception:
            return None
    return None


def load_cache() -> dict[str, Any] | None:
    """加载缓存文件全部内容。"""
    if KEY_CACHE.exists():
        try:
            return json.loads(KEY_CACHE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_wx_dir() -> str | None:
    """从缓存获取微信数据目录。"""
    cache = load_cache()
    if cache and cache.get("wx_dir"):
        return cache["wx_dir"]
    return None


def get_wxid() -> str | None:
    """从缓存获取 wxid。"""
    cache = load_cache()
    if cache and cache.get("wxid"):
        return cache["wxid"]
    return None


# ============================================================
# 数据库解密
# ============================================================


def decrypt_db(key_hex: str, src_path: str, out_path: str | Path) -> bool:
    """解密微信 SQLite 数据库文件。"""
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size > 1000:
        return True

    pw = bytes.fromhex(key_hex)
    try:
        with open(src_path, "rb") as f:
            blist = f.read()
    except FileNotFoundError:
        print(f"[-] 源数据库不存在: {src_path}")
        return False

    salt = blist[:16]
    bk = hashlib.pbkdf2_hmac("sha1", pw, salt, ITER, KEY_SIZE)
    first = blist[16:PAGE_SIZE]
    ms = bytes([(salt[i] ^ 58) for i in range(16)])
    mk = hashlib.pbkdf2_hmac("sha1", bk, ms, 2, KEY_SIZE)
    hm = hmac.new(mk, first[:-32], hashlib.sha1)
    hm.update(b"\x01\x00\x00\x00")
    if hm.digest() != first[-32:-12]:
        print("[-] 密钥验证失败")
        return False

    pages = [blist[i : i + PAGE_SIZE] for i in range(PAGE_SIZE, len(blist), PAGE_SIZE)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(SQLITE_HEADER)
        t = AES.new(bk, AES.MODE_CBC, first[-48:-32])
        f.write(t.decrypt(first[:-48]))
        f.write(first[-48:])
        for p in pages:
            t = AES.new(bk, AES.MODE_CBC, p[-48:-32])
            f.write(t.decrypt(p[:-48]))
            f.write(p[-48:])
    return True


# ============================================================
# 数据库路径（从缓存动态获取，不再硬编码）
# ============================================================


def _ensure_wx_dir() -> str | None:
    """确保 wx_dir 可用。"""
    wx_dir = get_wx_dir()
    if not wx_dir or not os.path.isdir(wx_dir):
        # 兜底：从 wxid 构造
        wxid = get_wxid()
        if wxid:
            wx_dir = str(Path.home() / "Documents" / "WeChat Files" / wxid)
            if os.path.isdir(wx_dir):
                return wx_dir
        print("[-] 无法确定微信数据目录，请先运行 extract_key.py --save")
        return None
    return wx_dir


def get_db_paths() -> dict[str, str]:
    """获取数据库源文件和缓存路径。"""
    key = load_key()
    wx_dir = _ensure_wx_dir()
    if not key or not wx_dir:
        return {}

    wxid = get_wxid() or os.path.basename(wx_dir)

    return {
        "key": key,
        "wxid": wxid,
        "wx_dir": wx_dir,
        "msg0_src": os.path.join(wx_dir, "Msg", "Multi", "MSG0.db"),
        "contact_src": os.path.join(wx_dir, "Msg", "MicroMsg.db"),
        "msg0_dec": str(CACHE_DIR / "de_MSG0.db"),
        "contact_dec": str(CACHE_DIR / "de_MicroMsg.db"),
    }


def ensure_db() -> bool:
    """解密所有需要的数据库。"""
    paths = get_db_paths()
    if not paths:
        print("[-] 未找到密钥缓存，请先运行: python extract_key.py --save")
        return False
    ok = decrypt_db(paths["key"], paths["msg0_src"], paths["msg0_dec"])
    decrypt_db(paths["key"], paths["contact_src"], paths["contact_dec"])
    return ok


# ============================================================
# 联系人映射
# ============================================================


def get_contact_map() -> dict[str, dict[str, str]]:
    """建立 wxid → {昵称, 备注, 微信号} 映射。"""
    paths = get_db_paths()
    if not paths:
        return {}

    contact_dec = Path(paths["contact_dec"])
    if not contact_dec.exists():
        key = load_key()
        if key:
            decrypt_db(key, paths["contact_src"], contact_dec)
    if not contact_dec.exists():
        return {}

    try:
        conn = sqlite3.connect(str(contact_dec))
        conn.text_factory = lambda x: x.decode("utf-8", errors="replace")
        c = conn.cursor()
        c.execute("SELECT UserName, NickName, Remark, Alias FROM Contact")
        result = {}
        for row in c.fetchall():
            result[row[0]] = {
                "nickname": row[1] or "",
                "remark": row[2] or "",
                "alias": row[3] or "",
            }
        conn.close()
        return result
    except Exception:
        return {}


def contact_display_name(wxid: str, cmap: dict | None = None) -> str:
    """获取联系人显示名称（备注→昵称→wxid）。"""
    if cmap is None:
        cmap = get_contact_map()
    info = cmap.get(wxid, {})
    return info.get("remark") or info.get("nickname") or wxid
