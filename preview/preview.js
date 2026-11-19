const fields = [
  ['subject', 'Subject'], ['appearance', 'Clothing'],
  ['hair_makeup', 'Hair & Makeup'], ['pose', 'Posing'],
  ['expression', 'Expression'], ['environment', 'Environment'],
  ['composition', 'Composition & Camera'], ['lighting', 'Lighting'],
  ['finishing', 'Finishing'],
];
const storageKey = 'photo-prompt-builder-preview-history';
const idsKey = 'photo-prompt-builder-preview-photo-ids';
const photoIdPattern = /^[A-Za-z0-9!#$%*+\-./:;=?@_~]{1,24}$/;
const nodeElement = document.querySelector('#node');
const status = document.querySelector('#status');
let extension;

const emptyHistory = () => Object.fromEntries(fields.map(([key]) => [key, []]));
function readHistory() {
  try { return { ...emptyHistory(), ...JSON.parse(localStorage.getItem(storageKey) || '{}') }; }
  catch { return emptyHistory(); }
}
function readIds() {
  try { return Object.assign(Object.create(null), JSON.parse(localStorage.getItem(idsKey) || '{}')); }
  catch { return Object.create(null); }
}
function reply(history, photoIds, savedPhotoId = null) {
  localStorage.setItem(storageKey, JSON.stringify(history));
  localStorage.setItem(idsKey, JSON.stringify(photoIds));
  return { ok: true, json: async () => ({ history, photo_ids: photoIds, saved_photo_id: savedPhotoId }) };
}
const api = {
  async fetchApi(path, options) {
    const history = readHistory();
    const photoIds = readIds();
    if (!options) return reply(history, photoIds);
    const body = JSON.parse(options.body);
    if (path.endsWith('/photo_id/rename')) {
      if (!photoIdPattern.test(body.new_id) || !Object.hasOwn(photoIds, body.old_id) ||
          Object.hasOwn(photoIds, body.new_id)) {
        return { ok: false, status: 400, json: async () => ({ error: 'Invalid or already used Photo ID' }) };
      }
      photoIds[body.new_id] = photoIds[body.old_id];
      delete photoIds[body.old_id];
      return reply(history, photoIds);
    }
    if (path.endsWith('/photo_id/delete')) {
      if (!Object.hasOwn(photoIds, body.photo_id)) {
        return { ok: false, status: 400, json: async () => ({ error: 'Photo ID does not exist' }) };
      }
      delete photoIds[body.photo_id];
      return reply(history, photoIds);
    }
    if (path.endsWith('/delete')) {
      history[body.field] = history[body.field].filter(value => value !== body.value);
      for (const values of Object.values(photoIds)) {
        if (values[body.field] === body.value) delete values[body.field];
      }
    } else if (path.endsWith('/clear')) {
      history[body.field] = [];
      for (const values of Object.values(photoIds)) delete values[body.field];
    } else {
      const savedPhotoId = body.photo_id === undefined ? null :
        (body.photo_id || new Date().toLocaleString('sv-SE', { hour12: false }).replace(/\D/g, '').slice(2));
      if (savedPhotoId && !body.overwrite) {
        const assigned = Object.hasOwn(photoIds, savedPhotoId) ? photoIds[savedPhotoId] : {};
        const conflicts = Object.entries(body.entries).filter(([key, raw]) =>
          raw.trim() && body.enabled?.[key] !== false &&
          Object.hasOwn(assigned, key) && assigned[key] !== raw.trim()).map(([key]) => key);
        if (conflicts.length) return {
          ok: false, status: 409,
          json: async () => ({ error: 'Photo ID conflict', photo_id: savedPhotoId, conflicts }),
        };
      }
      if (savedPhotoId) photoIds[savedPhotoId] = {};
      for (const [key, raw] of Object.entries(body.entries)) {
        const value = raw.trim();
        if (value) history[key] = [value, ...history[key].filter(item => item !== value)];
        if (value && savedPhotoId && body.enabled?.[key] !== false) photoIds[savedPhotoId][key] = value;
      }
      for (const [key] of fields) {
        let untagged = 0;
        history[key] = history[key].filter(value => {
          if (Object.values(photoIds).some(values => values[key] === value)) return true;
          return ++untagged <= body.limit;
        });
      }
      return reply(history, photoIds, savedPhotoId);
    }
    for (const [id, values] of Object.entries(photoIds)) if (!Object.keys(values).length) delete photoIds[id];
    return reply(history, photoIds);
  },
};
const app = { registerExtension(value) { extension = value; } };

class PreviewNode {
  constructor() {
    this.widgets = [];
    this.size = [430, 760];
  }
  onNodeCreated() {
    for (const [key] of fields) {
      const textarea = document.createElement('textarea');
      const widget = { name: key, element: textarea, callback: () => {} };
      Object.defineProperty(widget, 'value', {
        get: () => textarea.value,
        set: value => { textarea.value = value; },
      });
      this.widgets.push(widget, { name: `use_${key}`, value: true });
    }
    this.widgets.push({ name: 'history_limit', value: 100 });
    this.widgets.push({ name: 'photo_id', value: '' });
  }
  addWidget(type, name, value, callback, options = {}) {
    const widget = { type, name, value, callback, options };
    this.widgets.push(widget);
    return widget;
  }
  addDOMWidget(name, type, element, options = {}) {
    const widget = { name, type, element, options };
    this.widgets.push(widget);
    return widget;
  }
  computeSize() { return this.size; }
  setSize(size) { this.size = size; }
  setDirtyCanvas() {}
}

async function main() {
  const response = await fetch('../web/photo_prompt_builder.js');
  if (!response.ok) throw new Error(`Cannot load frontend script: HTTP ${response.status}`);
  const source = await response.text();
  const imports = source.match(/^import .*;\r?$/gm) || [];
  if (imports.length !== 2) throw new Error('Frontend imports changed; update the preview adapter.');
  const adapted = `const app = globalThis.__previewApp; const api = globalThis.__previewApi;\n${source.replace(/^import .*;\r?\n/gm, '')}`;
  globalThis.__previewApp = app;
  globalThis.__previewApi = api;
  const url = URL.createObjectURL(new Blob([adapted], { type: 'text/javascript' }));
  try { await import(url); }
  finally { URL.revokeObjectURL(url); delete globalThis.__previewApp; delete globalThis.__previewApi; }
  await extension.beforeRegisterNodeDef(PreviewNode, { name: 'MagichanLab_Krea2PhotoPromptBuilder' });
  const node = new PreviewNode();
  node.onNodeCreated();
  for (const [key, label] of fields) {
    const field = document.createElement('div');
    field.className = 'field';
    const title = document.createElement('label');
    title.textContent = label;
    const editor = document.createElement('div');
    editor.className = 'editor';
    editor.append(node.widgets.find(widget => widget.name === key).element);
    field.append(title, editor);
    nodeElement.append(field);
  }
  for (const control of node.widgets.filter(item => item.name.startsWith('Photo ID '))) {
    control.element.classList.add('photo-controls');
    nodeElement.append(control.element);
  }
  status.textContent = 'Enter values and save to create a Photo ID. Select it from the dropdown to restore them.';
}

main().catch(error => {
  status.className = 'error';
  status.textContent = error.message;
});
