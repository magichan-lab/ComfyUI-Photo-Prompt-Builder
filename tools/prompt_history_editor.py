"""Standalone tkinter editor for this node's local SQLite prompt history."""

import argparse
import re
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

try:
    from tkinterdnd2 import COPY, DND_TEXT, REFUSE_DROP, TkinterDnD
except ImportError:
    COPY = DND_TEXT = REFUSE_DROP = None
    TkRoot = tk.Tk
else:
    TkRoot = TkinterDnD.Tk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import history  # noqa: E402  (standalone script beside the node package)


def database_from_args(argv=None):
    parser = argparse.ArgumentParser(description='Edit a local Photo Prompt history database.')
    parser.add_argument('database', nargs='?', type=Path,
                        help='Existing SQLite database file (default: data/prompt_history.sqlite3)')
    parser.add_argument('-d', '--database', dest='database_option', metavar='PATH', type=Path,
                        help='Existing SQLite database file')
    args = parser.parse_args(argv)
    if args.database is not None and args.database_option is not None:
        parser.error('Specify the database path only once')
    selected = args.database_option or args.database
    if selected is None:
        return history.DB_FILE
    path = selected.expanduser().resolve()
    if not path.is_file():
        parser.error(f'Database file does not exist: {selected}')
    return path


HEADINGS = {
    'subject': 'Subject',
    'appearance': 'Clothing',
    'hair_makeup': 'Hair & Makeup',
    'pose': 'Posing',
    'expression': 'Expression',
    'environment': 'Environment',
    'composition': 'Composition & Camera',
    'lighting': 'Lighting',
    'finishing': 'Finishing',
}
TAG_FIELDS = {label.casefold(): field for field, label in HEADINGS.items()}
TAG_LINE = re.compile(r'^([^\s:][^:\r\n]{0,79}):[ \t]*(.*)$')


def parse_tagged_prompt(text):
    """Return recognized sections, or None when no prompt heading is present."""
    if not isinstance(text, str):
        return None
    sections = {field: [] for field in history.FIELDS}
    current = None
    found = False
    for line in text.splitlines():
        match = TAG_LINE.match(line.lstrip())
        name = match.group(1).strip() if match else ''
        body = match.group(2) if match else ''
        # Ratios such as "Horizontal 3:2" are prompt text, not a new tag.
        looks_like_ratio = name[-1:].isdigit() and body[:1].isdigit()
        if match and not looks_like_ratio:
            current = TAG_FIELDS.get(name.casefold())
            if current is not None:
                found = True
                sections[current].append(body)
        elif current is not None:
            sections[current].append(line)
    if not found:
        return None
    return {field: '\n'.join(lines).strip() for field, lines in sections.items()}


def compose_prompt(values, enabled):
    """Match the builder node's heading, field order and whitespace rules."""
    return '\n\n'.join(
        f'{HEADINGS[field]}:\n{values[field].strip()}'
        for field in history.FIELDS
        if enabled[field] and values[field].strip()
    )


def set_text(widget, value):
    widget.delete('1.0', 'end')
    widget.insert('1.0', value)


class HistoryDialog(tk.Toplevel):
    def __init__(self, app, field):
        super().__init__(app)
        self.app = app
        self.field = field
        self.before = None
        self.previous = []
        self.items = []
        self.title(f'{HEADINGS[field]} - History')
        self.geometry('720x570')
        self.transient(app)

        ttk.Label(self, text='[ID] With Photo ID   [--] Without Photo ID').pack(anchor='w', padx=12, pady=(12, 4))
        frame = ttk.Frame(self)
        frame.pack(fill='both', expand=True, padx=12)
        self.listbox = tk.Listbox(frame, exportselection=False)
        scroll = ttk.Scrollbar(frame, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.listbox.bind('<<ListboxSelect>>', self.show_selection)
        self.listbox.bind('<Double-Button-1>', lambda _event: self.use_selected())

        ttk.Label(self, text='Selected entry (full text)').pack(anchor='w', padx=12, pady=(8, 2))
        self.detail = tk.Text(self, height=6, wrap='word', state='disabled')
        self.detail.pack(fill='x', padx=12)
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=12, pady=12)
        self.prev_button = ttk.Button(bar, text='Previous 100', command=self.prev_page)
        self.prev_button.pack(side='left')
        self.next_button = ttk.Button(bar, text='Next 100', command=self.next_page)
        self.next_button.pack(side='left', padx=(4, 12))
        ttk.Button(bar, text='Use Selected', command=self.use_selected).pack(side='left')
        ttk.Button(bar, text='Edit Text', command=self.edit_selected).pack(side='left', padx=4)
        ttk.Button(bar, text='Delete Selected', command=self.delete_selected).pack(side='left')
        ttk.Button(bar, text='Clear All', command=self.clear_all).pack(side='left', padx=4)
        self.load_page()

    def selected(self):
        indices = self.listbox.curselection()
        return self.items[indices[0]] if indices else None

    def load_page(self):
        try:
            page = history.read_history_page(self.field, self.before)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Load History', str(exc), parent=self)
            return
        self.items = page['items']
        self.next_cursor = page['next_cursor']
        self.listbox.delete(0, 'end')
        for value, assigned in zip(self.items, page['has_photo_id']):
            short = ' '.join(value.split())[:140]
            self.listbox.insert('end', f'{"[ID]" if assigned else "[--]"} {short}')
        self.prev_button.configure(state='normal' if self.previous else 'disabled')
        self.next_button.configure(state='normal' if self.next_cursor is not None else 'disabled')
        if self.items:
            self.listbox.selection_set(0)
        self.show_selection()

    def show_selection(self, _event=None):
        self.detail.configure(state='normal')
        set_text(self.detail, self.selected() or '')
        self.detail.configure(state='disabled')

    def prev_page(self):
        if self.previous:
            self.before = self.previous.pop()
            self.load_page()

    def next_page(self):
        if self.next_cursor is not None:
            self.previous.append(self.before)
            self.before = self.next_cursor
            self.load_page()

    def use_selected(self):
        value = self.selected()
        if value is not None:
            self.app.set_field(self.field, value, True)
            self.destroy()

    def edit_selected(self):
        old = self.selected()
        if old is None:
            return
        dialog = tk.Toplevel(self)
        dialog.title(f'{HEADINGS[self.field]} - Edit Text')
        dialog.geometry('640x320')
        dialog.transient(self)
        dialog.grab_set()
        editor = tk.Text(dialog, wrap='word')
        editor.pack(fill='both', expand=True, padx=12, pady=12)
        set_text(editor, old)
        editor.focus_set()

        def save():
            new = editor.get('1.0', 'end-1c')
            try:
                history.update_entry(self.field, old, new, include_history=False)
            except (ValueError, RuntimeError, OSError) as exc:
                messagebox.showerror('Cannot Edit Entry', str(exc), parent=dialog)
                return
            if self.app.get_field(self.field) == old:
                self.app.set_field(self.field, new.strip(), self.app.enabled[self.field].get())
            self.app.refresh_photo_ids()
            self.app.status.set('History entry updated')
            dialog.destroy()
            self.before = None
            self.previous.clear()
            self.load_page()

        ttk.Button(dialog, text='Save', command=save).pack(pady=(0, 12))

    def delete_selected(self):
        value = self.selected()
        if value is None or not messagebox.askyesno(
                'Delete History Entry',
                'Delete the selected history entry?\nIt will also be removed from associated Photo IDs.',
                parent=self):
            return
        try:
            history.delete_entry(self.field, value, include_history=False)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Delete Entry', str(exc), parent=self)
            return
        self.app.refresh_photo_ids()
        self.app.status.set('History entry deleted')
        self.before = None
        self.previous.clear()
        self.load_page()

    def clear_all(self):
        if not messagebox.askyesno(
                'Clear Field History',
                f'Delete all {HEADINGS[self.field]} history entries?\n'
                'They will also be removed from associated Photo IDs.',
                parent=self):
            return
        try:
            history.clear_field(self.field, include_history=False)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Clear History', str(exc), parent=self)
            return
        self.app.refresh_photo_ids()
        self.app.status.set('Field history cleared')
        self.before = None
        self.previous.clear()
        self.load_page()


class Editor(TkRoot):
    def __init__(self):
        super().__init__()
        self.title('Photo Prompt History Editor')
        self.geometry('1040x760')
        self.minsize(800, 540)
        self.photo_ids = []
        self.selected_photo_id = None
        self.status = tk.StringVar(value=str(history.DB_FILE))
        self.search = tk.StringVar()
        self.photo_id = tk.StringVar()
        self.fields = {}
        self.enabled = {}

        pane = ttk.PanedWindow(self, orient='horizontal')
        pane.pack(fill='both', expand=True, padx=10, pady=10)
        left = ttk.Frame(pane, width=230)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=4)

        ttk.Label(left, text='Photo ID').pack(anchor='w')
        ttk.Entry(left, textvariable=self.search).pack(fill='x', pady=(4, 6))
        self.search.trace_add('write', lambda *_: self.filter_ids())
        list_frame = ttk.Frame(left)
        list_frame.pack(fill='both', expand=True)
        self.id_list = tk.Listbox(list_frame, exportselection=False)
        id_scroll = ttk.Scrollbar(list_frame, command=self.id_list.yview)
        self.id_list.configure(yscrollcommand=id_scroll.set)
        self.id_list.pack(side='left', fill='both', expand=True)
        id_scroll.pack(side='right', fill='y')
        self.id_list.bind('<<ListboxSelect>>', self.select_photo_id)
        ttk.Button(left, text='Refresh List', command=self.refresh_photo_ids).pack(fill='x', pady=(8, 2))
        ttk.Button(left, text='Rename Selected ID', command=self.rename_photo_id).pack(fill='x', pady=2)
        ttk.Button(left, text='Delete Selected ID', command=self.delete_photo_id).pack(fill='x', pady=2)

        top = ttk.Frame(right)
        top.pack(fill='x', padx=(10, 0))
        ttk.Label(top, text='Photo ID to Save').pack(side='left')
        ttk.Entry(top, textvariable=self.photo_id, width=28).pack(side='left', padx=6)
        ttk.Button(top, text='Save History', command=self.save).pack(side='left')
        ttk.Button(top, text='Preview Prompt', command=self.preview).pack(side='left', padx=6)

        drop_bar = ttk.Frame(right)
        drop_bar.pack(fill='x', padx=(10, 0), pady=(8, 0))
        hint = ('Drop tagged prompt text anywhere on this pane'
                if DND_TEXT else 'Install tkinterdnd2 to enable text drop')
        ttk.Label(drop_bar, text=hint).pack(side='left')
        ttk.Button(drop_bar, text='Paste Tagged Prompt', command=self.paste_tagged_prompt).pack(side='right')

        canvas = tk.Canvas(right, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True, padx=(10, 0), pady=(8, 0))
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(window, width=event.width))

        for field in history.FIELDS:
            row = ttk.Frame(body)
            row.pack(fill='x', pady=5)
            self.enabled[field] = tk.BooleanVar(value=True)
            ttk.Checkbutton(row, text=HEADINGS[field], variable=self.enabled[field]).pack(side='left')
            ttk.Button(row, text='History', command=lambda f=field: HistoryDialog(self, f)).pack(side='right')
            widget = tk.Text(body, height=4, wrap='word', undo=True)
            widget.pack(fill='x')
            self.fields[field] = widget

        ttk.Label(self, textvariable=self.status, anchor='w').pack(fill='x', padx=10, pady=(0, 8))
        if DND_TEXT:
            self.register_drop_targets(right)
        self.refresh_photo_ids()

    def register_drop_targets(self, widget):
        widget.drop_target_register(DND_TEXT)
        widget.dnd_bind('<<Drop>>', self.on_text_drop)
        for child in widget.winfo_children():
            self.register_drop_targets(child)

    def apply_tagged_prompt(self, text):
        values = parse_tagged_prompt(text)
        if values is None:
            self.status.set('No recognized prompt tags found; input was not changed')
            return False
        for field in history.FIELDS:
            self.set_field(field, values[field], bool(values[field]))
        self.status.set('Tagged prompt loaded into the editor')
        return True

    def on_text_drop(self, event):
        return COPY if self.apply_tagged_prompt(event.data) else REFUSE_DROP

    def paste_tagged_prompt(self):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            self.status.set('Clipboard does not contain text')
            return
        self.apply_tagged_prompt(text)

    def get_field(self, field):
        return self.fields[field].get('1.0', 'end-1c')

    def set_field(self, field, value, enabled):
        set_text(self.fields[field], value)
        self.enabled[field].set(enabled)

    def filter_ids(self):
        query = self.search.get().casefold()
        self.visible_ids = [item for item in self.photo_ids if query in item.casefold()]
        self.id_list.delete(0, 'end')
        for item in self.visible_ids:
            self.id_list.insert('end', item)
        if self.selected_photo_id in self.visible_ids:
            index = self.visible_ids.index(self.selected_photo_id)
            self.id_list.selection_set(index)
            self.id_list.see(index)

    def refresh_photo_ids(self):
        try:
            self.photo_ids = history.list_photo_ids()
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Load Database', str(exc), parent=self)
            return
        if self.selected_photo_id not in self.photo_ids:
            if self.photo_id.get() == self.selected_photo_id:
                self.photo_id.set('')
            self.selected_photo_id = None
        self.filter_ids()

    def select_photo_id(self, _event=None):
        indices = self.id_list.curselection()
        if not indices:
            return
        photo_id = self.visible_ids[indices[0]]
        if photo_id == self.selected_photo_id:
            return
        try:
            values = history.read_photo_id(photo_id)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Load Photo ID', str(exc), parent=self)
            return
        if values is None:
            self.refresh_photo_ids()
            return
        self.selected_photo_id = photo_id
        self.photo_id.set(photo_id)
        for field in history.FIELDS:
            value = values.get(field, '')
            self.set_field(field, value, bool(value))
        self.status.set(f'Photo ID: {photo_id}')

    def save(self):
        values = {field: self.get_field(field) for field in history.FIELDS}
        enabled = {field: self.enabled[field].get() for field in history.FIELDS}
        photo_id = self.photo_id.get().strip()
        try:
            result = history.add_entries(values, photo_id=photo_id, enabled=enabled,
                                         include_history=False)
        except history.PhotoIdConflict as exc:
            names = ', '.join(HEADINGS[field] for field in exc.fields)
            if not messagebox.askyesno('Overwrite Photo ID',
                    f'Photo ID "{exc.photo_id}" has different text in:\n{names}\nOverwrite its assignments?',
                    parent=self):
                return
            try:
                result = history.add_entries(values, photo_id=photo_id, enabled=enabled,
                                             overwrite=True, include_history=False)
            except (ValueError, RuntimeError, OSError) as error:
                messagebox.showerror('Cannot Save History', str(error), parent=self)
                return
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Save History', str(exc), parent=self)
            return
        self.selected_photo_id = result['saved_photo_id']
        self.photo_id.set(self.selected_photo_id)
        self.refresh_photo_ids()
        self.status.set(f'Saved Photo ID: {self.selected_photo_id}')

    def preview(self):
        values = {field: self.get_field(field) for field in history.FIELDS}
        enabled = {field: self.enabled[field].get() for field in history.FIELDS}
        dialog = tk.Toplevel(self)
        dialog.title('Combined Prompt Preview')
        dialog.geometry('700x560')
        dialog.transient(self)
        text = tk.Text(dialog, wrap='word')
        text.pack(fill='both', expand=True, padx=12, pady=12)
        set_text(text, compose_prompt(values, enabled))
        text.configure(state='disabled')

        def copy():
            self.clipboard_clear()
            self.clipboard_append(compose_prompt(values, enabled))
            self.status.set('Combined prompt copied')

        ttk.Button(dialog, text='Copy', command=copy).pack(pady=(0, 12))

    def rename_photo_id(self):
        old = self.selected_photo_id
        if old is None:
            messagebox.showinfo('Photo ID', 'Select a Photo ID from the list.', parent=self)
            return
        new = simpledialog.askstring('Rename Photo ID', 'New Photo ID:',
                                     initialvalue=old, parent=self)
        if new is None:
            return
        try:
            history.rename_photo_id(old, new, include_history=False)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Rename Photo ID', str(exc), parent=self)
            return
        self.selected_photo_id = new
        self.photo_id.set(new)
        self.refresh_photo_ids()
        self.status.set(f'Photo ID renamed to {new}')

    def delete_photo_id(self):
        photo_id = self.selected_photo_id
        if photo_id is None:
            messagebox.showinfo('Photo ID', 'Select a Photo ID from the list.', parent=self)
            return
        if not messagebox.askyesno('Delete Photo ID',
                f'Delete Photo ID "{photo_id}" from all fields?\nText history will remain.', parent=self):
            return
        try:
            history.delete_photo_id(photo_id, include_history=False)
        except (ValueError, RuntimeError, OSError) as exc:
            messagebox.showerror('Cannot Delete Photo ID', str(exc), parent=self)
            return
        self.selected_photo_id = None
        self.photo_id.set('')
        self.refresh_photo_ids()
        self.status.set(f'Photo ID "{photo_id}" deleted')


def main(argv=None):
    history.DB_FILE = database_from_args(argv)
    Editor().mainloop()


if __name__ == '__main__':
    main()
