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
const nodes = new Set();
const referenceNodes = new Set();
const PHOTO_ID_RE = /^[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}$/;
const SELECT_ID = '(Select Photo ID)';
const photoIdCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

function renderPhotoIds(node, selectedId = node.photoControls.select.value) {
  const { search, select } = node.photoControls;
  const query = search.value.trim().toLocaleLowerCase();
  const values = Object.keys(cache.photo_ids)
    .filter((id) => id.toLocaleLowerCase().includes(query))
    .sort((a, b) => photoIdCollator.compare(a, b) || a.localeCompare(b));
  select.replaceChildren(...[SELECT_ID, ...values].map((value) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    return option;
  }));
  select.value = values.includes(selectedId) ? selectedId : SELECT_ID;
  node.setDirtyCanvas?.(true, true);
}

function syncPhotoIds(photoIds) {
  cache.photo_ids = photoIds;
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
  const query = node.referenceSearch?.value.trim().toLocaleLowerCase() ?? '';
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
      photoWidget.value = photoId;
      photoWidget.callback?.(photoId);
      markReferenceSelection(node);
      node.setDirtyCanvas?.(true, true);
    });
    gallery.append(button);
  }
  if (!ids.length) gallery.textContent = node.referenceSearch?.value.trim()
    ? 'No matching Photo IDs' : 'No saved Photo IDs';
  markReferenceSelection(node);
}

function refreshReferencePhotoIds(node) {
  const photoWidget = widget(node, 'photo_id');
  if (!photoWidget) return;
  const ids = referenceIds(node);
  photoWidget.options ??= {};
  photoWidget.options.values = [SELECT_ID, ...ids];
  if (!Object.hasOwn(cache.photo_ids, photoWidget.value)) photoWidget.value = SELECT_ID;
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
  for (const [key] of FIELDS) values[key] = String(widget(node, key)?.value ?? '');
  return values;
}

function getEnabled(node) {
  return Object.fromEntries(FIELDS.map(([key]) => [key, widget(node, `use_${key}`)?.value !== false]));
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
  if (!Object.hasOwn(cache.photo_ids, photoId)) return;
  const values = cache.photo_ids[photoId];
  for (const [key] of FIELDS) {
    const value = values[key] ?? '';
    setWidget(node, key, value);
    setWidget(node, `use_${key}`, Boolean(value));
  }
  setWidget(node, 'photo_id', photoId);
}

function compose(node) {
  const parts = [];
  for (const [key, label] of FIELDS) {
    const enabled = widget(node, `use_${key}`)?.value !== false;
    const value = String(widget(node, key)?.value ?? '').trim();
    if (enabled && value) parts.push(`${label}:\n${value}`);
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
    const { items: list, next_cursor: nextCursor } = await request(`${PATH}?${query}`);
    showModal(`${label} — History (${list.length}${nextCursor !== null ? '+' : ''})`, ({ content, addButton, close }) => {
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
          row.style.background = i === selected ? '#405775' : 'transparent';
        });
        preview.textContent = getSelected() ?? '';
      };
      for (const [i, value] of list.entries()) {
        const row = document.createElement('button');
        row.type = 'button';
        row.setAttribute('role', 'option');
        row.textContent = value.replace(/\s+/g, ' ').slice(0, 150);
        row.title = value;
        Object.assign(row.style, {
          display: 'block', width: '100%', textAlign: 'left', padding: '9px',
          margin: '0', border: '0', borderRadius: '4px', color: '#fff',
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
        if (value === undefined) return;
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

  const row = document.createElement('div');
  Object.assign(row.style, {
    display: 'flex', width: '100%', height: '100%', alignItems: 'stretch', gap: '6px',
    boxSizing: 'border-box', minHeight: '50px',
  });
  row.style.setProperty('--comfy-widget-min-height', '80px');
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
  button.addEventListener('click', () => { void openHistory(node, field, label); });
  row.append(textarea, button);
  target.element = row;
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
  const photoId = node.photoControls?.select.value;
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
      node.photoControls.search.value = '';
      renderPhotoIds(node, result.saved_photo_id);
    }
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
        const affected = [...nodes].filter((item) => item.photoControls?.select.value === oldId);
        const inputs = [...nodes].filter((item) => widget(item, 'photo_id')?.value === oldId);
        await request(`${PHOTO_ID_PATH}/rename`, { old_id: oldId, new_id: newId });
        for (const item of affected) {
          item.photoControls.search.value = '';
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
      minHeight: '36px', alignItems: 'stretch', gap: '5px',
    });
    return row;
  };
  const select = document.createElement('select');
  select.setAttribute('aria-label', 'Select Photo ID');
  select.title = 'Select Photo ID';
  Object.assign(select.style, {
    flex: '1 1 auto', width: '0', minWidth: '0', padding: '4px',
    background: '#17191c', color: '#fff', border: '1px solid #666', borderRadius: '6px',
  });
  select.addEventListener('change', () => applyPhotoId(node, select.value));
  const search = document.createElement('input');
  search.type = 'search';
  search.placeholder = 'Search ID';
  search.setAttribute('aria-label', 'Search Photo ID');
  Object.assign(search.style, {
    flex: '1 1 auto', width: '0', minWidth: '0', padding: '4px',
    background: '#17191c', color: '#fff', border: '1px solid #666', borderRadius: '6px',
  });
  search.addEventListener('input', () => renderPhotoIds(node));
  const first = makeRow();
  first.append(search, select,
    makeControlButton('Rename', 'Rename selected Photo ID', () => openRenamePhotoId(node)),
    makeControlButton('Delete', 'Delete selected Photo ID', () => { void deleteSelectedPhotoId(node); }));

  const input = document.createElement('input');
  input.type = 'text';
  input.maxLength = 24;
  input.value = String(photoWidget.value ?? '');
  input.placeholder = 'Photo ID (blank = time)';
  input.setAttribute('aria-label', 'Photo ID for save');
  Object.assign(input.style, {
    flex: '1 1 auto', width: '0', minWidth: '0', padding: '4px',
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
  node.photoControls = { search, select, input };
  // DOM widgets reserve 10px above and below the element by default.
  const options = { serialize: false, hideOnZoom: false,
    getMinHeight: () => 56, getHeight: () => 56 };
  const firstWidget = node.addDOMWidget('Photo ID selection', 'photo_id_controls', first, options);
  const secondWidget = node.addDOMWidget('Photo ID actions', 'photo_id_controls', second, options);
  firstWidget.serialize = false;
  secondWidget.serialize = false;
  syncPhotoIds(cache.photo_ids);
}

function addReferencePromptControls(node) {
  const tagWidget = widget(node, 'additional_tag');
  const promptWidget = widget(node, 'additional_prompt');
  if (!tagWidget || !promptWidget) return;
  const row = document.createElement('div');
  Object.assign(row.style, {
    display: 'flex', width: '100%', height: '100%', minHeight: '32px',
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
      minWidth: '0', padding: '5px', background: '#17191c', color: '#fff',
      border: '1px solid #666', borderRadius: '6px', boxSizing: 'border-box',
    });
  }
  select.style.flex = '0 1 145px';
  input.style.flex = '1 1 0';
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
  const control = node.addDOMWidget('Additional prompt', 'additional_prompt_controls', row, {
    serialize: false, hideOnZoom: false,
    getMinHeight: () => 52, getHeight: () => 52,
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
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === REFERENCE_NODE_TYPE) {
      const oldCreated = nodeType.prototype.onNodeCreated;
      nodeType.prototype.onNodeCreated = function (...args) {
        const result = oldCreated?.apply(this, args);
        referenceNodes.add(this);
        const syncAdditionalPrompt = addReferencePromptControls(this);
        const photoWidget = widget(this, 'photo_id');
        if (photoWidget) {
          const oldCallback = photoWidget.callback;
          photoWidget.callback = (...callbackArgs) => {
            const callbackResult = oldCallback?.apply(photoWidget, callbackArgs);
            markReferenceSelection(this);
            return callbackResult;
          };
        }
        const search = document.createElement('input');
        search.type = 'search';
        search.placeholder = 'Search Photo ID';
        search.setAttribute('aria-label', 'Search Photo ID');
        Object.assign(search.style, {
          boxSizing: 'border-box', width: '100%', height: '100%', padding: '5px',
          background: '#17191c', color: '#fff', border: '1px solid #666',
          borderRadius: '6px',
        });
        this.referenceSearch = search;
        search.addEventListener('input', () => refreshReferencePhotoIds(this));
        const searchWidget = this.addDOMWidget('Search Photo ID', 'photo_id_search', search, {
          serialize: false, hideOnZoom: false,
          getMinHeight: () => 30, getHeight: () => 30,
        });
        searchWidget.serialize = false;
        const gallery = document.createElement('div');
        gallery.setAttribute('aria-label', 'Photo ID examples');
        Object.assign(gallery.style, {
          display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
          gap: '5px', width: '100%', height: '100%', boxSizing: 'border-box',
          padding: '4px', overflowY: 'auto', background: '#17191c',
          border: '1px solid #555', borderRadius: '6px',
        });
        this.referenceGallery = gallery;
        const galleryWidget = this.addDOMWidget('Photo ID examples', 'photo_id_gallery', gallery, {
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
          referenceNodes.delete(this);
          return oldRemoved?.apply(this, removeArgs);
        };
        const oldConfigure = this.onConfigure;
        this.onConfigure = function (...configureArgs) {
          const configured = oldConfigure?.apply(this, configureArgs);
          syncAdditionalPrompt?.();
          markReferenceSelection(this);
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
        nodes.delete(this);
        return oldRemoved?.apply(this, removeArgs);
      };
      for (const [key, label] of FIELDS) {
        addHistoryButton(this, key, label);
      }
      addPhotoControls(this);
      const oldConfigure = this.onConfigure;
      this.onConfigure = function (...configureArgs) {
        const configured = oldConfigure?.apply(this, configureArgs);
        // Older workflows serialize history_limit just before photo_id.
        const values = configureArgs[0]?.widgets_values;
        const oldLimitIndex = FIELDS.length * 2 + 1;
        if (Array.isArray(values) && typeof values[oldLimitIndex] === 'number') {
          const photoWidget = widget(this, 'photo_id');
          if (photoWidget) photoWidget.value = String(values[oldLimitIndex + 1] ?? '');
          values.splice(oldLimitIndex, 1);
        }
        if (this.photoControls) {
          this.photoControls.input.value = String(widget(this, 'photo_id')?.value ?? '');
        }
        fitNodeToWidgets(this);
        return configured;
      };
      void request(`${PATH}?include_history=0`).catch((error) => notify(`Cannot load Photo IDs: ${error.message}`));
      fitNodeToWidgets(this);
      return result;
    };
  },
});
