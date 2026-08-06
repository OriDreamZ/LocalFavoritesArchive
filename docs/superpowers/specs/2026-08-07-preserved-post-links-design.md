# Preserved Post Links Design

## Goal

后续新同步的推文应保留正文中的普通网页链接，并在本地收藏页面中以接近 X 的显示文本呈现为可点击链接。图片和视频对应的 `t.co` 媒体占位链接不进入本地标准化正文或链接记录，因为媒体已经由本地图片或视频元素展示。

当前既有归档不回填、不重建，也不改变其正文内容。原始响应 JSON 继续完整保存，媒体链接只从面向浏览和搜索的标准化数据中移除。

## Link Sources

采集器根据实际使用的正文来源选择链接实体：

- 普通推文使用 `legacy.full_text` 和 `legacy.entities.urls`。
- 长推文优先使用 `note_tweet.note_tweet_results.result.text` 和同一结果中的 `entity_set.urls`。
- 媒体占位链接来自 `legacy.entities.media` 与 `legacy.extended_entities.media` 中的 `url` 字段。

实体缺失但正文中存在完整 `http://` 或 `https://` 地址时，该地址作为普通链接保留，显示文本与跳转地址均使用原地址。

## Normalized Text

采集时生成用于 SQLite、全文搜索和页面显示的标准化正文：

1. 删除媒体实体对应的短链接 token。
2. 将普通链接的 `t.co` token 替换为 `display_url`。
3. `display_url` 缺失时依次使用 `expanded_url` 和原始 URL。
4. 合并多余空格并保留可读的换行结构。

例如：

```text
查看文章 https://t.co/article https://t.co/photo
```

普通链接实体显示为 `example.com/article`，媒体实体对应 `https://t.co/photo`，标准化结果为：

```text
查看文章 example.com/article
```

## Data Model

新增 `PostLink` 模型：

```python
@dataclass
class PostLink:
    index: int
    display_url: str
    expanded_url: str
    short_url: str
```

`Post` 新增 `links: list[PostLink]`，默认空列表。

SQLite 新增非破坏性的 `post_links` 表：

```sql
CREATE TABLE IF NOT EXISTS post_links (
  post_id TEXT NOT NULL,
  link_index INTEGER NOT NULL,
  display_url TEXT NOT NULL,
  expanded_url TEXT NOT NULL,
  short_url TEXT NOT NULL,
  PRIMARY KEY(post_id, link_index),
  FOREIGN KEY(post_id) REFERENCES posts(post_id) ON DELETE CASCADE
);
```

写入推文时，以当前解析结果替换该推文的链接行。旧数据库启动时只创建新表，不修改或回填已有 `posts` 行。

## API And Rendering

`ArchiveStore.get_post()` 返回按 `link_index` 排序的 `links` 数组。现有帖子详情请求已经在媒体与标签渲染时执行，因此不增加新的前端请求。

前端在收到详情后重新渲染 `.text`：

- 按链接顺序在标准化正文中定位 `display_url`。
- 链接前后的普通文本继续 HTML 转义。
- 链接使用 `expanded_url` 作为 `href`，显示 `display_url`。
- 链接在新标签页打开，并设置 `rel="noreferrer"`。
- 无法在正文中定位的链接记录不单独追加，避免出现 X 页面上不存在的额外链接列表。

媒体链接不进入 `post_links`，本地图片与视频仍使用当前 `/media/...` 地址展示和播放。

## Failure Handling

- 缺失或不完整的普通链接实体不会导致整条推文解析失败。
- `expanded_url` 缺失时使用原始 URL 作为跳转地址。
- 非 `http://` 或 `https://` 的跳转地址不生成可点击锚点，只保留转义后的显示文本。
- 媒体下载失败不恢复正文中的媒体短链接；原始响应 JSON 和同步失败记录仍可用于诊断。

## Testing

- 采集测试覆盖普通链接保留、显示 URL 替换、媒体链接删除、长推文 `entity_set.urls` 和无实体完整 URL 回退。
- 存储测试覆盖 `post_links` 写入、幂等更新和详情返回顺序。
- Web 契约测试覆盖安全链接渲染函数及详情加载后的正文更新。
- 浏览器验证普通链接可点击、媒体短链接不可见、图片或视频仍正常显示。

## Out Of Scope

- 不回填或修改当前既有归档。
- 不改变 Chrome 扩展、媒体下载器、原始 JSON 保存策略或 X 原始页面链接。
- 不实现引用推文卡片、链接预览卡片或网页离线镜像。
