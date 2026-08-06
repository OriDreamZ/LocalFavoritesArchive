const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
const numberFormatter = new Intl.NumberFormat('zh-CN');

const WORKSPACES = {
  overview: {title: '收藏总览', heading: 'overview-title'},
  favorites: {title: '我的收藏', heading: 'favorites-title'},
  sync: {title: '同步中心', heading: 'sync-title'},
  tags: {title: '标签管理', heading: 'tags-title'},
};

let currentPage = 1;
let totalPages = 1;
let allTags = [];
let pollTimer = null;
let viewerItems = [];
let viewerIndex = 0;
let viewerScale = 1;
let viewerFitScale = 1;
let viewerRotation = 0;
let viewerX = 0;
let viewerY = 0;
let viewerDragging = false;
let viewerDragStartX = 0;
let viewerDragStartY = 0;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `请求失败 (${response.status})`);
  return body;
}

function formatNumber(value) {
  return numberFormatter.format(Number(value) || 0);
}

function formatBytes(value) {
  let size = Number(value) || 0;
  if (size < 1024) return `${formatNumber(size)} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let unit = -1;
  do {
    size /= 1024;
    unit += 1;
  } while (size >= 1024 && unit < units.length - 1);
  const digits = size >= 100 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(digits)} ${units[unit]}`;
}

function normalizeRoute(hash = window.location.hash) {
  const route = String(hash).replace(/^#/, '');
  return Object.hasOwn(WORKSPACES, route) ? route : 'overview';
}

function activateWorkspace({focus = false} = {}) {
  const route = normalizeRoute();
  if (window.location.hash !== `#${route}`) history.replaceState(null, '', `#${route}`);
  document.querySelectorAll('[data-workspace]').forEach(section => {
    section.hidden = section.dataset.workspace !== route;
  });
  document.querySelectorAll('[data-route]').forEach(link => {
    const active = link.dataset.route === route;
    link.classList.toggle('is-active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  document.title = `${WORKSPACES[route].title} · 本地收藏归档`;
  if (focus) $(WORKSPACES[route].heading).focus({preventScroll: true});
}

function filterParams() {
  const params = new URLSearchParams({
    q: $('q').value,
    author: $('author').value,
    media_type: $('media').value,
    date_from: $('from').value,
    date_to: $('to').value,
  });
  if ($('tag-filter').value) params.set('tag_id', $('tag-filter').value);
  return params;
}

function syncDateInputState(input) {
  input.closest('.date-control').classList.toggle('has-value', Boolean(input.value));
}

function updatePageControls(total) {
  const label = `第 ${formatNumber(currentPage)} / ${formatNumber(totalPages)} 页 · 共 ${formatNumber(total)} 条`;
  document.querySelectorAll('[data-page-info]').forEach(node => { node.textContent = label; });
  document.querySelectorAll('[data-page-action="prev"]').forEach(node => { node.disabled = currentPage <= 1; });
  document.querySelectorAll('[data-page-action="next"]').forEach(node => { node.disabled = currentPage >= totalPages; });
  document.querySelectorAll('[data-page-number]').forEach(node => {
    node.max = totalPages;
    node.value = currentPage;
  });
}

function safeColor(color) {
  return /^#[0-9a-f]{6}$/i.test(color) ? color : '#64748b';
}

function safeHttpUrl(value) {
  try {
    const url = new URL(String(value));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function renderPostText(node, text, links) {
  const source = String(text ?? '');
  const parts = [];
  let cursor = 0;
  for (const link of links || []) {
    const label = String(link.display_url ?? '');
    if (!label) continue;
    const index = source.indexOf(label, cursor);
    if (index < 0) continue;
    parts.push(esc(source.slice(cursor, index)));
    const destination = safeHttpUrl(link.expanded_url);
    parts.push(destination
      ? `<a class="post-link" href="${esc(destination)}" target="_blank" rel="noreferrer">${esc(label)}</a>`
      : esc(label));
    cursor = index + label.length;
  }
  parts.push(esc(source.slice(cursor)));
  node.innerHTML = parts.join('');
}

function syncStateLabel(state) {
  return ({
    idle: '等待同步',
    starting: '正在连接',
    collecting: '正在采集',
    downloading: '正在下载媒体',
    finished: '同步完成',
    error: '同步失败',
  })[state] || '状态未知';
}

function renderOverviewStats(stats) {
  $('overview-posts-total').textContent = formatNumber(stats.posts_total);
  $('overview-authors-total').textContent = formatNumber(stats.authors_total);
  $('overview-media-completion').textContent = `${stats.media_completion_percent || 0}%`;
  $('overview-media-detail').textContent = `${formatNumber(stats.media_downloaded)} / ${formatNumber(stats.media_total)} 个媒体文件`;
  $('overview-tagged-posts').textContent = formatNumber(stats.tagged_posts);
  $('overview-tag-coverage').textContent = `覆盖 ${stats.tag_coverage_percent || 0}%`;
  $('overview-archive-days').textContent = `${formatNumber(stats.archive_days)} 天`;
  $('overview-storage-bytes').textContent = formatBytes(stats.storage_bytes);
  $('nav-posts-count').textContent = formatNumber(stats.posts_total);
  $('nav-failures-count').textContent = formatNumber(stats.media_failed);

  const distribution = [
    ['图片', stats.image_posts],
    ['视频', stats.video_posts],
    ['纯文本', stats.text_posts],
  ];
  const denominator = Math.max(Number(stats.posts_total) || 0, 1);
  $('overview-distribution').innerHTML = distribution.map(([label, count]) => {
    const percent = Math.min(100, Number(count) / denominator * 100);
    return `<div class="distribution-row"><span>${label}</span><div class="distribution-track"><span class="distribution-fill" style="width:${percent}%"></span></div><strong class="numeric">${formatNumber(count)}</strong></div>`;
  }).join('');

  const additions = stats.monthly_additions || [];
  const maxCount = Math.max(1, ...additions.map(item => Number(item.count) || 0));
  $('overview-monthly-additions').innerHTML = additions.map(item => {
    const height = Math.max(2, (Number(item.count) || 0) / maxCount * 100);
    const label = item.month.slice(5).replace(/^0/, '') + '月';
    return `<div class="month-column" title="${esc(item.month)}：${formatNumber(item.count)} 条"><div class="month-bar-wrap"><span class="month-bar" style="height:${height}%"></span></div><span class="month-label">${label}</span></div>`;
  }).join('');
}

function renderOverviewSync(state) {
  $('overview-sync-title').textContent = syncStateLabel(state.state);
  $('overview-sync-message').textContent = state.message || '尚未开始同步，可在已登录的 Chrome 中通过扩展启动。';
}

async function loadOverview() {
  try {
    const [stats, state] = await Promise.all([api('/api/stats/overview'), api('/api/sync/status')]);
    renderOverviewStats(stats);
    renderOverviewSync(state);
  } catch (error) {
    $('overview-sync-title').textContent = '总览读取失败';
    $('overview-sync-message').textContent = error.message;
  }
}

function renderPostTags(node, detail) {
  const assigned = detail.tags || [];
  const assignedIds = new Set(assigned.map(tag => tag.id));
  const remaining = allTags.filter(tag => !assignedIds.has(tag.id));
  const chips = assigned.map(tag => `<button class="tag-chip tag-remove" type="button" data-tag-id="${tag.id}" title="移除标签 ${esc(tag.name)}" style="--tag-color:${safeColor(tag.color)}"><span>${esc(tag.name)}</span><b aria-hidden="true">×</b></button>`).join('');
  const assignment = remaining.length
    ? `<div class="tag-assignment"><select class="tag-select" aria-label="选择要添加的标签"><option value="">添加标签…</option>${remaining.map(tag => `<option value="${tag.id}">${esc(tag.name)}</option>`).join('')}</select><button class="tag-add secondary" type="button">添加</button></div>`
    : allTags.length ? '' : '<button class="open-tag-manager secondary compact" type="button">新建标签</button>';
  node.innerHTML = `<div class="tag-chips">${chips}</div>${assignment}`;
}

async function load() {
  try {
    const filters = filterParams();
    const {total} = await api('/api/posts/count?' + filters);
    const pageSize = Number($('page-size').value);
    totalPages = Math.max(1, Math.ceil(total / pageSize));
    currentPage = Math.min(Math.max(1, currentPage), totalPages);
    updatePageControls(total);

    const params = new URLSearchParams(filters);
    params.set('sort', $('sort').value);
    params.set('direction', $('direction').value);
    params.set('limit', pageSize);
    params.set('offset', (currentPage - 1) * pageSize);
    const posts = await api('/api/posts?' + params);
    $('summary').textContent = `${formatNumber(total)} 条结果`;
    $('posts').innerHTML = posts.length ? posts.map(post => `
      <article class="post" data-id="${esc(post.post_id)}">
        <div class="post-head">
          <div><span class="author">${esc(post.author_name)}</span> <span class="handle">@${esc(post.author_handle)}</span></div>
          <span class="date">${post.published_at ? new Date(post.published_at).toLocaleString('zh-CN') : ''}</span>
        </div>
        <div class="text">${esc(post.text)}</div>
        <div class="post-tags"><span class="muted">正在读取标签…</span></div>
        <div class="media"></div>
        <a class="original" target="_blank" rel="noreferrer" href="${esc(post.url)}">在 X 查看原文 ↗</a>
      </article>`).join('') : '<div class="empty">没有符合条件的归档内容</div>';

    await Promise.all([...document.querySelectorAll('.post')].map(async article => {
      const detail = await api('/api/posts/' + encodeURIComponent(article.dataset.id));
      renderPostText(article.querySelector('.text'), detail.text, detail.links || []);
      const mediaNode = article.querySelector('.media');
      mediaNode.innerHTML = detail.media.filter(item => item.status === 'downloaded').map(item => {
        const filename = item.local_path.split(/[\\/]/).pop();
        const src = '/media/' + encodeURIComponent(item.post_id) + '/' + encodeURIComponent(filename);
        return item.kind === 'video'
          ? `<video controls preload="metadata" src="${src}"></video>`
          : `<img class="zoomable-media" loading="lazy" src="${src}" alt="推文图片" title="点击查看大图">`;
      }).join('');
      renderPostTags(article.querySelector('.post-tags'), detail);
    }));
  } catch (error) {
    $('posts').innerHTML = `<div class="empty">读取归档失败：${esc(error.message)}</div>`;
  }
}

function renderTagManager() {
  $('tag-list').innerHTML = allTags.length ? allTags.map(tag => `
    <div class="tag-row" data-tag-id="${tag.id}">
      <input class="tag-row-color" type="color" value="${safeColor(tag.color)}" aria-label="${esc(tag.name)} 的颜色">
      <input class="tag-row-name" maxlength="40" value="${esc(tag.name)}" aria-label="标签名称">
      <span class="tag-count numeric">${formatNumber(tag.post_count)} 条</span>
      <button class="tag-save secondary" type="button">保存</button>
      <button class="tag-delete danger" type="button">删除</button>
    </div>`).join('') : '<div class="empty-tag-list">还没有标签</div>';
}

async function loadTags() {
  const selected = $('tag-filter').value;
  allTags = await api('/api/tags');
  $('tag-filter').innerHTML = '<option value="">全部标签</option>' + allTags.map(tag => `<option value="${tag.id}">${esc(tag.name)} (${formatNumber(tag.post_count)})</option>`).join('');
  if (allTags.some(tag => String(tag.id) === selected)) $('tag-filter').value = selected;
  $('nav-tags-count').textContent = formatNumber(allTags.length);
  renderTagManager();
}

async function refreshAfterTagChange() {
  await loadTags();
  currentPage = 1;
  await Promise.all([loadOverview(), load()]);
}

async function loadSyncFailures() {
  try {
    const failures = await api('/api/sync/failures');
    $('sync-failures').innerHTML = failures.length ? failures.map(item => `
      <div class="failure-row">
        <div><strong>${esc(item.author_name || item.author_handle || '未知作者')}</strong><br><span class="muted">@${esc(item.author_handle)} · 推文 ${esc(item.post_id)}</span></div>
        <span>${item.kind === 'video' ? '视频' : '图片'}</span>
        <span class="failure-error">${esc(item.error || '未知错误')}</span>
        <a href="${esc(item.url)}" target="_blank" rel="noreferrer">查看原文 ↗</a>
      </div>`).join('') : '<div class="empty-state">当前没有媒体下载失败记录</div>';
  } catch (error) {
    $('sync-failures').innerHTML = `<div class="empty-state">失败记录读取失败：${esc(error.message)}</div>`;
  }
}

function renderSyncState(state) {
  const active = ['starting', 'collecting'].includes(state.state);
  const sync = $('sync-progress');
  if (active) sync.removeAttribute('value'); else sync.value = state.state === 'finished' ? 100 : 0;
  $('sync-progress-label').textContent = active ? `已发现 ${formatNumber(state.discovered || state.posts_total)}，新增 ${formatNumber(state.new)}` : `本地已有 ${formatNumber(state.posts_total)} 条`;
  const total = state.media_total || 0;
  const completed = (state.media_downloaded || 0) + (state.media_failed || 0);
  $('media-progress').value = total ? Math.round(completed / total * 100) : 0;
  $('media-progress-label').textContent = `${formatNumber(state.media_downloaded)} / ${formatNumber(total)}${state.media_queued ? ` · 排队 ${formatNumber(state.media_queued)}` : ''}${state.media_failed ? ` · 失败 ${formatNumber(state.media_failed)}` : ''}`;
  $('archive-path').textContent = state.archive_path || '';
  $('sync-posts-total').textContent = formatNumber(state.posts_total);
  $('sync-media-total').textContent = formatNumber(total);
  $('sync-media-downloaded').textContent = formatNumber(state.media_downloaded);
  $('sync-media-pending').textContent = `${formatNumber(state.media_queued)} / ${formatNumber(state.media_failed)}`;
  $('nav-posts-count').textContent = formatNumber(state.posts_total);
  $('nav-failures-count').textContent = formatNumber(state.media_failed);
  $('status').textContent = state.message || ({
    idle: '请在已登录的 Chrome 中打开自己的 Likes 页面，并点击扩展开始同步',
    collecting: `正在采集：发现 ${formatNumber(state.discovered)}，新增 ${formatNumber(state.new)}`,
    downloading: '正在下载图片与视频',
    finished: `同步完成：下载 ${formatNumber(state.media_downloaded)}，失败 ${formatNumber(state.media_failed)}`,
    error: `同步失败：${state.error || ''}`,
  })[state.state] || syncStateLabel(state.state);
  renderOverviewSync(state);
}

async function poll() {
  if (pollTimer) clearTimeout(pollTimer);
  try {
    const state = await api('/api/sync/status');
    renderSyncState(state);
    if (['starting', 'collecting', 'downloading'].includes(state.state)) {
      pollTimer = setTimeout(poll, 1500);
    }
    if (state.state === 'finished') {
      await Promise.all([load(), loadOverview(), loadSyncFailures()]);
    }
  } catch (error) {
    $('status').textContent = `状态读取失败：${error.message}`;
  }
}

function scrollToCollectionStart() {
  $('collection').scrollIntoView({behavior: 'smooth', block: 'start'});
}

async function changePage(nextPage) {
  currentPage = Math.min(Math.max(1, nextPage), totalPages);
  await load();
  scrollToCollectionStart();
}

async function jumpToPage(input) {
  const requested = Number.parseInt(input.value, 10);
  await changePage(Number.isFinite(requested) ? requested : currentPage);
}

function setupPagination(pagination) {
  pagination.addEventListener('click', async event => {
    const action = event.target.closest('[data-page-action]')?.dataset.pageAction;
    if (action === 'prev' && currentPage > 1) await changePage(currentPage - 1);
    else if (action === 'next' && currentPage < totalPages) await changePage(currentPage + 1);
    else if (action === 'jump') await jumpToPage(pagination.querySelector('[data-page-number]'));
  });
  pagination.querySelector('[data-page-number]').addEventListener('keydown', async event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      await jumpToPage(event.currentTarget);
    }
  });
}

function fitViewerImage() {
  const image = $('viewer-image');
  const canvas = $('viewer-canvas');
  if (!image.naturalWidth || !image.naturalHeight || !canvas.clientWidth || !canvas.clientHeight) return false;
  const quarterTurn = Math.abs(viewerRotation % 180) === 90;
  const displayWidth = quarterTurn ? image.naturalHeight : image.naturalWidth;
  const displayHeight = quarterTurn ? image.naturalWidth : image.naturalHeight;
  viewerFitScale = Math.min(canvas.clientWidth / displayWidth, canvas.clientHeight / displayHeight, 1);
  image.style.width = `${image.naturalWidth}px`;
  image.style.height = `${image.naturalHeight}px`;
  image.classList.add('is-ready');
  return true;
}

function applyViewerTransform() {
  $('viewer-image').style.transform = `translate(calc(-50% + ${viewerX}px), calc(-50% + ${viewerY}px)) scale(${viewerFitScale * viewerScale}) rotate(${viewerRotation}deg)`;
  $('viewer-caption').textContent = viewerItems.length ? `${viewerIndex + 1} / ${viewerItems.length} · ${Math.round(viewerScale * 100)}% · ${viewerRotation}°` : '';
}

function resetViewerTransform() {
  viewerScale = 1;
  viewerRotation = 0;
  viewerX = 0;
  viewerY = 0;
  fitViewerImage();
  applyViewerTransform();
}

function showViewerImage(index) {
  if (!viewerItems.length) return;
  viewerIndex = (index + viewerItems.length) % viewerItems.length;
  const item = viewerItems[viewerIndex];
  const image = $('viewer-image');
  viewerScale = 1;
  viewerFitScale = 1;
  viewerRotation = 0;
  viewerX = 0;
  viewerY = 0;
  image.classList.remove('is-ready');
  image.onload = () => { fitViewerImage(); applyViewerTransform(); };
  image.src = item.src;
  image.alt = item.alt || '推文图片';
  $('viewer-prev').disabled = viewerItems.length < 2;
  $('viewer-next').disabled = viewerItems.length < 2;
  if (image.complete && image.naturalWidth) {
    fitViewerImage();
    applyViewerTransform();
  }
}

function openImageViewer(sourceImage) {
  const images = [...document.querySelectorAll('.media img')];
  viewerItems = images.map(image => ({src: image.currentSrc || image.src, alt: image.alt}));
  const selectedIndex = images.indexOf(sourceImage);
  showViewerImage(selectedIndex < 0 ? 0 : selectedIndex);
  if (!$('image-viewer').open) $('image-viewer').showModal();
  requestAnimationFrame(() => { fitViewerImage(); applyViewerTransform(); });
}

function zoomViewer(factor) {
  viewerScale = Math.min(8, Math.max(.25, viewerScale * factor));
  applyViewerTransform();
}

$('filters').addEventListener('submit', event => { event.preventDefault(); currentPage = 1; load(); });
for (const input of [$('from'), $('to')]) {
  syncDateInputState(input);
  input.addEventListener('input', () => syncDateInputState(input));
  input.addEventListener('change', () => syncDateInputState(input));
}
$('page-size').addEventListener('change', () => { currentPage = 1; load(); });
document.querySelectorAll('.pagination').forEach(setupPagination);
$('refresh').addEventListener('click', async () => { await Promise.all([loadTags(), load(), loadOverview(), loadSyncFailures()]); poll(); });
window.addEventListener('hashchange', () => activateWorkspace({focus: true}));
window.addEventListener('scroll', () => $('back-to-top').classList.toggle('is-visible', window.scrollY > 480), {passive: true});
$('back-to-top').addEventListener('click', () => window.scrollTo({top: 0, behavior: 'smooth'}));

$('tag-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    await api('/api/tags', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: $('tag-name').value, color: $('tag-color').value})});
    $('tag-name').value = '';
    $('tag-message').textContent = '标签已创建';
    await refreshAfterTagChange();
  } catch (error) {
    $('tag-message').textContent = error.message;
  }
});

$('tag-list').addEventListener('click', async event => {
  const row = event.target.closest('.tag-row');
  if (!row) return;
  const tagId = row.dataset.tagId;
  try {
    if (event.target.closest('.tag-save')) {
      await api(`/api/tags/${tagId}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name: row.querySelector('.tag-row-name').value, color: row.querySelector('.tag-row-color').value})});
      $('tag-message').textContent = '标签已保存';
      await refreshAfterTagChange();
    }
    if (event.target.closest('.tag-delete') && window.confirm('删除这个标签？推文内容不会被删除。')) {
      await api(`/api/tags/${tagId}`, {method: 'DELETE'});
      $('tag-message').textContent = '标签已删除';
      await refreshAfterTagChange();
    }
  } catch (error) {
    $('tag-message').textContent = error.message;
  }
});

$('posts').addEventListener('click', async event => {
  const image = event.target.closest('.zoomable-media');
  if (image) {
    openImageViewer(image);
    return;
  }
  if (event.target.closest('.open-tag-manager')) {
    window.location.hash = '#tags';
    setTimeout(() => $('tag-name').focus(), 0);
    return;
  }
  const article = event.target.closest('.post');
  if (!article) return;
  try {
    const remove = event.target.closest('.tag-remove');
    if (remove) {
      await api(`/api/posts/${article.dataset.id}/tags/${remove.dataset.tagId}`, {method: 'DELETE'});
      await refreshAfterTagChange();
      return;
    }
    const add = event.target.closest('.tag-add');
    if (add) {
      const tagId = add.closest('.tag-assignment').querySelector('.tag-select').value;
      if (!tagId) return;
      await api(`/api/posts/${article.dataset.id}/tags/${tagId}`, {method: 'POST'});
      await refreshAfterTagChange();
    }
  } catch (error) {
    $('posts').insertAdjacentHTML('afterbegin', `<div class="empty">标签操作失败：${esc(error.message)}</div>`);
  }
});

$('viewer-close').addEventListener('click', () => $('image-viewer').close());
$('viewer-prev').addEventListener('click', () => showViewerImage(viewerIndex - 1));
$('viewer-next').addEventListener('click', () => showViewerImage(viewerIndex + 1));
$('viewer-zoom-out').addEventListener('click', () => zoomViewer(1 / 1.25));
$('viewer-zoom-in').addEventListener('click', () => zoomViewer(1.25));
$('viewer-rotate-left').addEventListener('click', () => { viewerRotation -= 90; fitViewerImage(); applyViewerTransform(); });
$('viewer-rotate-right').addEventListener('click', () => { viewerRotation += 90; fitViewerImage(); applyViewerTransform(); });
$('viewer-reset').addEventListener('click', resetViewerTransform);
window.addEventListener('resize', () => { if ($('image-viewer').open) { fitViewerImage(); applyViewerTransform(); } });
$('image-viewer').addEventListener('cancel', () => { viewerDragging = false; });
$('viewer-canvas').addEventListener('wheel', event => { event.preventDefault(); zoomViewer(event.deltaY < 0 ? 1.15 : 1 / 1.15); }, {passive: false});
$('viewer-canvas').addEventListener('dblclick', () => { viewerScale = viewerScale === 1 ? 2 : 1; viewerX = 0; viewerY = 0; applyViewerTransform(); });
$('viewer-canvas').addEventListener('pointerdown', event => {
  if (event.button !== 0) return;
  viewerDragging = true;
  viewerDragStartX = event.clientX - viewerX;
  viewerDragStartY = event.clientY - viewerY;
  $('viewer-canvas').setPointerCapture(event.pointerId);
  $('viewer-canvas').classList.add('is-dragging');
});
$('viewer-canvas').addEventListener('pointermove', event => {
  if (!viewerDragging) return;
  viewerX = event.clientX - viewerDragStartX;
  viewerY = event.clientY - viewerDragStartY;
  applyViewerTransform();
});
function stopViewerDrag() {
  viewerDragging = false;
  $('viewer-canvas').classList.remove('is-dragging');
}
$('viewer-canvas').addEventListener('pointerup', stopViewerDrag);
$('viewer-canvas').addEventListener('pointercancel', stopViewerDrag);
document.addEventListener('keydown', event => {
  if (!$('image-viewer').open) return;
  if (event.key === 'ArrowLeft') showViewerImage(viewerIndex - 1);
  if (event.key === 'ArrowRight') showViewerImage(viewerIndex + 1);
  if (event.key === '+' || event.key === '=') zoomViewer(1.25);
  if (event.key === '-') zoomViewer(1 / 1.25);
  if (event.key.toLowerCase() === 'r') resetViewerTransform();
});

(async function init() {
  if (!window.location.hash || normalizeRoute() !== window.location.hash.slice(1)) {
    history.replaceState(null, '', '#overview');
  }
  activateWorkspace();
  try {
    await loadTags();
    await Promise.all([load(), loadOverview(), loadSyncFailures()]);
  } catch (error) {
    $('status').textContent = `初始化失败：${error.message}`;
  }
  poll();
})();
