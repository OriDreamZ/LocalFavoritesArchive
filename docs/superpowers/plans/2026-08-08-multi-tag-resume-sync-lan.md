# 多标签筛选、续接同步与局域网访问实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多标签交集/并集筛选、从当前 Likes 页面位置继续同步，以及默认关闭、可显式开启的无认证局域网完整管理访问。

**Architecture:** SQLite 查询层统一生成多标签条件；Web API 接受规范化 DOM 推文并与 GraphQL 采集共用持久化流程；扩展以“当前位置继续”为默认模式并保留“从头同步”。`--lan` 显式改变监听地址，局域网模式对修改请求要求客户端标记头但不进行身份验证。

**Tech Stack:** Python、FastAPI、SQLite、Manifest V3 Chrome 扩展、原生 HTML/CSS/JavaScript、pytest。

---

### 任务 1：多标签查询与接口

**文件：** `src/local_favorites_archive/storage.py`、`src/local_favorites_archive/web.py`、`tests/test_storage.py`、`tests/test_web.py`

- [ ] 编写失败测试：两个标签分别验证 `tag_mode="all"` 只返回同时命中的推文，`tag_mode="any"` 返回任一命中的推文；验证计数与列表一致、重复 ID 归一化、旧 `tag_id` 兼容。
- [ ] 运行 `python -m pytest tests/test_storage.py tests/test_web.py -k "multi_tag or legacy_tag" -v`，确认旧签名或结果失败。
- [ ] 将 `_post_filters`、`count_posts`、`list_posts` 改为接收 `tag_ids: list[int] | None` 和 `tag_mode`。交集使用按标签生成的 `EXISTS`；并集使用参数化 `IN`，拒绝非 `all|any` 模式。
- [ ] Web 接口接受重复的 `tag_ids` 查询参数，若没有新参数则兼容单个 `tag_id`。
- [ ] 运行相关测试并提交 `feat: filter posts by multiple tags`。

### 任务 2：多标签筛选界面

**文件：** `src/local_favorites_archive/static/index.html`、`src/local_favorites_archive/static/app.js`、`src/local_favorites_archive/static/styles.css`、`tests/test_web.py`

- [ ] 编写前端契约测试，要求标签复选框容器、交集/并集分段控件、重复 `tag_ids` 参数、URL 查询参数恢复和标签删除后的选择清理存在。
- [ ] 将单选 `select#tag-filter` 替换为紧凑的多选弹出面板，标签使用颜色标记和复选框，模式使用“全部满足／任一满足”单选分段控件。
- [ ] `filterParams()` 对每个选择执行 `params.append('tag_ids', id)` 并写入 `tag_mode`；提交筛选时使用 `history.replaceState` 保存条件，初始化时从 URL 恢复。
- [ ] 标签增删只在结果成员变化时刷新列表，保留现有页码钳制和卡片原位更新规则；桌面和 390px 宽度不得重叠。
- [ ] 运行 Web 测试和 `node --check src/local_favorites_archive/static/app.js`，提交 `feat: add multi-tag filter controls`。

### 任务 3：规范化 DOM 推文接收

**文件：** `src/local_favorites_archive/collector.py`、`src/local_favorites_archive/web.py`、`tests/test_collector.py`、`tests/test_web.py`

- [ ] 编写失败测试，提交包含 ID、正文、作者、时间、链接、图片和无效 `blob:` 视频的 DOM 批次；验证有效字段保存、`blob:` 媒体忽略、重复 ID 不重复新增。
- [ ] 增加 `POST /api/ingest/dom-posts`，使用 Pydantic 限制批次大小和字段长度；新增 `post_from_dom_payload`，把 DOM 记录转换为现有 `Post`、`PostLink`、`MediaItem`。
- [ ] 抽取 Web 层公共 `ingest_posts(posts)`，GraphQL 与 DOM 接口共用已有连续计数、停止请求、下载调度和状态更新。
- [ ] 运行采集与 Web 测试，提交 `feat: ingest rendered likes posts`。

### 任务 4：扩展从当前页面继续采集

**文件：** `extension/popup.html`、`extension/popup.js`、`extension/popup.css`、`extension/background.js`、`tests/test_extension.py`

- [ ] 编写契约测试：默认消息包含 `mode: "resume"`，备用按钮包含 `mode: "restart"`；当前 Likes 的 resume 路径不得调用 reload；DOM 提取必须使用推文 article、状态链接、时间、正文、作者和媒体选择器。
- [ ] 弹窗提供主按钮“从当前位置继续”和次按钮“从头重新同步”，运行时同时禁用。
- [ ] `start(tabId, url, mode)` 在当前 Likes + resume 时先附加调试协议并启用 Network，不刷新、不改变滚动位置；restart 才刷新；非 Likes 页面仍导航到 Likes。
- [ ] 注入滚动驱动器时立即采集当前 DOM，并在每次滚动前发送 `dom-batch`。只接受带 `/status/<数字>` 与 `time` 的推文；跳过头像、表情和 `blob:` 视频。
- [ ] 后台将 DOM 批次发送至新接口；DOM 与 GraphQL 批次都服从服务端停止条件，finish 保持幂等。
- [ ] 运行扩展测试和两个扩展脚本语法检查，提交 `feat: resume likes sync from current position`。

### 任务 5：可选局域网完整管理模式

**文件：** `src/local_favorites_archive/config.py`、`src/local_favorites_archive/cli.py`、`src/local_favorites_archive/web.py`、`src/local_favorites_archive/static/app.js`、`src/local_favorites_archive/static/index.html`、`extension/background.js`、`tests/test_config.py`、`tests/test_web.py`、`tests/test_extension.py`

- [ ] 编写失败测试：默认绑定回环；`--lan` 产生 `0.0.0.0` 和 `lan_enabled=True`；状态接口返回模式与访问地址；LAN 模式修改请求缺少 `X-Local-Favorites-Client` 时为 403，带头时正常。
- [ ] CLI 增加 `--lan`，禁止与非默认 `--host` 模式混淆；默认不变。启动时打印本机和可用局域网 IPv4 URL，并打印无认证完整管理警告。
- [ ] Web 状态与同步中心显示“仅本机／局域网完整管理”及访问地址。LAN 模式下中间件只对 POST、PATCH、DELETE 校验客户端标记头；页面 `api()` 和扩展请求统一发送该头。
- [ ] 不增加 CORS，不自动修改防火墙，不改变扩展的 `127.0.0.1` 服务地址。
- [ ] 运行配置、Web 和扩展测试，提交 `feat: add opt-in lan management mode`。

### 任务 6：中文长期文档

**文件：** `README.md`、`docs/FEATURES.md`、`docs/ARCHITECTURE.md`、`docs/UI-DESIGN.md`、`docs/DEVELOPMENT.md`、`docs/DATA-STORAGE.md`、`docs/SECURITY-AND-LIMITATIONS.md`、新建 `docs/FILTERING-AND-TAGS.md`、`docs/CHROME-EXTENSION.md`、`docs/LAN-ACCESS.md`、`tests/test_project_documentation.py`

- [ ] 先增加文档契约测试，检查三份新中文文档、`tag_mode`、两种同步模式、`--lan`、无认证完整管理、Windows 防火墙和禁止公网暴露等关键说明。
- [ ] 更新 README 使用步骤和常见问题；六份长期文档分别记录功能、架构、交互、测试、存储查询与安全边界；新增三份专题文档。
- [ ] 运行文档测试和 `git diff --check`，提交 `docs: explain filtering sync and lan access`。

### 任务 7：完整与浏览器验证

- [ ] 运行完整 pytest、三个 JavaScript 语法检查与 `git diff --check`。
- [ ] 使用项目外临时归档启动回环服务，验证多标签 all/any、筛选 URL 恢复、当前位置继续不改变滚动位置、从头同步触发刷新。
- [ ] 以 `--lan` 启动隔离服务，从第二本机地址验证页面和完整管理 API；确认未启用时该地址不可访问。不得修改真实 `archive/`。
- [ ] 在桌面和 390×844 检查多标签面板、同步弹窗、LAN 风险提示，无溢出、重叠或控制台错误。
- [ ] 停止测试服务、删除已校验的临时目录并确认 Git 工作区状态。
