import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

const NODE_TYPE = 'MagichanLab_Krea2PhotoPromptBuilder';
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
const cache = { history: null, photo_ids: {} };
const nodes = new Set();
const PHOTO_ID_RE = /^[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}$/;
const SELECT_ID = '(Select Photo ID)';

function syncPhotoIds(photoIds) {
  cache.photo_ids = photoIds;
  const values = [SELECT_ID, ...Object.keys(photoIds).sort().reverse()];
  for (const node of nodes) {
    const picker = widget(node, 'Select Photo ID');
    if (!picker) continue;
    picker.options.values = values;
    if (!values.includes(picker.value)) picker.value = SELECT_ID;
    node.setDirtyCanvas?.(true, true);
  }
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
  if (result.history) cache.history = result.history;
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

function showModal(title, createContent) {
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
  addButton('Close', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.body.append(overlay);
  createContent({ content, addButton, close });
}

function notify(message) {
  showModal('Photo Prompt Builder', ({ content }) => { content.textContent = message; });
}

async function openHistory(node, field, label) {
  try {
    const { history } = await request(PATH);
    const list = history[field] || [];
    showModal(`${label} — History (${list.length})`, ({ content, addButton, close }) => {
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
  button.textContent = '履歴';
  button.title = `${label} の履歴を選択`;
  button.setAttribute('aria-label', button.title);
  Object.assign(button.style, {
    flex: '0 0 48px', alignSelf: 'stretch', border: '1px solid #666',
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

app.registerExtension({
  name: 'MagichanLab_photo_prompt_builder',
  async beforeRegisterNodeDef(nodeType, nodeData) {
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
      this.addWidget('combo', 'Select Photo ID', SELECT_ID,
        (photoId) => applyPhotoId(this, photoId), { values: [SELECT_ID], serialize: false });
      void request(PATH).catch((error) => notify(`Cannot load Photo IDs: ${error.message}`));
      this.addWidget('button', 'Save current values to history', null, async () => {
        try {
          const limit = Number(widget(this, 'history_limit')?.value ?? 100);
          const photoId = String(widget(this, 'photo_id')?.value ?? '');
          if (photoId && !PHOTO_ID_RE.test(photoId)) {
            throw new Error('Photo ID must be 1–24 characters: A–Z, a–z, 0–9, or !#$%*+-./:;=?@_~');
          }
          const payload = {
            entries: getValues(this), enabled: getEnabled(this), photo_id: photoId, limit,
          };
          let result;
          try {
            result = await request(PATH, payload);
          } catch (error) {
            if (error.status !== 409 || !Array.isArray(error.conflicts)) throw error;
            const labels = error.conflicts.map((key) => FIELDS.find(([field]) => field === key)?.[1] ?? key);
            const message = labels.map((label) => `${label}には既に同じPhoto IDが別の文字列に付いています。`).join('\n');
            if (!window.confirm(`${message}\nPhoto ID「${error.photoId}」の割り当てを上書きしますか？`)) return;
            result = await request(PATH, { ...payload, photo_id: error.photoId, overwrite: true });
          }
          const picker = widget(this, 'Select Photo ID');
          if (picker) picker.value = result.saved_photo_id;
          notify(`Saved current values with Photo ID: ${result.saved_photo_id}`);
        } catch (error) { notify(`Cannot save history: ${error.message}`); }
      }, { serialize: false });
      this.addWidget('button', 'Preview combined prompt', null,
        () => preview(this), { serialize: false });
      this.setSize([Math.max(this.size[0], 430), Math.max(this.size[1], 760)]);
      return result;
    };
  },
});
