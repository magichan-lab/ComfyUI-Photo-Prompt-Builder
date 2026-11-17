const fields = [
  ['subject', 'Subject'], ['appearance', 'Clothing'],
  ['hair_makeup', 'Hair & Makeup'], ['pose', 'Posing'],
  ['expression', 'Expression'], ['environment', 'Environment'],
  ['composition', 'Composition & Camera'], ['lighting', 'Lighting'],
  ['finishing', 'Finishing'],
];
const storageKey = 'photo-prompt-builder-preview-history';
const nodeElement = document.querySelector('#node');
const status = document.querySelector('#status');
let extension;

const emptyHistory = () => Object.fromEntries(fields.map(([key]) => [key, []]));
function readHistory() {
  try { return { ...emptyHistory(), ...JSON.parse(localStorage.getItem(storageKey) || '{}') }; }
  catch { return emptyHistory(); }
}
function reply(history) {
  localStorage.setItem(storageKey, JSON.stringify(history));
  return { ok: true, json: async () => ({ history }) };
}
const api = {
  async fetchApi(path, options) {
    const history = readHistory();
    if (!options) return reply(history);
    const body = JSON.parse(options.body);
    if (path.endsWith('/delete')) {
      history[body.field] = history[body.field].filter(value => value !== body.value);
    } else if (path.endsWith('/clear')) {
      history[body.field] = [];
    } else {
      for (const [key, raw] of Object.entries(body.entries)) {
        const value = raw.trim();
        if (value) history[key] = [value, ...history[key].filter(item => item !== value)].slice(0, body.limit);
      }
    }
    return reply(history);
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
  }
  addWidget(type, name, value, callback) {
    const widget = { type, name, value, callback };
    this.widgets.push(widget);
    return widget;
  }
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
  const controls = document.createElement('div');
  controls.className = 'controls';
  for (const widget of node.widgets.filter(widget => widget.type === 'button')) {
    const button = document.createElement('button');
    button.textContent = widget.name;
    button.addEventListener('click', widget.callback);
    controls.append(button);
  }
  nodeElement.append(controls);
  status.textContent = '履歴を試すには入力後に「Save current values to history」を押してください。';
}

main().catch(error => {
  status.className = 'error';
  status.textContent = error.message;
});
