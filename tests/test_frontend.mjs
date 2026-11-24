// Exercise the actual extension with a minimal DOM/ComfyUI adapter.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

class Element {
  constructor(tag) {
    this.tag = tag;
    this.style = {};
    this.value = '';
    this.children = [];
    this.listeners = {};
  }
  append(...children) {
    children.forEach(child => { child.parent = this; });
    this.children.push(...children);
  }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { this.parent.children = this.parent.children.filter(child => child !== this); }
  setAttribute() {}
  addEventListener(name, callback) { this.listeners[name] = callback; }
}
const body = new Element('body');
const calls = [];
const events = new Map();
let thumbnailAttempts = 0;
const entries = Array.from({ length: 205 }, (_, i) => `Entry ${i}`);
let extension;
const context = vm.createContext({
  URLSearchParams,
  setTimeout,
  HTMLTextAreaElement: class {},
  document: { body, createElement: tag => new Element(tag) },
  window: { confirm: () => true },
  app: { registerExtension(value) { extension = value; } },
  api: { addEventListener(name, callback) { events.set(name, callback); }, async fetchApi(path, options) {
    calls.push({ path, options });
    if (path.endsWith('/generation_thumbnail')) {
      thumbnailAttempts++;
      return thumbnailAttempts === 1
        ? { status: 202, ok: true }
        : { status: 200, ok: true, json: async () => ({ saved_photo_ids: ['photo-1'] }) };
    }
    const query = new URL(path, 'http://localhost').searchParams;
    if (query.has('field')) {
      const start = Number(query.get('before') || 0);
      return { ok: true, json: async () => ({
        items: entries.slice(start, start + 100),
        has_photo_id: entries.slice(start, start + 100).map((_, i) => (start + i) % 2 === 0),
        next_cursor: start + 100 < entries.length ? start + 100 : null,
      }) };
    }
    return { ok: true, json: async () => ({ photo_ids: {}, saved_photo_id: 'photo-1' }) };
  } },
});
const source = await readFile(new URL('../web/photo_prompt_builder.js', import.meta.url), 'utf8');
vm.runInContext(source.replace(/^import .*;\r?\n/gm, ''), context);
extension.setup();
const { openHistory, saveCurrent, fields } = vm.runInContext('({openHistory, saveCurrent, fields: FIELDS})', context);
class Builder {
  constructor() {
    this.widgets = fields.flatMap(([name]) => [{ name, value: '' }, { name: `use_${name}`, value: true }]);
    this.widgets.push({ name: 'auto_save_history', value: true }, { name: 'photo_id', value: '' });
    this.size = [430, 760];
  }
  addDOMWidget(name, type, element, options) {
    const widget = { name, type, element, options };
    this.widgets.push(widget);
    return widget;
  }
  computeSize() { return this.size; }
  setSize(size) { this.size = size; }
}
await extension.beforeRegisterNodeDef(Builder, { name: 'MagichanLab_Krea2PhotoPromptBuilder' });
const node = new Builder();
node.onNodeCreated();
const photoWidget = node.widgets.find(widget => widget.name === 'photo_id');
const oldValues = fields.flatMap(() => ['', true]);
oldValues.push(true, 100, 'legacy-photo');
photoWidget.value = 100; // Value assigned by the old positional serialization.
node.onConfigure({ widgets_values: oldValues });
assert.equal(photoWidget.value, 'legacy-photo');
assert.equal(node.photoControls.input.value, 'legacy-photo');
assert.equal(oldValues[19], 'legacy-photo');
const currentValues = fields.flatMap(() => ['', true]);
currentValues.push(true, '123');
photoWidget.value = '123';
node.onConfigure({ widgets_values: currentValues });
assert.equal(photoWidget.value, '123');
assert.equal(currentValues.length, 20);
assert.ok(calls[0].path.endsWith('?include_history=0'));
console.log('PASS: legacy workflow Photo ID restoration and current serialization');

function actions() { return body.children.at(-1).children[0].children[2].children; }
async function click(label) {
  const button = actions().find(child => child.textContent === label);
  assert.ok(button, `Missing ${label}`);
  await button.listeners.click();
  await new Promise(resolve => setImmediate(resolve));
}
await openHistory(node, 'subject', 'Subject');
const historyContent = body.children.at(-1).children[0].children[1];
assert.ok(historyContent.children[0].children[0].textContent.includes('With Photo ID'));
const historyRows = historyContent.children[1].children;
assert.notEqual(historyRows[0].style.color, historyRows[1].style.color);
assert.ok(historyRows[0].title.startsWith('Photo IDあり'));
assert.ok(historyRows[1].title.startsWith('Photo IDなし'));
const assignedColor = historyRows[0].style.color;
const assignedBorder = historyRows[0].style.borderLeft;
await historyRows[1].listeners.click();
assert.equal(historyRows[0].style.color, assignedColor);
assert.equal(historyRows[0].style.borderLeft, assignedBorder);
assert.notEqual(historyRows[0].style.background, historyRows[1].style.background);
assert.equal(historyContent.children[2].textContent, 'Entry 1');
console.log('PASS: Photo ID status colors, legend and selection preview');
assert.ok(!actions().some(child => child.textContent === 'Previous page'));
await click('Next page');
assert.ok(calls.at(-1).path.includes('before=100'));
await click('Next page');
assert.ok(calls.at(-1).path.includes('before=200'));
assert.ok(!actions().some(child => child.textContent === 'Next page'));
await click('Use selected');
assert.equal(node.widgets[0].value, 'Entry 200');
await openHistory(node, 'subject', 'Subject');
await click('Next page');
await click('Previous page');
assert.ok(!calls.at(-1).path.includes('before='));
await click('Delete selected');
const deletion = calls.find(call => call.path.endsWith('/delete'));
assert.deepEqual(JSON.parse(deletion.options.body), { field: 'subject', value: 'Entry 0' });
console.log('PASS: history page navigation, selection and deletion');

photoWidget.value = 'photo-1';
await saveCurrent(node);
const save = calls.findLast(call => call.path.endsWith('/history') && call.options);
assert.ok(save);
assert.ok(!Object.hasOwn(JSON.parse(save.options.body), 'limit'));
assert.equal(JSON.parse(save.options.body).entries.subject, 'Entry 200');
console.log('PASS: save payload omits the removed retention limit');

photoWidget.value = '';
await saveCurrent(node);
assert.equal(photoWidget.value, 'photo-1');
events.get('execution_success')({ detail: { prompt_id: 'completed-prompt' } });
await new Promise(resolve => setTimeout(resolve, 300));
const thumbnail = calls.find(call => call.path.endsWith('/generation_thumbnail'));
assert.deepEqual(JSON.parse(thumbnail.options.body), { prompt_id: 'completed-prompt' });
assert.equal(thumbnailAttempts, 2);
console.log('PASS: completed prompt triggers thumbnail save with its prompt ID');
