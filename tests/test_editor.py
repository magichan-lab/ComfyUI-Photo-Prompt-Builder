"""Tagged prompt parsing and application without opening a GUI or database."""

import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch


EDITOR = Path(__file__).resolve().parents[1] / 'tools' / 'prompt_history_editor.py'
spec = importlib.util.spec_from_file_location('prompt_history_editor', EDITOR)
editor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(editor)


class TestTaggedPrompt(unittest.TestCase):
    def test_round_trip_combined_prompt(self):
        values = {field: f'{field} first line\nsecond line' for field in editor.history.FIELDS}
        combined = editor.compose_prompt(values, {field: True for field in editor.history.FIELDS})
        self.assertEqual(editor.parse_tagged_prompt(combined), values)

    def test_known_tags_multiline_unknown_tags_and_missing_fields(self):
        result = editor.parse_tagged_prompt(
            'Preamble ignored\r\n'
            'subject: Portrait of a person\r\nwith a hat\r\n\r\n'
            'Custom Tag: Ignore this\r\nand this\r\n'
            'Lighting:\r\nSoft window light\r\n'
        )
        self.assertEqual(result['subject'], 'Portrait of a person\nwith a hat')
        self.assertEqual(result['lighting'], 'Soft window light')
        self.assertTrue(all(result[field] == '' for field in editor.history.FIELDS
                            if field not in ('subject', 'lighting')))

    def test_duplicate_known_tag_combines_text(self):
        result = editor.parse_tagged_prompt('Subject: First\nSubject: Second')
        self.assertEqual(result['subject'], 'First\nSecond')

    def test_camera_aspect_ratio_stays_in_composition(self):
        result = editor.parse_tagged_prompt(
            'Composition & Camera:\n'
            'Horizontal 3:2 medium-close portrait, subject placed slightly right of center, '
            'framed from chest to above head\n\n'
            'Lighting:\nSoft overcast winter daylight\n'
        )
        self.assertEqual(result['composition'],
                         'Horizontal 3:2 medium-close portrait, subject placed slightly right '
                         'of center, framed from chest to above head')
        self.assertEqual(result['lighting'], 'Soft overcast winter daylight')

    def test_non_tagged_text_does_not_change_inputs(self):
        class FakeStatus:
            def set(self, value):
                self.value = value

        class FakeEditor:
            status = FakeStatus()

            def __init__(self):
                self.values = {field: ('old', True) for field in editor.history.FIELDS}

            def set_field(self, field, value, enabled):
                self.values[field] = value, enabled

        app = FakeEditor()
        self.assertFalse(editor.Editor.apply_tagged_prompt(app, 'Plain prompt text'))
        self.assertTrue(all(value == ('old', True) for value in app.values.values()))
        self.assertTrue(editor.Editor.apply_tagged_prompt(app, 'Subject:\nNew text\nOther: ignored'))
        self.assertEqual(app.values['subject'], ('New text', True))
        self.assertEqual(app.values['lighting'], ('', False))


class TestDatabaseArgument(unittest.TestCase):
    def test_default_and_explicit_database_paths(self):
        self.assertEqual(editor.database_from_args([]), editor.history.DB_FILE)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'alternate.sqlite3'
            path.touch()
            self.assertEqual(editor.database_from_args([str(path)]), path.resolve())
            self.assertEqual(editor.database_from_args(['--database', str(path)]), path.resolve())
            self.assertEqual(editor.database_from_args(['-d', str(path)]), path.resolve())

    def test_missing_database_is_rejected_before_gui_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / 'missing.sqlite3')
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                editor.database_from_args(['--database', missing])
            self.assertEqual(raised.exception.code, 2)

    def test_main_sets_database_before_creating_editor(self):
        original = editor.history.DB_FILE
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'alternate.sqlite3'
            path.touch()
            try:
                with patch.object(editor, 'Editor') as editor_class:
                    editor.main([str(path)])
                    editor_class.assert_called_once_with()
                    editor_class.return_value.mainloop.assert_called_once_with()
                    self.assertEqual(editor.history.DB_FILE, path.resolve())
            finally:
                editor.history.DB_FILE = original


if __name__ == '__main__':
    unittest.main()
