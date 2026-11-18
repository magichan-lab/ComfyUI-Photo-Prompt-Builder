import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = load('independent_history', 'history.py')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = self.h.FILE
        self.h.FILE = Path(self.temp.name) / 'history.json'

    def tearDown(self):
        self.h.FILE = self.original
        self.temp.cleanup()

    def test_add_deduplicate_limit_delete(self):
        self.h.add_entries({'subject': 'A', 'appearance': 'White shirt'}, limit=2)
        self.h.add_entries({'subject': 'B'}, limit=2)
        self.h.add_entries({'subject': 'A'}, limit=2)
        self.assertEqual(self.h.read_history()['subject'], ['A', 'B'])
        self.assertEqual(self.h.read_history()['appearance'], ['White shirt'])
        self.h.delete_entry('subject', 'A')
        self.assertEqual(self.h.read_history()['subject'], ['B'])
        self.h.clear_field('subject')
        self.assertEqual(self.h.read_history()['subject'], [])

    def test_invalid_and_unicode(self):
        self.h.add_entries({'environment': '東京・夕暮れ'})
        self.assertIn('東京・夕暮れ', self.h.FILE.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            self.h.add_entries({'unknown': 'x'})
        with self.assertRaises(ValueError):
            self.h.add_entries({'subject': 'x'}, limit=0)

    def test_blank_ignored(self):
        self.h.add_entries({'subject': '  '})
        self.assertEqual(self.h.read_history()['subject'], [])

    def test_split_fields_have_independent_history(self):
        self.h.add_entries({
            'appearance': 'White shirt', 'hair_makeup': 'Short hair',
            'pose': 'Standing', 'expression': 'Smiling',
        })
        history = self.h.read_history()
        self.assertEqual(history['appearance'], ['White shirt'])
        self.assertEqual(history['hair_makeup'], ['Short hair'])
        self.assertEqual(history['pose'], ['Standing'])
        self.assertEqual(history['expression'], ['Smiling'])

    def test_existing_history_loads_with_new_fields(self):
        self.h.FILE.write_text('{"version": 1, "history": {"appearance": ["Old look"], "pose": ["Old pose"]}}', encoding='utf-8')
        history = self.h.read_history()
        self.assertEqual(history['appearance'], ['Old look'])
        self.assertEqual(history['pose'], ['Old pose'])
        self.assertEqual(history['hair_makeup'], [])
        self.assertEqual(history['expression'], [])

    def test_photo_id_reuses_text_and_restores_only_enabled_fields(self):
        self.h.add_entries({'subject': 'A', 'lighting': 'soft'}, photo_id='A-1',
                           enabled={'subject': True, 'lighting': False})
        self.h.add_entries({'subject': 'A', 'lighting': 'hard'}, photo_id='B-2')
        self.assertEqual(self.h.read_photo_ids()['A-1'], {'subject': 'A'})
        self.assertEqual(self.h.read_photo_ids()['B-2'],
                         {'subject': 'A', 'lighting': 'hard'})
        saved = self.h.FILE.read_text(encoding='utf-8')
        self.assertIn('"photo_ids": [', saved)
        self.assertIn('"A-1"', saved)
        self.assertIn('"B-2"', saved)

    def test_resaving_id_moves_association_and_deletion_updates_index(self):
        self.h.add_entries({'subject': 'Old', 'pose': 'Standing'}, photo_id='photo:1')
        with self.assertRaises(self.h.PhotoIdConflict) as raised:
            self.h.add_entries({'subject': 'New'}, photo_id='photo:1')
        self.assertEqual(raised.exception.fields, ['subject'])
        self.assertEqual(self.h.read_photo_ids()['photo:1'],
                         {'subject': 'Old', 'pose': 'Standing'})
        self.h.add_entries({'subject': 'New'}, photo_id='photo:1', overwrite=True)
        self.assertEqual(self.h.read_photo_ids()['photo:1'], {'subject': 'New'})
        self.h.delete_entry('subject', 'New')
        self.assertNotIn('photo:1', self.h.read_photo_ids())

    def test_same_text_and_new_field_do_not_require_confirmation(self):
        self.h.add_entries({'subject': 'Same'}, photo_id='shared')
        self.h.add_entries({'subject': 'Same', 'pose': 'Standing'}, photo_id='shared')
        self.assertEqual(self.h.read_photo_ids()['shared'],
                         {'subject': 'Same', 'pose': 'Standing'})

    def test_conflicts_report_all_changed_enabled_fields(self):
        self.h.add_entries({'subject': 'Old', 'pose': 'Old pose', 'lighting': 'Soft'},
                           photo_id='shared')
        with self.assertRaises(self.h.PhotoIdConflict) as raised:
            self.h.add_entries({'subject': 'New', 'pose': 'New pose', 'lighting': 'Hard'},
                               photo_id='shared', enabled={'lighting': False})
        self.assertEqual(raised.exception.fields, ['subject', 'pose'])
        self.assertEqual(self.h.read_photo_ids()['shared']['lighting'], 'Soft')

    def test_tagged_entries_survive_history_limit(self):
        self.h.add_entries({'subject': 'Pinned'}, photo_id='pin')
        self.h.add_entries({'subject': 'One'}, limit=1)
        self.h.add_entries({'subject': 'Two'}, limit=1)
        self.assertEqual(self.h.read_history()['subject'], ['Two', 'Pinned'])
        self.assertEqual(self.h.read_photo_ids()['pin'], {'subject': 'Pinned'})

    def test_auto_id_and_validation(self):
        result = self.h.add_entries({'subject': 'A'}, photo_id='')
        self.assertRegex(result['saved_photo_id'], r'^\d{12}$')
        for photo_id in ('a b', '日本語', 'a' * 25, 'bad&'):
            with self.subTest(photo_id=photo_id), self.assertRaises(ValueError):
                self.h.add_entries({'subject': 'B'}, photo_id=photo_id)
        self.assertEqual(self.h.read_history()['subject'], ['A'])
        self.h.add_entries({'subject': 'B'}, photo_id='a' * 24)
        with self.assertRaises(ValueError):
            self.h.add_entries({'subject': 'C'}, photo_id='unused', enabled={'subject': False})
        self.assertNotIn('C', self.h.read_history()['subject'])


class TestCompose(unittest.TestCase):
    def test_headings_blank_and_disabled(self):
        # Avoid importing ComfyUI's server (which isn't needed for node functionality).
        import sys
        import types
        from unittest.mock import patch
        package = types.ModuleType('testphoto')
        package.__path__ = [str(ROOT)]
        with patch.dict(sys.modules, {'testphoto': package, 'testphoto.history': load('history_for_node', 'history.py')}):
            spec = importlib.util.spec_from_file_location('testphoto.nodes', ROOT / 'nodes.py')
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        self.assertEqual(mod.NODE_ID, 'MagichanLab_Krea2PhotoPromptBuilder')
        self.assertEqual(mod.NODE_CLASS_MAPPINGS, {mod.NODE_ID: mod.Krea2PhotoPromptBuilder})
        self.assertEqual(mod.NODE_DISPLAY_NAME_MAPPINGS, {mod.NODE_ID: 'Krea2 Photo Prompt Builder'})
        output = mod.compose_prompt(
            {'subject': ' A woman ', 'appearance': 'black hair', 'lighting': '  '},
            {'subject': True, 'appearance': False})
        self.assertEqual(output, 'Subject:\nA woman')
        output2 = mod.compose_prompt({'subject': 'A woman', 'lighting': 'soft light'},
                                     {'subject': True, 'lighting': True})
        self.assertEqual(output2, 'Subject:\nA woman\n\nLighting:\nsoft light')
        split = mod.compose_prompt({
            'appearance': 'White shirt', 'hair_makeup': 'Short hair',
            'pose': 'Standing', 'expression': 'Smiling',
        }, {})
        self.assertEqual(split, 'Clothing:\nWhite shirt\n\nHair & Makeup:\nShort hair'
                         '\n\nPosing:\nStanding\n\nExpression:\nSmiling')
        inputs = mod.Krea2PhotoPromptBuilder.INPUT_TYPES()['required']
        for field in ('appearance', 'hair_makeup', 'pose', 'expression'):
            self.assertIn(field, inputs)
            self.assertIn(f'use_{field}', inputs)


if __name__ == '__main__':
    unittest.main()
