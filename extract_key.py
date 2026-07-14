#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信数据库密钥提取工具
======================
从正在运行的微信进程内存中提取数据库加密密钥。
支持微信 v3 (WeChat.exe) 和 v4 (Weixin.exe)。

使用方法:
    python extract_key.py              # 自动检测并提取密钥
    python extract_key.py --save       # 提取密钥并保存到文件
    python extract_key.py --v3         # 强制使用 v3 方式提取
    python extract_key.py --v4         # 强制使用 v4 方式提取
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import hmac
import json
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================
# 常量定义
# ============================================================
PROCESS_ALL_ACCESS = 0x1F0FFF
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400

# v3 微信数据库常量
V3_KEY_SIZE = 32
V3_PAGE_SIZE = 4096
V3_ITER_COUNT = 64000

# v4 微信数据库常量
V4_KEY_SIZE = 32
V4_PAGE_SIZE = 4096
V4_SALT_SIZE = 16
V4_IV_SIZE = 16
V4_HMAC_SIZE = 64
V4_AES_BLOCK_SIZE = 16
V4_ROUND_COUNT = 256000

ReadProcessMemory = ctypes.windll.kernel32.ReadProcessMemory
void_p = ctypes.c_void_p


# ============================================================
# 基础工具函数
# ============================================================


def _get_wechat_processes() -> list[dict[str, Any]]:
    """查找正在运行的微信进程。"""
    import psutil

    processes = []
    for proc in psutil.process_iter(["name", "pid", "exe"]):
        name = proc.info["name"]
        if name in ("WeChat.exe", "Weixin.exe"):
            version = _get_process_version(proc)
            processes.append(
                {
                    "pid": proc.info["pid"],
                    "name": name,
                    "exe": proc.info["exe"],
                    "version": version,
                    "proc": proc,
                }
            )
    return processes


def _get_process_version(proc) -> str:
    """获取进程版本号。"""
    try:
        import win32api

        version_info = win32api.GetFileVersionInfo(proc.exe(), "\\")
        ms = version_info["FileVersionMS"]
        ls = version_info["FileVersionLS"]
        return (
            f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}."
            f"{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
        )
    except Exception:
        return "未知"


def _get_exe_bit(file_path: str) -> int:
    """检测 exe 是 32 位还是 64 位。"""
    try:
        with open(file_path, "rb") as f:
            if f.read(2) != b"MZ":
                return 64
            f.seek(60)
            pe_offset = int.from_bytes(f.read(4), byteorder="little")
            f.seek(pe_offset + 4)
            machine = int.from_bytes(f.read(2), byteorder="little")
            return 32 if machine == 0x14C else 64
    except Exception:
        return 64


def _open_process(pid: int, access: int = PROCESS_ALL_ACCESS) -> int:
    """打开指定 PID 的进程句柄。"""
    return ctypes.windll.kernel32.OpenProcess(access, False, pid)


def _close_handle(handle: int) -> None:
    """关闭进程句柄。"""
    ctypes.windll.kernel32.CloseHandle(handle)


def _read_process_memory(handle: int, address: int, size: int) -> bytes:
    """从指定进程内存地址读取数据。"""
    buf = ctypes.create_string_buffer(size)
    ret = ReadProcessMemory(handle, void_p(address), buf, size, 0)
    if ret == 0:
        return b""
    return bytes(buf)


# ============================================================
# v3 密钥提取（WeChat.exe）
# ============================================================


def _v3_find_wxid(handle: int) -> str:
    """从进程内存中扫描 wxid。"""
    import pymem

    next_region = 0
    wxids = []
    user_space_limit = 0x7FFFFFFF0000 if sys.maxsize > 2**32 else 0x7FFF0000
    pattern = rb"\\Msg\\FTSContact"

    while next_region < user_space_limit:
        try:
            next_region, page_found = pymem.pattern.scan_pattern_page(
                handle, next_region, pattern, return_multiple=True
            )
        except Exception:
            break
        if page_found:
            for addr in page_found:
                buf = ctypes.create_string_buffer(80)
                if ReadProcessMemory(handle, void_p(addr - 30), buf, 80, 0) == 0:
                    continue
                raw = bytes(buf).split(b"\\Msg")[0].split(b"\\")[-1]
                wxids.append(raw.decode("utf-8", errors="ignore"))
        if len(wxids) > 100:
            break
    return max(wxids, key=wxids.count) if wxids else ""


def _v3_get_wx_dir(wxid: str) -> str:
    """根据 wxid 获取微信数据目录路径。"""
    if not wxid:
        return ""
    try:
        import winreg

        # 尝试从注册表获取微信文件保存路径
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Tencent\WeChat", 0, winreg.KEY_READ
            )
            w_dir = winreg.QueryValueEx(key, "FileSavePath")[0]
            winreg.CloseKey(key)
        except Exception:
            w_dir = "MyDocument:"

        if w_dir == "MyDocument:":
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion"
                    r"\Explorer\User Shell Folders",
                )
                w_dir = winreg.QueryValueEx(key, "Personal")[0]
                winreg.CloseKey(key)
                if "%" in os.path.split(w_dir)[0]:
                    env_var = os.path.split(w_dir)[0].replace("%", "")
                    w_dir = os.path.join(
                        os.environ.get(env_var, ""), *os.path.split(w_dir)[1:]
                    )
            except Exception:
                w_dir = os.path.join(os.environ.get("USERPROFILE", ""), "Documents")

        return os.path.join(w_dir, "WeChat Files", wxid)
    except Exception:
        return ""


def _v3_verify_key(key: bytes, db_path: str) -> bool:
    """用 MicroMsg.db 校验密钥是否正确。"""
    if not db_path or not os.path.isfile(db_path):
        return False
    try:
        with open(db_path, "rb") as f:
            blist = f.read(5000)
    except Exception:
        return False

    salt = blist[:16]
    byte_key = hashlib.pbkdf2_hmac("sha1", key, salt, V3_ITER_COUNT, V3_KEY_SIZE)
    first = blist[16:V3_PAGE_SIZE]

    mac_salt = bytes([b ^ 58 for b in salt])
    mac_key = hashlib.pbkdf2_hmac("sha1", byte_key, mac_salt, 2, V3_KEY_SIZE)
    hash_mac = hmac.new(mac_key, first[:-32], hashlib.sha1)
    hash_mac.update(b"\x01\x00\x00\x00")

    return hash_mac.digest() == first[-32:-12]


def _v3_extract_key(wx_dir: str, addr_len: int) -> str | None:
    """
    v3 密钥提取核心逻辑：
    1. 附加到 WeChat.exe 进程
    2. 在 WeChatWin.dll 中扫描 "iphone"/"android"/"ipad" 字符串
    3. 从匹配地址向前回溯 2000 字节，查找密钥指针
    4. 读取候选密钥，用 MicroMsg.db 校验
    """
    import pymem

    try:
        pm = pymem.Pymem("WeChat.exe")
    except pymem.exception.ProcessNotFound:
        print("[v3] 未找到 WeChat.exe 进程")
        return None

    module_name = "WeChatWin.dll"
    micro_msg_path = os.path.join(wx_dir, "MSG", "MicroMsg.db")

    if not os.path.isfile(micro_msg_path):
        print(f"[v3] 未找到数据库: {micro_msg_path}")
        return None

    # 扫描手机类型字符串
    phone_types = ["iphone\x00", "android\x00", "ipad\x00"]
    all_addrs = []
    for pt in phone_types:
        try:
            addrs = pm.pattern_scan_module(
                pt.encode(), module_name, return_multiple=True
            )
            if isinstance(addrs, list) and len(addrs) >= 2:
                all_addrs = addrs
                print(f"[v3] 找到 '{pt.strip(chr(0))}' 特征地址: {len(addrs)} 个")
                break
        except Exception:
            continue

    if not all_addrs:
        print("[v3] 未找到手机类型特征字符串")
        return None

    # 回溯扫描密钥
    for base_addr in all_addrs[::-1]:
        for offset in range(0, 2000, addr_len):
            j = base_addr - offset
            ptr_bytes = _read_process_memory(pm.process_handle, j, addr_len)
            if not ptr_bytes:
                continue
            key_addr = int.from_bytes(ptr_bytes, byteorder="little")
            key_bytes = _read_process_memory(pm.process_handle, key_addr, 32)
            if not key_bytes or len(key_bytes) != 32:
                continue
            if _v3_verify_key(key_bytes, micro_msg_path):
                return key_bytes.hex()
    return None


# ============================================================
# v4 密钥提取（Weixin.exe）
# ============================================================


def _v4_get_memory_regions(handle: int) -> list[tuple[int, int]]:
    """获取进程的所有私有内存区域。"""
    import ctypes.wintypes as wintypes

    class MEMORY_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
        ]

    MEM_COMMIT = 0x1000
    MEM_PRIVATE = 0x20000
    PAGE_READWRITE = 0x04

    regions = []
    address = 0
    while True:
        mbi = MEMORY_BASIC_INFORMATION()
        ret = ctypes.windll.kernel32.VirtualQueryEx(
            handle, void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
        )
        if ret == 0:
            break
        if (
            mbi.State == MEM_COMMIT
            and mbi.Type == MEM_PRIVATE
            and mbi.Protect == PAGE_READWRITE
        ):
            regions.append((mbi.BaseAddress, mbi.RegionSize))
        address += mbi.RegionSize
    return regions


def _v4_is_key_valid(passphrase: bytes, buf: bytes) -> bool:
    """
    用数据库文件头校验 v4 密钥。
    校验算法: PBKDF2-SHA512(256000轮) → AES HMAC 验证
    """
    from Crypto.Hash import SHA512
    from Crypto.Protocol.KDF import PBKDF2

    salt = buf[:V4_SALT_SIZE]
    mac_salt = bytes(x ^ 0x3A for x in salt)
    new_key = PBKDF2(
        passphrase,
        salt,
        dkLen=V4_KEY_SIZE,
        count=V4_ROUND_COUNT,
        hmac_hash_module=SHA512,
    )
    mac_key = PBKDF2(
        new_key, mac_salt, dkLen=V4_KEY_SIZE, count=2, hmac_hash_module=SHA512
    )

    reserve = V4_IV_SIZE + V4_HMAC_SIZE
    reserve = (
        (reserve + V4_AES_BLOCK_SIZE - 1) // V4_AES_BLOCK_SIZE
    ) * V4_AES_BLOCK_SIZE

    start = V4_SALT_SIZE
    end = V4_PAGE_SIZE
    mac = hmac.new(mac_key, buf[start : end - reserve + V4_IV_SIZE], SHA512)
    mac.update(struct.pack("<I", 1))
    hash_mac = mac.digest()

    hash_start = end - reserve + V4_IV_SIZE
    hash_end = hash_start + len(hash_mac)
    return hash_mac == buf[hash_start:hash_end]


def _v4_scan_key_addresses(pid: int, regions: list[tuple[int, int]]) -> list[bytes]:
    """
    用 YARA 规则扫描内存，找到可能指向密钥的地址。
    """
    import yara

    rule_text = r"""
    rule GetKeyAddrStub {
        strings:
            $a = /.{6}\x00{2}\x00{8}\x20\x00{7}\x2f\x00{7}/
        condition:
            all of them
    }
    """
    rules = yara.compile(source=rule_text)

    handle = _open_process(pid, PROCESS_VM_READ | PROCESS_QUERY_INFORMATION)
    if not handle:
        return []

    pre_addresses = []
    for base_addr, region_size in regions:
        memory = _read_process_memory(handle, base_addr, region_size)
        if not memory:
            continue
        try:
            matches = rules.match(data=memory)
        except Exception:
            continue
        for match in matches:
            if match.rule == "GetKeyAddrStub":
                for s in match.strings:
                    offset = s.instances[0].offset
                    addr = struct.unpack_from("<Q", memory, offset)[0]
                    pre_addresses.append(addr)
    _close_handle(handle)

    # 读取候选密钥
    keys, key_set = [], set()
    for pre_addr in pre_addresses:
        key = _v4_read_bytes(pid, pre_addr, 32)
        if key and key not in key_set:
            keys.append(key)
            key_set.add(key)
    return keys


def _v4_read_bytes(pid: int, addr: int, size: int) -> bytes:
    """从指定进程和地址读取原始字节。"""
    handle = _open_process(pid, PROCESS_VM_READ | PROCESS_QUERY_INFORMATION)
    if not handle:
        return b""
    try:
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t(0)
        success = ctypes.windll.kernel32.ReadProcessMemory(
            handle, void_p(addr), buf, size, ctypes.byref(bytes_read)
        )
        return bytes(buf) if success else b""
    finally:
        _close_handle(handle)


def _v4_find_db_file(wx_dir: str) -> str | None:
    """查找用于校验密钥的 v4 数据库文件。"""
    candidates = [
        os.path.join(wx_dir, "favorite", "favorite_fts.db"),
        os.path.join(wx_dir, "head_image", "head_image.db"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    # 兜底: 在 db_storage 下找任意 .db 文件
    db_storage = os.path.join(wx_dir, "db_storage")
    if os.path.isdir(db_storage):
        for root, _dirs, files in os.walk(db_storage):
            for f in files:
                if f.endswith(".db"):
                    return os.path.join(root, f)
    return None


def _v4_find_wx_dir(pid: int) -> str | None:
    """从 v4 微信进程内存中扫描数据目录路径。"""
    import yara

    rule_text = r"""
    rule GetDataDir {
        strings:
            $a = /[a-zA-Z]:\\(.{1,100}?\\){0,1}?xwechat_files\\[0-9a-zA-Z_-]{6,24}?\\db_storage\\/
        condition:
            $a
    }
    """
    rules = yara.compile(source=rule_text)

    handle = _open_process(pid, PROCESS_VM_READ | PROCESS_QUERY_INFORMATION)
    if not handle:
        return None

    regions = _v4_get_memory_regions(handle)
    wx_dir_counts = {}
    for base_addr, region_size in regions:
        memory = _read_process_memory(handle, base_addr, region_size)
        if not memory or b"db_storage" not in memory:
            continue
        try:
            matches = rules.match(data=memory)
        except Exception:
            continue
        for match in matches:
            for s in match.strings:
                path = s.instances[0].matched_data.decode("utf-8", errors="ignore")
                wx_dir_counts[path] = wx_dir_counts.get(path, 0) + 1

    _close_handle(handle)

    if wx_dir_counts:
        return max(wx_dir_counts, key=wx_dir_counts.get)
    return None


def _v4_extract_key(pid: int) -> dict[str, Any]:
    """
    v4 密钥提取核心逻辑：
    1. 从进程内存中扫描微信数据目录
    2. 扫描所有私有内存区域，用 YARA 匹配密钥指针
    3. 读取候选密钥，用数据库文件头校验
    """
    result = {"key": None, "wx_dir": None, "wxid": None}

    # 1. 获取微信数据目录
    wx_dir = _v4_find_wx_dir(pid)
    if not wx_dir:
        print("[v4] 未能从内存中扫描到微信数据目录")
        return result
    result["wx_dir"] = wx_dir
    print(f"[v4] 微信数据目录: {wx_dir}")

    # 2. 获取用于校验的数据库文件
    db_file = _v4_find_db_file(wx_dir)
    if not db_file:
        print("[v4] 未找到可用于校验密钥的数据库文件")
        return result
    print(f"[v4] 校验数据库: {db_file}")

    try:
        with open(db_file, "rb") as f:
            buf = f.read(V4_PAGE_SIZE)
    except Exception as e:
        print(f"[v4] 读取数据库文件失败: {e}")
        return result

    # 3. 扫描内存找候选密钥
    handle = _open_process(pid, PROCESS_VM_READ | PROCESS_QUERY_INFORMATION)
    if not handle:
        print("[v4] 无法打开进程")
        return result
    regions = _v4_get_memory_regions(handle)
    _close_handle(handle)
    print(f"[v4] 内存区域数: {len(regions)}，正在扫描密钥...")

    # 拆分区域并行扫描
    candidate_keys = _v4_scan_key_addresses(pid, regions)
    print(f"[v4] 候选密钥数: {len(candidate_keys)}")

    if not candidate_keys:
        return result

    # 4. 批量校验
    from multiprocessing import Pool, cpu_count

    with Pool(processes=max(1, cpu_count() // 2)) as pool:
        results = pool.starmap(_v4_is_key_valid, [(key, buf) for key in candidate_keys])

    for key, valid in zip(candidate_keys, results):
        if valid:
            result["key"] = key.hex()
            # 从目录路径提取 wxid
            import re

            m = re.search(r"xwechat_files[\\/]([^\\/]+)", wx_dir)
            if m:
                result["wxid"] = m.group(1)
            break

    return result


# ============================================================
# 整合入口
# ============================================================


def extract_key(
    force_v3: bool = False, force_v4: bool = False, verbose: bool = True
) -> dict[str, Any]:
    """
    自动检测并提取微信数据库密钥。

    参数:
        force_v3: 只使用 v3 方式
        force_v4: 只使用 v4 方式
        verbose: 是否输出详细信息

    返回:
        {
            "success": bool,
            "key": str | None,          # 64位十六进制密钥
            "wxid": str | None,
            "wx_dir": str | None,        # 微信数据目录
            "version": int,              # 3 或 4
            "process_name": str | None,
            "message": str
        }
    """
    result = {
        "success": False,
        "key": None,
        "wxid": None,
        "wx_dir": None,
        "version": None,
        "process_name": None,
        "message": "",
    }

    def _log(msg: str) -> None:
        if verbose:
            print(msg)

    # 查找微信进程
    processes = _get_wechat_processes()
    if not processes:
        result["message"] = "未找到正在运行的微信进程 (WeChat.exe / Weixin.exe)"
        _log(f"[!] {result['message']}")
        return result

    _log(f"[*] 发现 {len(processes)} 个微信进程:")
    for p in processes:
        _log(f"    - {p['name']} (PID={p['pid']}, 版本={p['version']})")

    # 优先尝试 v4 (Weixin.exe)
    v4_procs = [p for p in processes if p["name"] == "Weixin.exe"]
    if v4_procs and not force_v3:
        _log("\n[*] 尝试 v4 密钥提取 (Weixin.exe)...")
        for proc in v4_procs:
            _log(f"    PID: {proc['pid']}, 版本: {proc['version']}")
            r = _v4_extract_key(proc["pid"])
            if r.get("key"):
                result.update(
                    {
                        "success": True,
                        "key": r["key"],
                        "wxid": r.get("wxid"),
                        "wx_dir": r.get("wx_dir"),
                        "version": 4,
                        "process_name": "Weixin.exe",
                        "message": "v4 密钥提取成功",
                    }
                )
                _log("\n[✓] 密钥提取成功 (v4)!")
                _log(f"    密钥: {r['key']}")
                _log(f"    目录: {r.get('wx_dir')}")
                if r.get("wxid"):
                    _log(f"    wxid: {r['wxid']}")
                return result
            _log("    - 未提取到密钥")

    # 尝试 v3 (WeChat.exe)
    v3_procs = [p for p in processes if p["name"] == "WeChat.exe"]
    if v3_procs and not force_v4:
        _log("\n[*] 尝试 v3 密钥提取 (WeChat.exe)...")
        for proc in v3_procs:
            _log(f"    PID: {proc['pid']}, 版本: {proc['version']}")
            handle = _open_process(proc["pid"])
            if not handle:
                _log("    - 无法打开进程")
                continue

            wxid = _v3_find_wxid(handle)
            _close_handle(handle)

            if not wxid:
                _log("    - 未能获取 wxid")
                continue

            wx_dir = _v3_get_wx_dir(wxid)
            if not wx_dir or not os.path.isdir(wx_dir):
                _log(f"    - 微信目录不存在: {wx_dir}")
                continue

            addr_len = _get_exe_bit(proc["exe"]) // 8
            key = _v3_extract_key(wx_dir, addr_len)

            if key:
                result.update(
                    {
                        "success": True,
                        "key": key,
                        "wxid": wxid,
                        "wx_dir": wx_dir,
                        "version": 3,
                        "process_name": "WeChat.exe",
                        "message": "v3 密钥提取成功",
                    }
                )
                _log("\n[✓] 密钥提取成功 (v3)!")
                _log(f"    密钥: {key}")
                _log(f"    wxid: {wxid}")
                _log(f"    目录: {wx_dir}")
                return result
            _log("    - 未提取到密钥")

    if not result["success"]:
        result["message"] = (
            "密钥提取失败。\n"
            "可能原因:\n"
            "  1. 微信版本过新，密钥未常驻内存\n"
            "  2. 微信未登录\n"
            "  3. 缺少管理员权限"
        )
    return result


# ============================================================
# 缓存功能
# ============================================================

CACHE_FILE = Path(__file__).parent / "wx_cache.json"


def save_key_cache(data: dict[str, Any]) -> None:
    """将密钥信息保存到缓存文件。"""
    cache = {
        "key": data.get("key"),
        "wxid": data.get("wxid"),
        "wx_dir": data.get("wx_dir"),
        "version": data.get("version"),
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[*] 密钥已缓存到: {CACHE_FILE}")


def load_key_cache() -> dict[str, Any] | None:
    """从缓存文件加载密钥信息。"""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ============================================================
# 命令行入口
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="微信数据库密钥提取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python extract_key.py             自动检测并提取
  python extract_key.py --save      提取并缓存密钥
  python extract_key.py --load      从缓存读取密钥
  python extract_key.py --v3        强制使用 v3 方式
  python extract_key.py --v4        强制使用 v4 方式
        """,
    )
    parser.add_argument("--save", action="store_true", help="提取成功后缓存密钥到文件")
    parser.add_argument("--load", action="store_true", help="从缓存文件读取密钥")
    parser.add_argument(
        "--v3", action="store_true", help="只使用 v3 (WeChat.exe) 方式提取"
    )
    parser.add_argument(
        "--v4", action="store_true", help="只使用 v4 (Weixin.exe) 方式提取"
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    args = parser.parse_args()

    # 从缓存读取
    if args.load:
        cache = load_key_cache()
        if cache and cache.get("key"):
            if args.json:
                print(json.dumps(cache, ensure_ascii=False, indent=2))
            else:
                print("[*] 从缓存读取密钥:")
                print(f"    密钥: {cache['key']}")
                print(f"    wxid: {cache.get('wxid')}")
                if cache.get("wx_dir"):
                    print(f"    目录: {cache['wx_dir']}")
                print(f"    提取时间: {cache.get('extracted_at')}")
        else:
            print("[!] 缓存文件中没有有效密钥")
        return

    # 提取密钥
    start = time.time()
    result = extract_key(force_v3=args.v3, force_v4=args.v4)
    elapsed = time.time() - start

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print()
        print("=" * 50)
        if result["success"]:
            print(f"[✓] 结果: 成功 ({result['message']})")
            print(f"    耗时: {elapsed:.2f} 秒")
            print(f"    密钥: {result['key']}")
            print(f"    wxid: {result.get('wxid')}")
            print(f"    版本: v{result.get('version')}")
            print(f"    进程: {result.get('process_name')}")
            if result.get("wx_dir"):
                print(f"    目录: {result['wx_dir']}")
        else:
            print("[✗] 结果: 失败")
            print(f"    耗时: {elapsed:.2f} 秒")
            print(f"    原因: {result['message']}")
        print("=" * 50)

    # 缓存
    if args.save and result["success"]:
        save_key_cache(result)

    # 返回值方便脚本调用
    return result


if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()
    main()
