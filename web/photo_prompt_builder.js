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
const cache = { history: null };

async function request(path, body = undefined) {
  const response = await api.fetchApi(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let result;
  try { result = await response.json(); } catch { throw new Error(`HTTP ${response.status}`); }
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  if (result.history) cache.history = result.history;
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
      const select = document.createElement('select');
      Object.assign(select.style, {
        width: '100%', padding: '10px', background: '#17191c', color: '#fff',
        border: '1px solid #777', borderRadius: '6px',
      });
      for (const [i, value] of list.entries()) {
        const option = document.createElement('option');
        option.value = String(i);
        option.textContent = value.replace(/\s+/g, ' ').slice(0, 150);
        select.append(option);
      }
      if (!list.length) {
        const option = document.createElement('option');
        option.textContent = '(No saved history yet)';
        select.append(option);
        select.disabled = true;
      }
      content.append(select);
      const preview = document.createElement('pre');
      Object.assign(preview.style, {
        whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '220px', overflow: 'auto',
        padding: '12px', background: '#17191c', borderRadius: '6px',
      });
      content.append(preview);
      const getSelected = () => list[Number(select.value)];
      const updatePreview = () => { preview.textContent = getSelected() ?? ''; };
      select.addEventListener('change', updatePreview);
      updatePreview();
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
      for (const [key, label] of FIELDS) {
        this.addWidget('button', `History: ${label} ▾`, null,
          () => { void openHistory(this, key, label); }, { serialize: false });
      }
      this.addWidget('button', 'Save current values to history', null, async () => {
        try {
          const limit = Number(widget(this, 'history_limit')?.value ?? 100);
          await request(PATH, { entries: getValues(this), limit });
          notify('Current nonempty values were saved to the JSON history.');
        } catch (error) { notify(`Cannot save history: ${error.message}`); }
      }, { serialize: false });
      this.addWidget('button', 'Preview combined prompt', null,
        () => preview(this), { serialize: false });
      this.setSize([Math.max(this.size[0], 430), Math.max(this.size[1], 920)]);
      return result;
    };
  },
});
