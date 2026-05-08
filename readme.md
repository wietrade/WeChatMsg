# WeChatMsg - 微信聊天记录导出工具

微信 PC 端聊天记录导出与分析工具，支持导出聊天记录、联系人、图片视频等数据，并提供数据统计和可视化分析。

> 原项目：[LC044/WeChatMsg](https://github.com/LC044/WeChatMsg)，本仓库为 fork 学习版本。

## 功能

- 微信数据库解密（从进程内存获取密钥）
- 聊天记录导出（文本、图片、语音、视频）
- 联系人信息导出
- 数据统计与可视化（词云、聊天分析等）
- 支持 HTML / CSV / PDF 导出

## 环境要求

- **Windows 10/11**（必须，依赖 Windows API 读取微信进程内存）
- **Python 3.8+**（推荐 3.10）
- **微信 PC 版**（需登录状态）

## 快速开始（Windows）

### 1. 克隆项目

```bash
git clone https://github.com/Motionists/WeChatMsg.git
cd WeChatMsg
```

### 2. 创建虚拟环境并安装依赖

```bash
# 如果没有 uv，先安装
pip install uv

# 创建虚拟环境
uv venv

# 安装依赖
uv pip install -r requirements.txt
```

或者用传统方式：

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 运行

**确保微信已登录**，然后运行：

```bash
python main.py
```

程序会自动从微信进程内存中提取数据库密钥，解密数据库后展示聊天记录。

## 项目结构

```
WeChatMsg/
├── app/
│   ├── Ui/              # 图形界面
│   ├── DataBase/        # 数据库操作
│   ├── decrypt/         # 数据解密（密钥提取）
│   ├── web_ui/          # Web 可视化界面
│   └── util/            # 工具函数
├── main.py              # 主程序入口
├── main_pc.py           # PC 版入口
├── requirements.txt     # Python 依赖
└── readme.md
```

## 注意事项

- 本工具仅限**个人数据备份**使用，请勿用于非法用途
- 需要微信处于**已登录**状态才能获取密钥
- 支持的微信版本见 `app/decrypt/version_list.json`
- macOS / Linux 不支持（依赖 Windows API）

## License

[GPL-3.0](LICENSE)
