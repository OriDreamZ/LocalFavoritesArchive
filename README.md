# Local Favorites Archive

Local Favorites Archive 是一个本地优先的 X Likes 归档工具。它通过用户已经登录的 Google Chrome 读取 Likes 页面刷新后返回的网络数据，将推文正文、作者、发布时间、原始链接、图片和视频保存到本机，并提供本地筛选、排序、标签与媒体浏览功能。

项目不使用 X 官方收费 API，不上传归档内容到第三方服务，也不保存点赞、转发或评论等互动统计。

## 功能

- 保存推文 ID、正文、作者显示名、@账号、作者 ID、发布时间和原文链接。
- 下载图片与视频；视频选择网络响应中的最高码率 MP4 地址。
- 以推文 ID 去重，已下载媒体不会重复下载。
- 按关键词、作者、日期、图片、视频、纯文本、单个或多个标签筛选。
- 支持发布时间、归档时间和作者名称的正序或逆序排序，以及分页与每页数量设置。
- 支持本地标签管理、单条或批量删除、图片放大缩放旋转、视频本地播放。
- 同步中心显示采集进度、媒体下载状态和逐条失败信息，并支持重试。
- 可选局域网访问；默认只监听本机。

## 运行环境

- Windows 10 或 Windows 11
- Python 3.11 或更高版本
- Google Chrome
- 可访问 X 的网络
- Node.js：仅开发时用于 JavaScript 语法检查

## 安装

在 PowerShell 中进入项目目录（填写自己本机的项目存放地址，以下为示例）：

```powershell
cd D:\MyDocument\LocalFavoritesArchive
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

## 启动

首次运行会自动创建空归档目录。启动本机服务：

```powershell
.\.venv\Scripts\local-favorites.exe serve
```

打开 http://127.0.0.1:8765 。默认归档目录为项目内的 `archive/`。

指定归档目录或端口：

```powershell
.\.venv\Scripts\local-favorites.exe serve --archive D:\XArchive --port 8766
```

扩展默认连接 `http://127.0.0.1:8765`；修改端口后，需要同步修改扩展中的本地服务地址。

## 加载 Chrome 扩展

1. 在 Chrome 打开 `chrome://extensions`。
2. 开启“开发者模式”。
3. 点击“加载已解压的扩展程序”。
4. 选择项目中的 `extension` 目录。
5. 将 Local Favorites Archive 固定到工具栏。

修改扩展源文件后，必须在扩展管理页点击“重新加载”。

## 同步 Likes

1. 确认本地服务正在运行，并在 Chrome 登录需要归档的 X 账号。
2. 打开该账号的 Likes 页面。
3. 打开扩展，设置“翻页间隔”。间隔范围为 0.5 到 5 秒，默认 1.8 秒，并会保存在 Chrome 本地存储。
4. 点击“刷新并开始同步”。扩展会刷新 Likes 页面、监听刷新后产生的 GraphQL 响应，并自动平滑向下滚动。
5. 保持标签页打开，直到自动完成，或在扩展中手动停止。

扩展不读取已渲染推文 DOM，也不提供不刷新续采模式。这样可以避免页面中的视频缩略图或 `blob:` 地址被错误保存为图片或视频。

## 媒体校验与失败处理

媒体下载会校验推文媒体类型和 HTTP 响应 MIME 类型：视频必须返回 `video/*`，图片必须返回 `image/*`。缩略图地址、类型不一致和下载失败不会写入错误文件，而会进入同步中心失败列表。

失败列表会显示推文 ID、作者、原文链接、媒体序号和原因。可在网页中单条或全部重试；也可运行：

```powershell
local-favorites retry-media
```

未激活虚拟环境时，可改用 `.\.venv\Scripts\local-favorites.exe retry-media`。

命令行重试会处理所有未下载媒体，包括 `failed` 与 `queued` 状态。

## 本地浏览与管理

网页包含总览、我的收藏、同步中心和标签管理四个页面。我的收藏支持全文搜索、筛选、排序、分页和多标签交集或并集。图片可在查看器中缩放、旋转和复位；视频使用浏览器原生控件播放。删除推文会同步删除其媒体、原始响应和标签关联，操作不可撤销。

详细规范见：

- [功能说明](docs/FEATURES.md)
- [系统架构](docs/ARCHITECTURE.md)
- [数据存储](docs/DATA-STORAGE.md)
- [界面规范](docs/UI-DESIGN.md)
- [Chrome 扩展规范](docs/CHROME-EXTENSION.md)
- [安全、隐私与限制](docs/SECURITY-AND-LIMITATIONS.md)

## 局域网访问

默认仅本机访问。如需让同一局域网的设备访问并管理归档：

```powershell
.\.venv\Scripts\local-favorites.exe serve --lan
```

局域网模式无身份验证，访问设备拥有完整管理权限。只应在可信网络使用，禁止将服务暴露到公网。

## 备份与迁移

停止服务后，完整复制 `archive/` 目录。该目录包含 SQLite 数据库、原始响应和媒体文件；只复制数据库会丢失媒体内容。恢复时将完整目录放回原位置，或使用 `--archive` 指向该目录。

## 开发与测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check extension\background.js
node --check extension\popup.js
node --check src\local_favorites_archive\static\app.js
```

开发、数据和界面规范均在 `docs/` 中维护。新增功能必须同步更新相关中文文档并增加相应测试。

## 限制

- X 页面、网络接口或访问权限变化可能导致采集或下载失败。
- 只能归档当前登录账号实际可访问的 Likes 内容。
- 视频清晰度受 X 网络响应中提供的视频变体限制。
- 本项目为个人本地归档工具；使用者应自行遵守 X 的服务条款、当地法律和内容版权要求。

## 许可证

本项目采用 [GNU GPL v3.0 或更高版本](LICENSE) 开源许可证，SPDX 标识为 `GPL-3.0-or-later`。
