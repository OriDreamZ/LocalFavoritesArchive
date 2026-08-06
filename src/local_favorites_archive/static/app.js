const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));

let currentPage = 1;
let totalPages = 1;
let allTags = [];
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
  $('page-info').textContent = `第 ${currentPage} / ${totalPages} 页 · 共 ${total} 条`;
  $('prev-page').disabled = currentPage <= 1;
  $('next-page').disabled = currentPage >= totalPages;
  $('page-number').max = totalPages;
  $('page-number').value = currentPage;
}

function safeColor(color) {
  return /^#[0-9a-f]{6}$/i.test(color) ? color : '#64748b';
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
    $('summary').textContent = `${total} 条结果`;
    $('posts').innerHTML = posts.length ? posts.map(post => `
      <article class="post" data-id="${esc(post.post_id)}">
        <div class="post-head">
          <div><span class="author">${esc(post.author_name)}</span> <span class="handle">@${esc(post.author_handle)}</span></div>
          <span class="date">${post.published_at ? new Date(post.published_at).toLocaleString() : ''}</span>
        </div>
        <div class="text">${esc(post.text)}</div>
        <div class="post-tags"><span class="muted">正在读取标签…</span></div>
        <div class="media"></div>
        <a class="original" target="_blank" rel="noreferrer" href="${esc(post.url)}">在 X 查看原文 ↗</a>
      </article>`).join('') : '<div class="empty">没有符合条件的归档内容</div>';

    await Promise.all([...document.querySelectorAll('.post')].map(async article => {
      const detail = await api('/api/posts/' + encodeURIComponent(article.dataset.id));
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
    $('status').textContent = `读取归档失败：${error.message}`;
  }
}

function renderTagManager() {
  $('tag-list').innerHTML = allTags.length ? allTags.map(tag => `
    <div class="tag-row" data-tag-id="${tag.id}">
      <input class="tag-row-color" type="color" value="${safeColor(tag.color)}" aria-label="${esc(tag.name)} 的颜色">
      <input class="tag-row-name" maxlength="40" value="${esc(tag.name)}" aria-label="标签名称">
      <span class="tag-count">${tag.post_count} 条</span>
      <button class="tag-save secondary" type="button">保存</button>
      <button class="tag-delete danger" type="button">删除</button>
    </div>`).join('') : '<div class="empty-tag-list">还没有标签</div>';
}

async function loadTags() {
  const selected = $('tag-filter').value;
  allTags = await api('/api/tags');
  $('tag-filter').innerHTML = '<option value="">全部标签</option>' + allTags.map(tag => `<option value="${tag.id}">${esc(tag.name)} (${tag.post_count})</option>`).join('');
  if (allTags.some(tag => String(tag.id) === selected)) $('tag-filter').value = selected;
  renderTagManager();
}

function openTagManager() {
  $('tag-message').textContent = '';
  if (!$('tag-dialog').open) $('tag-dialog').showModal();
}

async function refreshAfterTagChange() {
  await loadTags();
  currentPage = 1;
  await load();
}

function jumpToPage() {
  const requested = Number.parseInt($('page-number').value, 10);
  currentPage = Number.isFinite(requested) ? Math.min(Math.max(1, requested), totalPages) : currentPage;
  updatePageControls(Number(($('page-info').textContent.match(/共 (\d+) 条/) || [0, 0])[1]));
  load();
  window.scrollTo({top: 0, behavior: 'smooth'});
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

async function poll() {
  try {
    const state = await api('/api/sync/status');
    $('hero-posts-total').textContent = state.posts_total || 0;
    $('hero-authors-total').textContent = state.authors_total || 0;
    $('hero-sync-state').textContent = syncStateLabel(state.state);
    const active = ['starting', 'collecting'].includes(state.state);
    const sync = $('sync-progress');
    if (active) sync.removeAttribute('value'); else sync.value = state.state === 'finished' ? 100 : 0;
    $('sync-progress-label').textContent = active ? `已发现 ${state.discovered || state.posts_total || 0}，新增 ${state.new || 0}` : `本地已有 ${state.posts_total || 0} 条`;
    const total = state.media_total || 0;
    const completed = (state.media_downloaded || 0) + (state.media_failed || 0);
    $('media-progress').value = total ? Math.round(completed / total * 100) : 0;
    $('media-progress-label').textContent = `${state.media_downloaded || 0} / ${total}${state.media_queued ? ` · 排队 ${state.media_queued}` : ''}${state.media_failed ? ` · 失败 ${state.media_failed}` : ''}`;
    $('archive-path').textContent = state.archive_path || '';
    $('status').textContent = state.message || ({idle: '请在已登录的 Chrome 中打开自己的 Likes 页面，并点击扩展开始同步', collecting: `正在采集：发现 ${state.discovered || 0}，新增 ${state.new || 0}`, downloading: '正在下载图片与视频', finished: `同步完成：下载 ${state.media_downloaded || 0}，失败 ${state.media_failed || 0}`, error: `同步失败：${state.error || ''}`}[state.state] || state.state);
    if (['starting', 'collecting', 'downloading'].includes(state.state)) setTimeout(poll, 1500);
    if (state.state === 'finished') load();
  } catch (error) {
    $('status').textContent = `状态读取失败：${error.message}`;
  }
}

$('filters').addEventListener('submit', event => { event.preventDefault(); currentPage = 1; load(); });
for (const input of [$('from'), $('to')]) {
  syncDateInputState(input);
  input.addEventListener('input', () => syncDateInputState(input));
  input.addEventListener('change', () => syncDateInputState(input));
}
$('page-size').addEventListener('change', () => { currentPage = 1; load(); });
$('prev-page').addEventListener('click', () => { if (currentPage > 1) { currentPage--; load(); window.scrollTo({top: 0, behavior: 'smooth'}); } });
$('next-page').addEventListener('click', () => { if (currentPage < totalPages) { currentPage++; load(); window.scrollTo({top: 0, behavior: 'smooth'}); } });
$('jump-page').addEventListener('click', jumpToPage);
$('page-number').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); jumpToPage(); } });
$('refresh').addEventListener('click', async () => { await loadTags(); await load(); poll(); });
$('tag-manager-open').addEventListener('click', openTagManager);
$('tag-dialog-close').addEventListener('click', () => $('tag-dialog').close());
$('viewer-close').addEventListener('click', () => $('image-viewer').close());
$('viewer-prev').addEventListener('click', () => showViewerImage(viewerIndex - 1));
$('viewer-next').addEventListener('click', () => showViewerImage(viewerIndex + 1));
$('viewer-zoom-out').addEventListener('click', () => zoomViewer(1 / 1.25));
$('viewer-zoom-in').addEventListener('click', () => zoomViewer(1.25));
$('viewer-rotate-left').addEventListener('click', () => { viewerRotation -= 90; fitViewerImage(); applyViewerTransform(); });
$('viewer-rotate-right').addEventListener('click', () => { viewerRotation += 90; fitViewerImage(); applyViewerTransform(); });
$('viewer-reset').addEventListener('click', resetViewerTransform);
window.addEventListener('resize', () => {
  if ($('image-viewer').open) {
    fitViewerImage();
    applyViewerTransform();
  }
});

$('image-viewer').addEventListener('cancel', () => { viewerDragging = false; });
$('viewer-canvas').addEventListener('wheel', event => {
  event.preventDefault();
  zoomViewer(event.deltaY < 0 ? 1.15 : 1 / 1.15);
}, {passive: false});
$('viewer-canvas').addEventListener('dblclick', () => {
  viewerScale = viewerScale === 1 ? 2 : 1;
  viewerX = 0;
  viewerY = 0;
  applyViewerTransform();
});
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
  if (event.target.closest('.open-tag-manager')) return openTagManager();
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
    $('status').textContent = `标签操作失败：${error.message}`;
  }
});

(async function init() {
  try {
    await loadTags();
    await load();
  } catch (error) {
    $('status').textContent = `初始化失败：${error.message}`;
  }
  poll();
})();
