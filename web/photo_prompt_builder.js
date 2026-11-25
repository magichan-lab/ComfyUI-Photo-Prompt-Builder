import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

const NODE_TYPE = 'MagichanLab_Krea2PhotoPromptBuilder';
const REFERENCE_NODE_TYPE = 'MagichanLab_Krea2PhotoPromptReference';
const FIELDS = [
  ['subject', 'Subject'],
  ['appearance', 'Clothing'],
  ['hair_makeup', 'Hair & Makeup'],
  ['pose', 'Posing'],
  ['expression', 'Expression'],
  ['environment', 'Environment'],
  ['composition', 'Composition & Camera'],
  ['lighting', 'Lighting'],
  ['finishing', 'Finishing'],
];
const PATH = '/magichanlab_photo_prompt/history';
const PHOTO_ID_PATH = '/magichanlab_photo_prompt/photo_id';
const cache = { photo_ids: {}, images: {} };
let photoIdsLoaded = false;
const nodes = new Set();
const referenceNodes = new Set();
const PHOTO_ID_RE = /^[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}$/;
const SELECT_ID = '(Select Photo ID)';
const EDITED_SUFFIX = ' [Edited]';
const SEARCH_COLOR = '#b9c3d0';
const SELECTED_COLOR = '#8fd4ff';
const EDITED_COLOR = '#ffd58a';
const FIELD_WIDGET_HEIGHT = 124; // 104px of content plus the DOM widget's 10px margins.
const photoIdCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function followNodeWidth(node, target) {
  // ComfyUI can retain a widget.width from an earlier layout. Its DOM wrapper
  // uses that width before falling back to the node width.
  const syncWidth = () => { target.width = node.size[0]; };
  target.options ??= {};
  for (const name of ['onDraw', 'afterResize']) {
    const previous = target.options[name];
    target.options[name] = function (...args) {
      const result = previous?.apply(this, args);
      syncWidth();
      return result;
    };
  }
  syncWidth();
  return target;
}

function addFullWidthDOMWidget(node, ...args) {
  return followNodeWidth(node, node.addDOMWidget(...args));
}

function makePhotoIdAutocomplete(onSelect, onQuery) {
  const root = document.createElement('div');
  Object.assign(root.style, { position: 'relative', width: '100%', height: '100%', minWidth: '0' });
  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'Search Photo ID';
  input.setAttribute('aria-label', 'Search or select Photo ID');
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  Object.assign(input.style, {
    boxSizing: 'border-box', width: '100%', height: '100%', minHeight: '32px',
    padding: '5px 30px 5px 6px', background: '#17191c', color: SEARCH_COLOR,
    border: '1px solid #666', borderRadius: '6px',
  });
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.textContent = '▾';
  toggle.title = 'Show Photo IDs';
  toggle.setAttribute('aria-label', 'Show Photo IDs');
  Object.assign(toggle.style, {
    position: 'absolute', right: '1px', top: '1px', height: 'calc(100% - 2px)',
    width: '28px', padding: '0', background: 'transparent', color: '#ddd',
    border: '0', cursor: 'pointer',
  });
  const list = document.createElement('div');
  list.setAttribute('role', 'listbox');
  Object.assign(list.style, {
    display: 'none', position: 'absolute', left: '0', right: '0', top: '100%',
    zIndex: '10000', maxHeight: '180px', overflowY: 'auto', boxSizing: 'border-box',
    background: '#17191c', border: '1px solid #666', borderRadius: '6px',
    boxShadow: '0 6px 16px #000a',
  });
  root.append(input, toggle, list);
  // Each ComfyUI DOM widget can have its own stacking context. A large z-index
  // inside the search widget cannot cover the following widget; use the top layer.
  const usePopover = typeof list.showPopover === 'function';
  if (usePopover) {
    list.setAttribute('popover', 'manual');
    Object.assign(list.style, {
      position: 'fixed', inset: 'auto', margin: '0', transformOrigin: 'top left',
    });
  }
  let positionFrame;
  function positionList() {
    const rect = input.getBoundingClientRect();
    const width = input.offsetWidth;
    const scale = width ? rect.width / width : 1;
    Object.assign(list.style, {
      left: `${rect.left}px`, top: `${rect.bottom}px`, width: `${width}px`,
      transform: `scale(${scale})`,
    });
  }
  function trackPosition() {
    if (!root.isConnected) { close(); return; }
    positionList();
    positionFrame = requestAnimationFrame(trackPosition);
  }
  let ids = [];
  let selected = '';
  let edited = false;
  let query = '';
  let searching = false;
  let active = -1;
  let opened = false;
  function updateInput() {
    const hasSelection = selected && selected !== SELECT_ID && ids.includes(selected);
    input.style.color = searching || !hasSelection ? SEARCH_COLOR
      : edited ? EDITED_COLOR : SELECTED_COLOR;
    if (!searching) input.value = hasSelection
      ? `${selected}${edited ? EDITED_SUFFIX : ''}` : '';
    input.title = !searching && hasSelection && edited
      ? `${selected}${EDITED_SUFFIX}` : 'Search or select Photo ID';
  }
  const matches = () => ids.filter((id) => id.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  function close() {
    opened = false;
    if (usePopover) {
      cancelAnimationFrame(positionFrame);
      if (list.matches(':popover-open')) list.hidePopover();
    }
    list.style.display = 'none';
    input.setAttribute('aria-expanded', 'false');
  }
  function render() {
    const values = matches();
    list.replaceChildren();
    for (const [index, id] of values.entries()) {
      const item = document.createElement('button');
      item.type = 'button';
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(id === selected));
      item.textContent = id === selected && edited ? `${id}${EDITED_SUFFIX}` : id;
      Object.assign(item.style, {
        display: 'block', width: '100%', padding: '6px 8px', textAlign: 'left',
        border: '0', background: index === active ? '#30445e' : '#17191c',
        color: id === selected && edited ? EDITED_COLOR : '#fff', cursor: 'pointer',
      });
      item.addEventListener('mousedown', (event) => event.preventDefault());
      item.addEventListener('click', () => choose(id));
      list.append(item);
    }
    if (!values.length) {
      const empty = document.createElement('div');
      empty.textContent = query ? 'No matching Photo IDs' : 'No saved Photo IDs';
      Object.assign(empty.style, { padding: '6px 8px', color: '#aaa' });
      list.append(empty);
    }
  }
  function open() {
    active = -1;
    opened = true;
    render();
    list.style.display = 'block';
    if (usePopover) {
      positionList();
      list.showPopover();
      cancelAnimationFrame(positionFrame);
      positionFrame = requestAnimationFrame(trackPosition);
    }
    input.setAttribute('aria-expanded', 'true');
  }
  function choose(id) {
    selected = id;
    query = '';
    searching = false;
    edited = false;
    updateInput();
    close();
    onSelect(id);
    onQuery?.('');
  }
  input.addEventListener('focus', () => {
    if (edited && !searching) input.select?.();
    open();
  });
  input.addEventListener('input', () => {
    query = input.value;
    searching = true;
    updateInput();
    active = -1;
    if (!opened) open(); else render();
    onQuery?.(query);
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { close(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!opened) open();
      const count = matches().length;
      if (!count) return;
      active = (active + (event.key === 'ArrowDown' ? 1 : -1) + count) % count;
      render();
      list.children[active]?.scrollIntoView?.({ block: 'nearest' });
    } else if (event.key === 'Enter' && opened && active >= 0) {
      event.preventDefault();
      choose(matches()[active]);
    }
  });
  input.addEventListener('blur', () => setTimeout(() => {
    if (!root.contains(document.activeElement)) close();
  }, 0));
  toggle.addEventListener('click', () => {
    if (opened) { close(); return; }
    query = '';
    searching = false;
    updateInput();
    input.focus();
    open();
  });
  return {
    root, input, list, close,
    get query() { return query; },
    set query(value) { query = value; if (opened) render(); },
    setSelected(value) {
      selected = value;
      query = '';
      searching = false;
      edited = false;
      updateInput();
      close();
    },
    setItems(values, selectedId, isEdited = false) {
      ids = [...values].sort((a, b) => photoIdCollator.compare(a, b) || a.localeCompare(b));
      selected = selectedId;
      edited = isEdited;
      updateInput();
      if (opened) render();
    },
  };
}

function renderPhotoIds(node, selectedId = node.photoControls.selectedId) {
  node.photoControls.selectedId = selectedId;
  updatePhotoIdEdited(node);
  node.setDirtyCanvas?.(true, true);
}

function updatePhotoIdEdited(node) {
  const autocomplete = node.photoControls?.autocomplete;
  if (!autocomplete) return;
  const photoId = node.photoControls.selectedId;
  const saved = cache.photo_ids[photoId];
  const edited = !!saved && FIELDS.some(([field]) =>
    (isConnected(node, field) ? '' : String(widget(node, field)?.value ?? '')) !== (saved[field] ?? ''));
  autocomplete.setItems(Object.keys(cache.photo_ids), photoId, edited);
}

function syncPhotoIds(photoIds) {
  cache.photo_ids = photoIds;
  photoIdsLoaded = true;
  for (const node of nodes) {
    if (node.photoControls) renderPhotoIds(node);
  }
  for (const node of referenceNodes) refreshReferencePhotoIds(node);
  if (referenceNodes.size) void refreshReferenceImages().catch((error) =>
    notify(`Cannot load example images: ${error.message}`));
}

async function refreshReferenceImages() {
  const response = await api.fetchApi(`${PHOTO_ID_PATH}/images`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const result = await response.json();
  cache.images = result.images ?? {};
  for (const node of referenceNodes) renderReferenceGallery(node);
}

async function saveGenerationThumbnail(promptId) {
  for (let attempt = 0; attempt < 20; attempt++) {
    const response = await api.fetchApi(`${PHOTO_ID_PATH}/generation_thumbnail`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt_id: promptId }),
    });
    if (response.status === 202) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      continue;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    if (result.saved_photo_ids?.length) await refreshReferenceImages();
    return;
  }
  throw new Error('Generation history was not available in time');
}

function markReferenceSelection(node) {
  const selected = widget(node, 'photo_id')?.value;
  for (const button of node.referenceGallery?.querySelectorAll('button') ?? []) {
    const active = button.dataset.photoId === selected;
    button.setAttribute('aria-pressed', String(active));
    button.style.borderColor = active ? '#74a9ed' : '#666';
    button.style.background = active ? '#30445e' : '#25272c';
  }
}

function referenceIds(node) {
  const query = node.referenceAutocomplete?.query.trim().toLocaleLowerCase() ?? '';
  return Object.keys(cache.photo_ids)
    .filter((id) => id.toLocaleLowerCase().includes(query))
    .sort((a, b) => photoIdCollator.compare(a, b) || a.localeCompare(b));
}

function renderReferenceGallery(node) {
  const gallery = node.referenceGallery;
  if (!gallery) return;
  gallery.replaceChildren();
  const ids = referenceIds(node);
  for (const photoId of ids) {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.photoId = photoId;
    button.title = photoId;
    Object.assign(button.style, {
      display: 'flex', flexDirection: 'column', alignItems: 'stretch', minWidth: '0',
      padding: '4px', border: '1px solid #666', borderRadius: '6px',
      background: '#25272c', color: '#fff', cursor: 'pointer',
    });
    const image = document.createElement('div');
    Object.assign(image.style, {
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '76px', width: '100%', overflow: 'hidden', borderRadius: '4px',
      background: '#17191c', color: '#aaa', fontSize: '11px',
    });
    if (Object.hasOwn(cache.images, photoId)) {
      const thumbnail = document.createElement('img');
      thumbnail.alt = '';
      thumbnail.loading = 'lazy';
      thumbnail.src = `${PHOTO_ID_PATH}/image?${new URLSearchParams({ photo_id: photoId, v: cache.images[photoId] })}`;
      Object.assign(thumbnail.style, { width: '100%', height: '100%', objectFit: 'cover' });
      image.append(thumbnail);
    } else {
      image.textContent = 'No image';
    }
    const label = document.createElement('span');
    label.textContent = photoId;
    Object.assign(label.style, {
      marginTop: '4px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      fontSize: '11px', textAlign: 'center',
    });
    button.append(image, label);
    button.addEventListener('click', () => {
      const photoWidget = widget(node, 'photo_id');
      if (!photoWidget) return;
      setWidget(node, 'photo_id', photoId);
      markReferenceSelection(node);
      node.setDirtyCanvas?.(true, true);
    });
    gallery.append(button);
  }
  if (!ids.length) gallery.textContent = node.referenceAutocomplete?.query.trim()
    ? 'No matching Photo IDs' : 'No saved Photo IDs';
  markReferenceSelection(node);
}

function refreshReferencePhotoIds(node) {
  const photoWidget = widget(node, 'photo_id');
  if (!photoWidget) return;
  if (photoIdsLoaded && !Object.hasOwn(cache.photo_ids, photoWidget.value)) photoWidget.value = SELECT_ID;
  node.referenceAutocomplete?.setItems(Object.keys(cache.photo_ids), photoWidget.value);
  if (!node.referenceAutocomplete?.query) node.referenceAutocomplete?.setSelected(photoWidget.value);
  renderReferenceGallery(node);
  node.setDirtyCanvas?.(true, true);
}

async function request(path, body = undefined) {
  const response = await api.fetchApi(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let result;
  try { result = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
  if (!response.ok) {
    const error = new Error(result.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.conflicts = result.conflicts;
    error.photoId = result.photo_id;
    throw error;
  }
  if (result.photo_ids) syncPhotoIds(result.photo_ids);
  return result;
}

function widget(node, name) {
  return node.widgets?.find((item) => item.name === name);
}

function getValues(node) {
  const values = {};
  for (const [key] of FIELDS) values[key] = isConnected(node, key)
    ? '' : String(widget(node, key)?.value ?? '');
  return values;
}

function getEnabled(node) {
  return Object.fromEntries(FIELDS.map(([key]) => [key, !isConnected(node, key)]));
}

function isConnected(node, field) {
  return node.inputs?.some((input) => input.name === field && input.link != null) ?? false;
}

function setWidget(node, name, value) {
  const target = widget(node, name);
  if (!target) return;
  target.value = value;
  target.callback?.(value);
  if (name === 'photo_id' && node.photoControls) node.photoControls.input.value = value;
  node.setDirtyCanvas?.(true, true);
}

function applyPhotoId(node, photoId) {
  if (!Object.hasOwn(cache.photo_ids, photoId)) {
    updatePhotoIdEdited(node);
    return;
  }
  const values = cache.photo_ids[photoId];
  for (const [key] of FIELDS) {
    if (isConnected(node, key)) continue;
    const value = values[key] ?? '';
    setWidget(node, key, value);
  }
  setWidget(node, 'photo_id', photoId);
  updatePhotoIdEdited(node);
}

function compose(node) {
  const parts = [];
  for (const [key, label] of FIELDS) {
    const value = String(widget(node, key)?.value ?? '').trim();
    if (!isConnected(node, key) && value) parts.push(`${label}:\n${value}`);
  }
  return parts.join('\n\n');
}

function showModal(title, createContent, closeText = 'Close') {
  const overlay = document.createElement('div');
  Object.assign(overlay.style, {
    position: 'fixed', inset: '0', background: 'rgba(0,0,0,.68)', zIndex: '99999',
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '18px',
  });
  const panel = document.createElement('div');
  Object.assign(panel.style, {
    width: 'min(650px,95vw)', maxHeight: '85vh', overflow: 'auto', background: '#25272c',
    color: '#f0f0f0', padding: '20px', border: '1px solid #555', borderRadius: '10px',
    boxSizing: 'border-box', fontFamily: 'system-ui, sans-serif',
  });
  const heading = document.createElement('h3');
  heading.textContent = title;
  heading.style.margin = '0 0 15px';
  panel.append(heading);
  const content = document.createElement('div');
  panel.append(content);
  const actions = document.createElement('div');
  Object.assign(actions.style, { display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '16px' });
  panel.append(actions);
  overlay.append(panel);
  const close = () => overlay.remove();
  function addButton(text, callback, danger = false) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = text;
    Object.assign(btn.style, {
      padding: '8px 12px', cursor: 'pointer', borderRadius: '6px',
      background: danger ? '#793333' : '#444b56', color: 'white', border: '1px solid #666',
    });
    btn.addEventListener('click', callback);
    actions.append(btn);
    return btn;
  }
  addButton(closeText, close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.body.append(overlay);
  createContent({ content, addButton, close });
}

function notify(message) {
  showModal('Photo Prompt Builder', ({ content }) => { content.textContent = message; });
}

async function openHistory(node, field, label, before = null, previous = []) {
  try {
    const query = new URLSearchParams({ field });
    if (before !== null) query.set('before', String(before));
    const { items: list, has_photo_id: hasPhotoId, next_cursor: nextCursor } = await request(`${PATH}?${query}`);
    showModal(`${label} — History (${list.length}${nextCursor !== null ? '+' : ''})`, ({ content, addButton, close }) => {
      const colors = { assigned: '#9de0bd', unassigned: '#c0c5ce' };
      const assigned = list.map((value, i) => hasPhotoId?.[i] ??
        Object.values(cache.photo_ids).some((values) => values[field] === value));
      const legend = document.createElement('div');
      Object.assign(legend.style, { display: 'flex', flexWrap: 'wrap', gap: '16px', marginBottom: '8px', fontSize: '13px' });
      for (const [text, color] of [['● Photo IDあり / With Photo ID', colors.assigned], ['● Photo IDなし / Without Photo ID', colors.unassigned]]) {
        const item = document.createElement('span');
        item.textContent = text;
        item.style.color = color;
        legend.append(item);
      }
      content.append(legend);
      const listbox = document.createElement('div');
      listbox.setAttribute('role', 'listbox');
      listbox.setAttribute('aria-label', `${label} history`);
      Object.assign(listbox.style, {
        maxHeight: '260px', overflowY: 'auto', background: '#17191c',
        border: '1px solid #777', borderRadius: '6px', padding: '4px',
      });
      content.append(listbox);
      let selected = list.length ? 0 : -1;
      const rows = [];
      const preview = document.createElement('pre');
      Object.assign(preview.style, {
        whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '220px', overflow: 'auto',
        padding: '12px', background: '#17191c', borderRadius: '6px',
      });
      const getSelected = () => list[selected];
      const choose = (index) => {
        selected = index;
        rows.forEach((row, i) => {
          row.setAttribute('aria-selected', String(i === selected));
          row.style.background = i === selected ? '#405775' : assigned[i] ? '#20372d' : '#272a30';
        });
        preview.textContent = getSelected() ?? '';
      };
      for (const [i, value] of list.entries()) {
        const row = document.createElement('button');
        row.type = 'button';
        row.setAttribute('role', 'option');
        row.textContent = value.replace(/\s+/g, ' ').slice(0, 150);
        row.title = `${assigned[i] ? 'Photo IDあり / With Photo ID' : 'Photo IDなし / Without Photo ID'}\n${value}`;
        Object.assign(row.style, {
          display: 'block', width: '100%', textAlign: 'left', padding: '9px',
          margin: '0', border: '0', borderRadius: '4px',
          borderLeft: `4px solid ${assigned[i] ? colors.assigned : colors.unassigned}`,
          color: assigned[i] ? colors.assigned : colors.unassigned,
          cursor: 'pointer', overflowWrap: 'anywhere',
        });
        row.addEventListener('click', () => choose(i));
        listbox.append(row);
        rows.push(row);
      }
      if (!list.length) {
        const empty = document.createElement('div');
        empty.textContent = '(No saved history yet)';
        empty.style.padding = '10px';
        listbox.append(empty);
      }
      content.append(preview);
      choose(selected);
      if (previous.length) addButton('Previous page', () => {
        close();
        void openHistory(node, field, label, previous.at(-1), previous.slice(0, -1));
      });
      if (nextCursor !== null) addButton('Next page', () => {
        close();
        void openHistory(node, field, label, nextCursor, [...previous, before]);
      });
      addButton('Use selected', () => {
        const value = getSelected();
        if (value === undefined || isConnected(node, field)) return;
        const target = widget(node, field);
        if (target) {
          target.value = value;
          target.callback?.(value);
          node.setDirtyCanvas?.(true, true);
        }
        close();
      });
      addButton('Delete selected', async () => {
        const value = getSelected();
        if (value === undefined || !window.confirm(`Delete selected ${label} history?`)) return;
        try {
          await request(`${PATH}/delete`, { field, value });
          close();
          await openHistory(node, field, label);
        } catch (error) { notify(`Failed to delete: ${error.message}`); }
      }, true);
      addButton(`Clear all ${label}`, async () => {
        if (!window.confirm(`Delete ALL saved ${label} history?`)) return;
        try {
          await request(`${PATH}/clear`, { field });
          close();
          await openHistory(node, field, label);
        } catch (error) { notify(`Failed to clear history: ${error.message}`); }
      }, true);
    });
  } catch (error) { notify(`Cannot load history: ${error.message}`); }
}

function addHistoryButton(node, field, label) {
  const target = widget(node, field);
  const textarea = target?.element ?? target?.inputEl;
  if (!(textarea instanceof HTMLTextAreaElement)) return;

  const container = document.createElement('div');
  Object.assign(container.style, {
    display: 'flex', flexDirection: 'column', width: '100%', height: '100%',
    minHeight: '104px', gap: '4px', boxSizing: 'border-box',
  });
  container.style.setProperty('--comfy-widget-min-height', `${FIELD_WIDGET_HEIGHT}px`);
  target.options ??= {};
  target.options.getMinHeight = () => FIELD_WIDGET_HEIGHT;
  followNodeWidth(node, target);
  const heading = document.createElement('div');
  heading.textContent = label;
  Object.assign(heading.style, {
    flex: '0 0 20px', lineHeight: '20px', fontSize: '12px', fontWeight: '600',
    color: '#ddd',
  });
  textarea.setAttribute('aria-label', label);
  const row = document.createElement('div');
  Object.assign(row.style, {
    display: 'flex', flex: '1 1 auto', width: '100%', alignItems: 'stretch', gap: '6px',
    boxSizing: 'border-box', minHeight: '80px',
  });
  Object.assign(textarea.style, {
    flex: '1 1 auto', width: '0', height: '100%', minWidth: '0', boxSizing: 'border-box',
  });
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = 'History';
  button.title = `Select ${label} history`;
  button.setAttribute('aria-label', button.title);
  Object.assign(button.style, {
    flex: '0 0 72px', alignSelf: 'stretch', border: '1px solid #666',
    borderRadius: '6px', background: '#444b56', color: '#fff', cursor: 'pointer',
  });
  button.addEventListener('click', () => {
    if (!isConnected(node, field)) void openHistory(node, field, label);
  });
  row.append(textarea, button);
  container.append(heading, row);
  target.element = container;
  textarea.addEventListener('input', () => updatePhotoIdEdited(node));
  const oldCallback = target.callback;
  target.callback = function (...args) {
    const result = oldCallback?.apply(this, args);
    updatePhotoIdEdited(node);
    return result;
  };
  const status = document.createElement('div');
  status.textContent = `${label}: Exclude — external node connected / 外部ノード接続中`;
  Object.assign(status.style, {
    boxSizing: 'border-box', width: '100%', padding: '5px 8px',
    background: '#42372b', color: '#ffe0a8', borderRadius: '6px',
    fontSize: '12px',
  });
  const statusWidget = addFullWidthDOMWidget(node, `${field} connection`, 'connection_status', status, {
    serialize: false, hideOnZoom: false,
    getMinHeight: () => isConnected(node, field) ? 30 : 0,
    getHeight: () => isConnected(node, field) ? 30 : 0,
  });
  statusWidget.serialize = false;
  node.connectionControls ??= {};
  node.connectionControls[field] = { textarea, button, status };
}

function syncConnections(node) {
  for (const [field] of FIELDS) {
    const control = node.connectionControls?.[field];
    if (!control) continue;
    const connected = isConnected(node, field);
    control.textarea.disabled = connected;
    control.button.disabled = connected;
    control.status.style.display = connected ? 'block' : 'none';
  }
  fitNodeToWidgets(node);
  updatePhotoIdEdited(node);
  node.setDirtyCanvas?.(true, true);
}

function preview(node) {
  showModal('Combined Prompt Preview', ({ content, addButton }) => {
    const textarea = document.createElement('textarea');
    textarea.readOnly = true;
    textarea.value = compose(node);
    Object.assign(textarea.style, {
      boxSizing: 'border-box', width: '100%', height: '380px', padding: '12px',
      background: '#15171b', color: '#f3f3f3', border: '1px solid #666',
      whiteSpace: 'pre-wrap', borderRadius: '6px', resize: 'vertical',
    });
    content.append(textarea);
    addButton('Copy prompt', async () => {
      try { await navigator.clipboard.writeText(textarea.value); }
      catch { textarea.select(); document.execCommand('copy'); }
    });
  });
}

function selectedPhotoId(node) {
  const photoId = node.photoControls?.selectedId;
  return photoId && Object.hasOwn(cache.photo_ids, photoId) ? photoId : null;
}

async function saveCurrent(node) {
  try {
    const photoId = String(widget(node, 'photo_id')?.value ?? '');
    if (photoId && !PHOTO_ID_RE.test(photoId)) {
      throw new Error('Photo ID must be 1–24 characters: A–Z, a–z, 0–9, or !#$%*+-./:;=?@_~');
    }
    const payload = {
      entries: getValues(node), enabled: getEnabled(node), photo_id: photoId,
    };
    let result;
    try {
      result = await request(PATH, payload);
    } catch (error) {
      if (error.status !== 409 || !Array.isArray(error.conflicts)) throw error;
      const labels = error.conflicts.map((key) => FIELDS.find(([field]) => field === key)?.[1] ?? key);
      const message = labels.map((label) => `${label} already has different text assigned to this Photo ID.`).join('\n');
      if (!window.confirm(`${message}\nOverwrite the assignments for Photo ID "${error.photoId}"?`)) return;
      result = await request(PATH, { ...payload, photo_id: error.photoId, overwrite: true });
    }
    if (node.photoControls) {
      node.photoControls.autocomplete.setSelected(result.saved_photo_id);
      renderPhotoIds(node, result.saved_photo_id);
    }
    setWidget(node, 'photo_id', result.saved_photo_id);
    notify(`Saved current values with Photo ID: ${result.saved_photo_id}`);
  } catch (error) { notify(`Cannot save history: ${error.message}`); }
}

function openRenamePhotoId(node) {
  const oldId = selectedPhotoId(node);
  if (!oldId) return notify('Select a Photo ID to rename.');
  showModal(`Rename Photo ID: ${oldId}`, ({ content, addButton, close }) => {
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 24;
    input.value = oldId;
    input.placeholder = 'New Photo ID';
    input.setAttribute('aria-label', 'New Photo ID');
    Object.assign(input.style, {
      boxSizing: 'border-box', width: '100%', padding: '8px', background: '#17191c',
      color: '#fff', border: '1px solid #777', borderRadius: '6px',
    });
    const errorText = document.createElement('div');
    Object.assign(errorText.style, { color: '#ffb3b3', marginTop: '8px' });
    content.append(input, errorText);
    const submit = async () => {
      const newId = input.value;
      if (!PHOTO_ID_RE.test(newId)) {
        errorText.textContent = 'Photo ID must be 1–24 characters: A–Z, a–z, 0–9, or !#$%*+-./:;=?@_~.';
        return;
      }
      if (Object.hasOwn(cache.photo_ids, newId)) {
        errorText.textContent = 'This Photo ID is already in use.';
        return;
      }
      try {
        const affected = [...nodes].filter((item) => item.photoControls?.selectedId === oldId);
        const inputs = [...nodes].filter((item) => widget(item, 'photo_id')?.value === oldId);
        await request(`${PHOTO_ID_PATH}/rename`, { old_id: oldId, new_id: newId });
        for (const item of affected) {
          item.photoControls.autocomplete.setSelected(newId);
          renderPhotoIds(item, newId);
        }
        for (const item of inputs) setWidget(item, 'photo_id', newId);
        close();
      } catch (error) { errorText.textContent = error.message; }
    };
    input.addEventListener('keydown', (event) => { if (event.key === 'Enter') void submit(); });
    addButton('OK', () => { void submit(); });
    input.focus();
  }, 'Cancel');
}

async function deleteSelectedPhotoId(node) {
  const photoId = selectedPhotoId(node);
  if (!photoId) return notify('Select a Photo ID to delete.');
  if (!window.confirm(`Delete Photo ID "${photoId}" from all sections?\nText history will remain.`)) return;
  try {
    const inputs = [...nodes].filter((item) => widget(item, 'photo_id')?.value === photoId);
    await request(`${PHOTO_ID_PATH}/delete`, { photo_id: photoId });
    for (const item of inputs) setWidget(item, 'photo_id', '');
    for (const item of nodes) {
      if (item.photoControls?.selectedId !== photoId) continue;
      item.photoControls.autocomplete.setSelected(SELECT_ID);
      renderPhotoIds(item, SELECT_ID);
    }
    // syncPhotoIds resets the selection; section text widgets stay untouched.
  } catch (error) { notify(`Cannot delete Photo ID: ${error.message}`); }
}

function makeControlButton(label, title, action) {
  const button = document.createElement('button');
  button.type = 'button';
  button.textContent = label;
  button.title = title;
  Object.assign(button.style, {
    flex: '0 0 75px', minWidth: '0', padding: '4px', cursor: 'pointer',
    borderRadius: '6px', background: '#444b56', color: '#fff', border: '1px solid #666',
  });
  button.addEventListener('click', action);
  return button;
}

function addPhotoControls(node) {
  const photoWidget = widget(node, 'photo_id');
  if (!photoWidget) return;
  const makeRow = () => {
    const row = document.createElement('div');
    Object.assign(row.style, {
      display: 'flex', boxSizing: 'border-box', width: '100%', height: '100%',
      minHeight: '36px', minWidth: '0', flexShrink: '0', alignItems: 'stretch', gap: '5px',
    });
    return row;
  };
  const autocomplete = makePhotoIdAutocomplete((photoId) => {
    applyPhotoId(node, photoId);
    renderPhotoIds(node, photoId);
  });
  const first = makeRow();
  autocomplete.root.style.flex = '1 1 0%';
  first.append(autocomplete.root,
    makeControlButton('Rename', 'Rename selected Photo ID', () => openRenamePhotoId(node)),
    makeControlButton('Delete', 'Delete selected Photo ID', () => { void deleteSelectedPhotoId(node); }));

  const input = document.createElement('input');
  input.type = 'text';
  input.maxLength = 24;
  input.value = String(photoWidget.value ?? '');
  input.placeholder = 'Photo ID (blank = time)';
  input.setAttribute('aria-label', 'Photo ID for save');
  Object.assign(input.style, {
    flex: '1 1 0%', width: '100%', minWidth: '0', boxSizing: 'border-box', padding: '4px',
    background: '#17191c', color: '#fff', border: '1px solid #666', borderRadius: '6px',
  });
  input.addEventListener('input', () => setWidget(node, 'photo_id', input.value));
  const second = makeRow();
  second.append(input,
    makeControlButton('Save', 'Save current values', () => { void saveCurrent(node); }),
    makeControlButton('Preview', 'Preview combined prompt', () => preview(node)));

  photoWidget.type = 'hidden';
  photoWidget.options ??= {};
  photoWidget.options.hidden = true;
  photoWidget.computeSize = () => [0, -4];
  photoWidget.draw = () => {};
  node.photoControls = { autocomplete, input, selectedId: SELECT_ID };
  // DOM widgets reserve 10px above and below the element by default.
  const firstWidget = addFullWidthDOMWidget(node, 'Photo ID selection', 'photo_id_controls', first, {
    serialize: false, hideOnZoom: false, getMinHeight: () => 56, getHeight: () => 56,
  });
  const secondWidget = addFullWidthDOMWidget(node, 'Photo ID actions', 'photo_id_controls', second, {
    serialize: false, hideOnZoom: false, getMinHeight: () => 56, getHeight: () => 56,
  });
  firstWidget.serialize = false;
  secondWidget.serialize = false;
  renderPhotoIds(node);
}

function addReferencePromptControls(node) {
  const tagWidget = widget(node, 'additional_tag');
  const promptWidget = widget(node, 'additional_prompt');
  if (!tagWidget || !promptWidget) return;
  const row = document.createElement('div');
  Object.assign(row.style, {
    display: 'flex', flexDirection: 'column', width: '100%', height: '100%',
    minWidth: '0', minHeight: '70px', flexShrink: '0',
    alignItems: 'stretch', gap: '6px', boxSizing: 'border-box',
  });
  const select = document.createElement('select');
  select.title = 'Tag to append prompt to';
  select.setAttribute('aria-label', select.title);
  for (const [, label] of FIELDS) {
    const option = document.createElement('option');
    option.value = label;
    option.textContent = label;
    select.append(option);
  }
  const input = document.createElement('input');
  input.type = 'text';
  input.placeholder = 'Additional prompt / LoRA trigger words';
  input.setAttribute('aria-label', 'Additional prompt / LoRA trigger words');
  for (const element of [select, input]) {
    Object.assign(element.style, {
      width: '100%', minWidth: '0', minHeight: '32px', padding: '5px', background: '#17191c', color: '#fff',
      border: '1px solid #666', borderRadius: '6px', boxSizing: 'border-box',
    });
  }
  select.style.flex = '0 0 32px';
  input.style.flex = '1 0 32px';
  select.addEventListener('change', () => setWidget(node, 'additional_tag', select.value));
  input.addEventListener('input', () => setWidget(node, 'additional_prompt', input.value));
  for (const target of [tagWidget, promptWidget]) {
    target.type = 'hidden';
    target.options ??= {};
    target.options.hidden = true;
    target.computeSize = () => [0, -4];
    target.draw = () => {};
    const oldCallback = target.callback;
    target.callback = function (...args) {
      const result = oldCallback?.apply(this, args);
      sync();
      return result;
    };
  }
  function sync() {
    select.value = tagWidget.value;
    input.value = String(promptWidget.value ?? '');
  }
  sync();
  row.append(select, input);
  const control = addFullWidthDOMWidget(node, 'Additional prompt', 'additional_prompt_controls', row, {
    serialize: false, hideOnZoom: false,
    getMinHeight: () => 90, getHeight: () => 90,
  });
  control.serialize = false;
  return sync;
}

function fitNodeToWidgets(node) {
  const [widgetWidth, widgetHeight] = node.computeSize();
  node.setSize([
    Math.max(node.size[0], widgetWidth, 430),
    Math.max(node.size[1], widgetHeight, 760),
  ]);
}

app.registerExtension({
  name: 'MagichanLab_photo_prompt_builder',
  setup() {
    window.addEventListener('magichanlab-photo-ids-changed', () => {
      void request(`${PATH}?include_history=0`).catch((error) =>
        notify(`Cannot refresh Photo IDs: ${error.message}`));
    });
    api.addEventListener('execution_success', ({ detail }) => {
      if (detail?.prompt_id) void saveGenerationThumbnail(detail.prompt_id).catch((error) =>
        notify(`Cannot save Photo ID thumbnail: ${error.message}`));
    });
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === REFERENCE_NODE_TYPE) {
      const oldCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function (...args) {
        const result = oldCreated?.apply(this, args);
        referenceNodes.add(this);
        const syncAdditionalPrompt = addReferencePromptControls(this);
        const photoWidget = widget(this, 'photo_id');
        if (photoWidget) {
          photoWidget.type = 'hidden';
          photoWidget.options ??= {};
          photoWidget.options.hidden = true;
          photoWidget.computeSize = () => [0, -4];
          photoWidget.draw = () => {};
          const oldCallback = photoWidget.callback;
          photoWidget.callback = (...callbackArgs) => {
            const callbackResult = oldCallback?.apply(photoWidget, callbackArgs);
            if (this.referenceAutocomplete) {
              this.referenceAutocomplete.setSelected(photoWidget.value);
              refreshReferencePhotoIds(this);
            }
            markReferenceSelection(this);
            return callbackResult;
          };
        }
        const autocomplete = makePhotoIdAutocomplete(
          (photoId) => setWidget(this, 'photo_id', photoId),
          () => renderReferenceGallery(this));
        this.referenceAutocomplete = autocomplete;
        autocomplete.setSelected(photoWidget?.value ?? SELECT_ID);
        const searchWidget = addFullWidthDOMWidget(this, 'Photo ID selection', 'photo_id_search', autocomplete.root, {
          serialize: false, hideOnZoom: false,
          getMinHeight: () => 54, getHeight: () => 54,
        });
        searchWidget.serialize = false;
        refreshReferencePhotoIds(this);
        const gallery = document.createElement('div');
        gallery.setAttribute('aria-label', 'Photo ID examples');
        Object.assign(gallery.style, {
          display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: '5px', width: '100%', height: '100%', boxSizing: 'border-box',
          padding: '4px', overflowY: 'auto', background: '#17191c',
          border: '1px solid #555', borderRadius: '6px',
        });
        this.referenceGallery = gallery;
        const galleryWidget = addFullWidthDOMWidget(this, 'Photo ID examples', 'photo_id_gallery', gallery, {
          serialize: false, hideOnZoom: false,
          getMinHeight: () => 190, getHeight: () => 190,
        });
        galleryWidget.serialize = false;
        renderReferenceGallery(this);
        const [width, height] = this.computeSize();
        this.setSize([Math.max(this.size[0], width, 320),
                      Math.max(this.size[1], height, 260)]);
        const oldRemoved = this.onRemoved;
        this.onRemoved = function (...removeArgs) {
          this.referenceAutocomplete?.close();
          referenceNodes.delete(this);
          return oldRemoved?.apply(this, removeArgs);
        };
        const oldConfigure = this.onConfigure;
        this.onConfigure = function (...configureArgs) {
          const configured = oldConfigure?.apply(this, configureArgs);
          syncAdditionalPrompt?.();
          this.referenceAutocomplete.setSelected(photoWidget?.value ?? SELECT_ID);
          refreshReferencePhotoIds(this);
          return configured;
        };
        void request(`${PATH}?include_history=0`).catch((error) => notify(`Cannot load Photo IDs: ${error.message}`));
        return result;
      };
      return;
    }
    if (nodeData.name !== NODE_TYPE) return;
    const oldCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = oldCreated?.apply(this, args);
      nodes.add(this);
      const oldRemoved = this.onRemoved;
      this.onRemoved = function (...removeArgs) {
        this.photoControls?.autocomplete.close();
        nodes.delete(this);
        return oldRemoved?.apply(this, removeArgs);
      };
      for (const [key, label] of FIELDS) {
        addHistoryButton(this, key, label);
      }
      addPhotoControls(this);
      const oldConfigure = this.onConfigure;
      this.onConfigure = function (...configureArgs) {
        // Old workflows serialized a Boolean after each field, optionally with history_limit.
        const values = configureArgs[0]?.widgets_values;
        let restoredPhotoId;
        if (Array.isArray(values) && values.length >= FIELDS.length * 2 + 2) {
          restoredPhotoId = values[typeof values[FIELDS.length * 2 + 1] === 'number'
            ? FIELDS.length * 2 + 2 : FIELDS.length * 2 + 1];
          values.splice(0, values.length,
            ...FIELDS.map((_, index) => values[index * 2]),
            values[FIELDS.length * 2],
            restoredPhotoId);
        }
        const configured = oldConfigure?.apply(this, configureArgs);
        if (restoredPhotoId !== undefined) {
          const photoWidget = widget(this, 'photo_id');
          if (photoWidget) photoWidget.value = String(restoredPhotoId ?? '');
        }
        if (this.photoControls) {
          const photoId = String(widget(this, 'photo_id')?.value ?? '');
          this.photoControls.input.value = photoId;
          this.photoControls.selectedId = photoId;
          this.photoControls.autocomplete.setSelected(photoId);
          renderPhotoIds(this);
        }
        syncConnections(this);
        return configured;
      };
      const oldConnectionsChange = this.onConnectionsChange;
      this.onConnectionsChange = function (...connectionArgs) {
        const changed = oldConnectionsChange?.apply(this, connectionArgs);
        queueMicrotask(() => syncConnections(this));
        return changed;
      };
      void request(`${PATH}?include_history=0`).catch((error) => notify(`Cannot load Photo IDs: ${error.message}`));
      syncConnections(this);
      return result;
    };
  },
});
