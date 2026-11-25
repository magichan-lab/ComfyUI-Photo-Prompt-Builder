import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

class Element {
  constructor() {
    this.style = {};
    this.listeners = {};
  }
  append(...children) { this.children = children; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
}

let extension;
let refreshes = 0;
const context = vm.createContext({
  document: { createElement: () => new Element() },
  window: { dispatchEvent: () => { refreshes++; } },
  Event: class {},
  app: { registerExtension: value => { extension = value; } },
  api: { fetchApi: async () => ({
    ok: true, json: async () => ({ saved_photo_id: 'photo-1' }),
  }) },
});
const source = await readFile(new URL('../web/image_to_text_save.js', import.meta.url), 'utf8');
vm.runInContext(source.replace(/^import .*;\r?\n/gm, ''), context);

class ImageToTextNode {
  constructor() { this.size = [410, 500]; }
  addDOMWidget(name, type, element, options) {
    this.widget = { name, type, element, options, width: 140 };
    return this.widget;
  }
  computeSize() { return [360, 430]; }
  setSize(size) { this.size = size; }
}
extension.beforeRegisterNodeDef(ImageToTextNode, {
  name: 'MagichanLab_Krea2ImageToTextSave',
});
const node = new ImageToTextNode();
node.onNodeCreated();
assert.equal(node.widget.width, 410);
assert.equal(node.widget.element.style.width, '100%');

node.onExecuted({ image_to_text: [{
  entries: { subject: 'Portrait' }, photo_id: 'photo-1', overwrite: false, saved: false,
}] });
node.imageToTextControls.button.listeners.click();
await new Promise(resolve => setImmediate(resolve));
assert.equal(node.imageToTextControls.status.textContent, 'Saved: photo-1');
assert.equal(refreshes, 1);

for (const width of [410, 600, 360]) {
  node.size[0] = width;
  for (const callback of ['onDraw', 'afterResize']) {
    node.widget.width = 140; // Simulate ComfyUI retaining an old layout width.
    node.widget.options[callback](node.widget);
    assert.equal(node.widget.width, width);
  }
}
console.log('PASS: Image to Text controls retain node width after Save and resize');
