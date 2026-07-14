# WeChatMsg

微信聊天记录解密与导出工具（CLI 版本）。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 提取密钥（微信需已在登录状态）
python extract_key.py --save

# 3. 导出全部聊天记录
python export.py

# 4. 查询聊天记录
python messages.py --search "关键词"

# 5. 查看通讯录
python contacts.py --stats
```

## 工具一览

| 工具 | 功能 | 用法 |
|------|------|------|
| `extract_key.py` | 提取微信数据库密钥 | `python extract_key.py --save` |
| `contacts.py` | 通讯录管理 | `--stats` 统计, `--search` 搜索, `--export` 导出 |
| `messages.py` | 聊天记录查询 | `--search` 搜内容, `--days 7` 最近7天, `--sql` 原始SQL |
| `export.py` | 聊天记录导出 | `--csv` / `--txt`, `--days N`, `--date YYYY-MM-DD` |

## 目录说明

```
exporter/         导出模块（HTML/TXT/Markdown/CSV 等）
wxManager/        数据库读取、解析、解密逻辑
cache/            解密后的数据库缓存
wx_cache.json     密钥缓存
requirements.txt  Python 依赖
```

## 使用前提

- Windows 10/11
- Python 3.8+
- 微信已登录状态（支持 v3 WeChat.exe / v4 Weixin.exe）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 注意事项

- 首次使用先运行 `extract_key.py --save` 提取并缓存密钥
- 微信版本过新（≥4.0.3.36）可能无法直接从内存提取密钥，建议使用 4.0.3.19
- 本工具仅用于个人数据备份

### 上游项目

[https://github.com/LC044/WeChatMsg](https://github.com/LC044/WeChatMsg) (MemoTrace)
下载地址：[https://memotrace.cn/](https://memotrace.cn/)

下载打包好的exe可执行文件，双击即可运行

**⚠️注意：若出现闪退情况请右击选择用管理员身份运行exe程序，该程序不存在任何病毒，若杀毒软件提示有风险选择略过即可，key为none可重启电脑**

## 源码运行

[使用示例](./example/README.md)
[详见开发者手册](./doc/开发者手册.md)

[AI聊天](./MemoAI/readme.md)

## PC端使用过程中部分问题解决（可参考）

#### 🤔如果您在pc端使用的时候出现问题，可以先参考以下方面，如果仍未解决，可以在群里交流~

* 不支持Win7
* 不支持Mac(未来或许会实现)
* 遇到问题四大法宝
  * 首先要删除app/Database/Msg文件夹
  * 重启微信
  * 重启exe程序
  * 重启电脑
  * 换电脑
如果您在运行可执行程序的时候出现闪退的现象，请右击软件使用管理员权限运行。

[查看详细教程](https://memotrace.cn/doc/)

# 🏆致谢

<details>

* PC微信工具:[https://github.com/xaoyaoo/PyWxDump](https://github.com/xaoyaoo/PyWxDump)
* PyQt组件库:[https://github.com/PyQt5/CustomWidgets](https://github.com/PyQt5/CustomWidgets)
* 得力小助手:[ChatGPT](https://chat.openai.com/)

</details>

---
> \[!IMPORTANT]
> 
> 声明：该项目有且仅有一个目的：“留痕”——我的数据我做主，前提是“我的数据”其次才是“我做主”，禁止任何人以任何形式将其用于任何非法用途，对于使用该程序所造成的任何后果，所有创作者不承担任何责任🙄<br>
> 该软件不能找回删除的聊天记录，任何企图篡改微信聊天数据的想法都是无稽之谈。<br>
> 本项目所有功能均建立在”前言“的基础之上，基于该项目的所有开发者均不能接受任何有悖于”前言“的功能需求，违者后果自负。<br>
> 如果该项目侵犯了您或您产品的任何权益，请联系我删除<br>
> 软件贩子勿扰，违规违法勿扰，二次开发请务必遵守开源协议

[![Star History Chart](https://api.star-history.com/svg?repos=LC044/WeChatMsg&type=Date)](https://star-history.com/?utm_source=bestxtools.com#LC044/WeChatMsg&Date)

# 🤝贡献者

<a href="https://github.com/lc044/wechatmsg/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=lc044/wechatmsg" />
</a>

## 赞助者名单

感谢以下赞助者的慷慨支持：

- [STDquantum](https://github.com/STDquantum)
- [xuanli](https://github.com/xuanli)
- [无名路人](https://github.com/wumingluren)
- [时鹏亮](https://shipengliang.com)

# 🎄温馨提示

如果您在使用该软件的过程中

* 发现新的bug
* 有新的功能诉求
* 操作比较繁琐
* 觉得UI不够美观
* 等其他给您造成困扰的地方

请提起[issue](https://github.com/LC044/WeChatMsg/issues)，我将尽快为您解决问题

如果您是一名开发者，有新的想法或建议，欢迎[fork](https://github.com/LC044/WeChatMsg/forks)
该项目并发起[PR](https://github.com/LC044/WeChatMsg/pulls)，我将把您的名字写入贡献者名单中

# 联系方式

如果您遇到了问题，可以添加QQ群寻求帮助，由于精力有限，不能回答所有问题，所以还请您仔细阅读文档之后再考虑是否入群

## 加群方式

1. 关注官方公众号，回复：联系方式
2. QQ扫码入群

后续更新将会在公众号同步发布
<div>
  <img src="https://blog.lc044.love/static/img/b8df8c594a4cabaa0a62025767a3cfd9.weixin.webp">
</div>

## AI交流

欢迎对“前言”中AI感兴趣的加入QQ群（不负责任何答疑），让我们一起探讨新技术，钻研新方案，将科技的力量融入生活，打造出一个真正具有情感的个人AI

<div>
  <img src="doc/images/ai_qq.jpg" height="200">
</div>

# License

WeChatMsg is licensed under [MIT](./LICENSE).

Copyright © 2022-2024 by SiYuan.
