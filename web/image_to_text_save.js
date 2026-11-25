import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

const NODE_TYPE = 'MagichanLab_Krea2ImageToTextSave';
const PATH = '/magichanlab_photo_prompt/history';
const LABELS = [
  ['subject', 'Subject'], ['appearance', 'Clothing'],
  ['hair_makeup', 'Hair & Makeup'], ['pose', 'Posing'],
  ['expression', 'Expression'], ['environment', 'Environment'],
  ['composition', 'Composition & Camera'], ['lighting', 'Lighting'],
  ['finishing', 'Finishing'],
];

function describe(entries) {
  return LABELS.filter(([field]) => entries[field])
    .map(([field, label]) => `${label}:\n${entries[field]}`).join('\n\n');
}

function refreshPhotoIds() {
  window.dispatchEvent(new Event('magichanlab-photo-ids-changed'));
}

async function save(node) {
  const pending = node.imageToTextPending;
  if (!pending || pending.saved) return;
  const button = node.imageToTextControls.button;
  button.disabled = true;
  try {
    let response = await api.fetchApi(PATH, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries: pending.entries, photo_id: pending.photo_id,
                             overwrite: pending.overwrite }),
    });
    if (response.status === 409 && !pending.overwrite) {
      if (!window.confirm(`Photo ID "${pending.photo_id}" already contains different text. Overwrite it?`)) {
        button.disabled = false;
        return;
      }
      response = await api.fetchApi(PATH, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries: pending.entries, photo_id: pending.photo_id,
                               overwrite: true }),
      });
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
    pending.saved = true;
    node.imageToTextControls.status.textContent = `Saved: ${result.saved_photo_id}`;
    refreshPhotoIds();
  } catch (error) {
    node.imageToTextControls.status.textContent = `Save failed: ${error.message}`;
    button.disabled = false;
  }
}

app.registerExtension({
  name: 'MagichanLab_image_to_text_save',
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;
    const oldCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const result = oldCreated?.apply(this, args);
      const container = document.createElement('div');
      Object.assign(container.style, {
        display: 'flex', flexDirection: 'column', gap: '6px', width: '100%', height: '100%',
        boxSizing: 'border-box', padding: '5px',
      });
      const status = document.createElement('div');
      status.textContent = 'Run the workflow to inspect the tags.';
      const preview = document.createElement('textarea');
      preview.readOnly = true;
      preview.placeholder = 'Validated tags will appear here.';
      Object.assign(preview.style, {
        width: '100%', flex: '1', boxSizing: 'border-box', resize: 'none',
        color: '#eee', background: '#17191c', border: '1px solid #666',
      });
      const button = document.createElement('button');
      button.textContent = 'Save';
      button.disabled = true;
      button.addEventListener('click', () => void save(this));
      container.append(status, preview, button);
      const ui = this.addDOMWidget('Image to Text result', 'image_to_text_result', container, {
        serialize: false, hideOnZoom: false,
        getMinHeight: () => 250, getHeight: () => 250,
      });
      ui.serialize = false;
      // ComfyUI may reuse a stale widget width when redrawing after Save.
      // Its DOM wrapper reads this value before falling back to the node width.
      const syncWidth = () => { ui.width = this.size[0]; };
      ui.options ??= {};
      for (const name of ['onDraw', 'afterResize']) {
        const previous = ui.options[name];
        ui.options[name] = function (...callbackArgs) {
          const callbackResult = previous?.apply(this, callbackArgs);
          syncWidth();
          return callbackResult;
        };
      }
      this.imageToTextControls = { status, preview, button };
      this.imageToTextPending = null;
      const oldExecuted = this.onExecuted;
      this.onExecuted = function (message) {
        const executed = oldExecuted?.call(this, message);
        const payload = message?.image_to_text?.[0];
        if (!payload || !payload.entries) return executed;
        this.imageToTextPending = payload;
        preview.value = describe(payload.entries);
        status.textContent = `${payload.saved ? 'Saved' : 'Ready to save'}: ${payload.photo_id}`;
        button.disabled = payload.saved;
        if (payload.saved) refreshPhotoIds();
        return executed;
      };
      const oldConfigure = this.onConfigure;
      this.onConfigure = function (...configureArgs) {
        const configured = oldConfigure?.apply(this, configureArgs);
        this.imageToTextPending = null;
        button.disabled = true;
        preview.value = '';
        status.textContent = 'Run the workflow to inspect the tags.';
        return configured;
      };
      const [width, height] = this.computeSize();
      this.setSize([Math.max(this.size[0], width, 360),
                    Math.max(this.size[1], height, 430)]);
      syncWidth();
      return result;
    };
  },
});
