# WeChatMsg

微信聊天记录命令行工具。提取密钥、管理通讯录、查询和导出聊天记录。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 提取密钥（微信需已登录）
python extract_key.py --save

# 3. 查看通讯录统计
python contacts.py --stats

# 4. 搜索聊天记录
python messages.py --search "关键词"

# 5. 导出全部聊天记录
python export.py
```

## 工具

### `extract_key.py` — 密钥提取

从正在运行的微信进程内存中提取数据库加密密钥。
支持 v3（`WeChat.exe`）和 v4（`Weixin.exe`）。

```bash
python extract_key.py --save     # 提取并缓存密钥
python extract_key.py --load     # 从缓存读取密钥
python extract_key.py --v3       # 强制使用 v3 方式
python extract_key.py --v4       # 强制使用 v4 方式
```

### `contacts.py` — 通讯录管理

解密并查询微信通讯录。

```bash
python contacts.py --stats               # 统计（好友/群聊/公众号数量）
python contacts.py --search 张三          # 搜索联系人
python contacts.py --groups              # 列出所有群聊
python contacts.py --list                # 列出所有联系人
python contacts.py --export [文件名]     # 导出联系人到 CSV
python contacts.py --refresh             # 重新解密数据库
```

### `messages.py` — 聊天记录查询

快速查询聊天记录，支持按联系人、关键词、日期范围搜索。

```bash
python messages.py                           # 最近 24 小时消息
python messages.py wxid_xxx                  # 查某个人的聊天
python messages.py --search "关键词"         # 搜索消息内容
python messages.py --search "关键词" -n 10   # 限制显示条数
python messages.py --date 2026-07-14         # 查某天的消息
python messages.py --days 7                  # 最近 7 天
python messages.py --list                    # 列出最近有消息的联系人
python messages.py --sql "SELECT count(*) FROM MSG"  # 执行 SQL
python messages.py --refresh                 # 重新解密数据库
```

### `export.py` — 聊天记录导出

将聊天记录导出为 CSV、TXT、JSON 或 SQLite 数据库。支持按联系人、时间范围筛选。

```bash
python export.py                                 # 导出全部（CSV+TXT）
python export.py --csv                           # 仅导出 CSV
python export.py --txt                           # 仅导出 TXT
python export.py --json                          # 仅导出 JSON
python export.py --db                            # 导出到 SQLite 数据库
python export.py --contact wxid_xxx              # 只导出某个联系人
python export.py --days 7                        # 最近 7 天
python export.py --date 2026-07-14               # 指定日期
python export.py --output ./my_data              # 指定输出目录
python export.py --id-list                       # 导出微信号列表
```

## 目录结构

```
WeChatMsg/
├── extract_key.py      密钥提取
├── contacts.py         通讯录管理
├── messages.py         聊天记录查询
├── export.py           聊天记录导出
├── wx_common.py        共享模块
├── wxManager/          核心库（数据库读取、解析、解密）
├── cache/              解密后的数据库缓存（自动生成）
├── wx_cache.json       密钥缓存
├── contacts_to_send.txt  按键精灵发送列表
├── requirements.txt    Python 依赖
└── readme.md           本文件
```

## 使用前提

- Windows 10/11
- Python 3.8+
- 微信已登录（v3 `WeChat.exe` 或 v4 `Weixin.exe`）
- 管理员权限（读取微信进程内存需要）

## 流程说明

```
微信源数据库（加密）
    ↓ decrypt_db() 解密
cache/de_MSG0.db        ←── messages.py / export.py 读取消息
cache/de_MicroMsg.db    ←── contacts.py / export.py 读取联系人
```

首次运行自动解密并缓存，之后直接读取缓存。如需重新解密，使用 `--refresh` 参数。

## 注意事项

- 首次使用先运行 `extract_key.py --save` 提取并缓存密钥
- 微信 ≥ 4.0.3.36 版本密钥不再常驻内存，建议用 4.0.3.19 获取密钥后升级
- 本工具仅用于个人数据备份


