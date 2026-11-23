import copy
import importlib.util
import json
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
        self.original_template = self.h.TEMPLATE_FILE
        self.h.FILE = Path(self.temp.name) / 'history.json'
        self.h.TEMPLATE_FILE = Path(self.temp.name) / 'template.json'
        template = ROOT / 'data' / 'prompt_history_template.json'
        self.h.TEMPLATE_FILE.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')

    def tearDown(self):
        self.h.FILE = self.original
        self.h.TEMPLATE_FILE = self.original_template
        self.temp.cleanup()

    def test_missing_history_uses_template_then_saved_history(self):
        self.h.TEMPLATE_FILE.write_text(
            '{"version": 2, "history": {"subject": [{"text": "Default", "photo_ids": []}]}}',
            encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['Default'])
        self.assertFalse(self.h.FILE.exists())
        self.h.add_entries({'subject': 'Saved'})
        self.assertEqual(self.h.read_history()['subject'], ['Saved', 'Default'])
        self.h.TEMPLATE_FILE.write_text('{"version": 2, "history": {}}', encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['Saved', 'Default'])

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

    def test_rename_photo_id_updates_all_fields_without_changing_text(self):
        self.h.add_entries({'subject': 'Same', 'pose': 'Standing'}, photo_id='old')
        self.h.add_entries({'subject': 'Same'}, photo_id='other')
        original_history = self.h.read_history()
        result = self.h.rename_photo_id('old', 'new-1')
        self.assertEqual(result['history'], original_history)
        self.assertNotIn('old', result['photo_ids'])
        self.assertEqual(result['photo_ids']['new-1'],
                         {'subject': 'Same', 'pose': 'Standing'})
        self.assertEqual(result['photo_ids']['other'], {'subject': 'Same'})
        self.assertEqual(self.h.read_photo_ids(), result['photo_ids'])

    def test_rename_rejects_empty_duplicate_and_invalid_ids(self):
        self.h.add_entries({'subject': 'A'}, photo_id='old')
        self.h.add_entries({'pose': 'B'}, photo_id='taken')
        for new_id in ('', 'taken', 'bad id', 'old', 'a' * 25):
            with self.subTest(new_id=new_id), self.assertRaises(ValueError):
                self.h.rename_photo_id('old', new_id)
        with self.assertRaises(ValueError):
            self.h.rename_photo_id('missing', 'new')
        self.assertEqual(set(self.h.read_photo_ids()), {'old', 'taken'})

    def test_delete_photo_id_preserves_history_and_other_ids(self):
        self.h.add_entries({'subject': 'A', 'pose': 'Standing'}, photo_id='delete-me')
        self.h.add_entries({'subject': 'A'}, photo_id='keep-me')
        original_history = self.h.read_history()
        result = self.h.delete_photo_id('delete-me')
        self.assertEqual(result['history'], original_history)
        self.assertEqual(result['photo_ids'], {'keep-me': {'subject': 'A'}})
        self.assertNotIn('delete-me', self.h.FILE.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            self.h.delete_photo_id('delete-me')

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

    def test_export_import_round_trip_preserves_history_and_photo_ids(self):
        self.h.add_entries({'subject': '東京', 'lighting': 'Soft'}, photo_id='photo-1')
        self.h.add_entries({'subject': 'Another'}, photo_id='photo-2')
        backup = json.loads(json.dumps(self.h.export_data(), ensure_ascii=False))
        self.assertEqual(backup['version'], 2)
        self.assertEqual(backup['history']['subject'][1]['photo_ids'], ['photo-1'])
        self.h.clear_field('subject')
        self.h.clear_field('lighting')
        self.assertNotIn('photo-1', self.h.read_photo_ids())
        restored = self.h.import_data(backup)
        self.assertEqual(restored['photo_ids']['photo-1'],
                         {'subject': '東京', 'lighting': 'Soft'})
        self.assertEqual(self.h.export_data(), backup)

    def test_invalid_import_does_not_replace_existing_history(self):
        self.h.add_entries({'subject': 'Keep'}, photo_id='keep')
        before = self.h.FILE.read_bytes()
        good = self.h.export_data()
        bad_cases = [
            None,
            {'version': 1, 'history': good['history']},
            {'version': 2, 'history': {}},
        ]
        duplicate_text = copy.deepcopy(good)
        duplicate_text['history']['subject'].append(copy.deepcopy(
            duplicate_text['history']['subject'][0]))
        bad_cases.append(duplicate_text)
        duplicate_id = copy.deepcopy(good)
        duplicate_id['history']['subject'].append(
            {'text': 'Other', 'photo_ids': ['keep']})
        bad_cases.append(duplicate_id)
        bad_id = copy.deepcopy(good)
        bad_id['history']['subject'][0]['photo_ids'] = ['bad id']
        bad_cases.append(bad_id)
        for bad in bad_cases:
            with self.subTest(data=bad), self.assertRaises(ValueError):
                self.h.import_data(bad)
            self.assertEqual(self.h.FILE.read_bytes(), before)


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
        self.assertEqual(mod.NODE_CLASS_MAPPINGS, {
            mod.NODE_ID: mod.Krea2PhotoPromptBuilder,
            mod.REFERENCE_NODE_ID: mod.Krea2PhotoPromptReference,
        })
        self.assertEqual(mod.NODE_DISPLAY_NAME_MAPPINGS, {
            mod.NODE_ID: 'Krea2 Photo Prompt Builder',
            mod.REFERENCE_NODE_ID: 'Krea2 Photo Prompt Reference',
        })
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

    def test_reference_reads_current_combination_without_writing(self):
        import sys
        import types
        from unittest.mock import patch
        history = load('history_for_reference', 'history.py')
        with tempfile.TemporaryDirectory() as directory:
            history.FILE = Path(directory) / 'history.json'
            history.add_entries({'subject': ' A woman ', 'lighting': 'Soft light',
                                 'pose': 'Unused'}, photo_id='photo-1',
                                enabled={'pose': False})
            package = types.ModuleType('testreference')
            package.__path__ = [str(ROOT)]
            with patch.dict(sys.modules, {'testreference': package,
                                          'testreference.history': history}):
                spec = importlib.util.spec_from_file_location('testreference.nodes', ROOT / 'nodes.py')
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            reference = mod.Krea2PhotoPromptReference()
            self.assertEqual(set(reference.INPUT_TYPES()['required']), {'photo_id'})
            self.assertEqual(reference.INPUT_TYPES()['required']['photo_id'][0],
                             [mod.SELECT_PHOTO_ID, 'photo-1'])
            before = history.FILE.read_bytes()
            self.assertEqual(reference.build('photo-1'),
                             ('Subject:\nA woman\n\nLighting:\nSoft light',))
            self.assertEqual(history.FILE.read_bytes(), before)
            self.assertEqual(set(reference.INPUT_TYPES()['optional']),
                             {'additional_tag', 'additional_prompt'})
            for field, label in mod.HEADINGS.items():
                with self.subTest(tag=label):
                    expected = {'subject': 'A woman', 'lighting': 'Soft light'}
                    expected[field] = '\n'.join(filter(None, [expected.get(field, ''),
                                                              'trigger_one, trigger_two']))
                    self.assertEqual(
                        reference.build('photo-1', label, ' trigger_one, trigger_two '),
                        (mod.compose_prompt(expected, {}),))
            self.assertEqual(reference.build('photo-1', 'Subject', '  '),
                             reference.build('photo-1'))
            self.assertEqual(reference.build('photo-1'),
                             ('Subject:\nA woman\n\nLighting:\nSoft light',))
            self.assertEqual(history.FILE.read_bytes(), before)
            self.assertEqual(reference.IS_CHANGED('photo-1', 'Subject', 'trigger'),
                             reference.IS_CHANGED('photo-1'))
            with self.assertRaisesRegex(ValueError, 'Unknown additional prompt tag'):
                reference.build('photo-1', 'invalid', 'trigger')
            with self.assertRaisesRegex(ValueError, 'Select a Photo ID'):
                reference.build(mod.SELECT_PHOTO_ID)
            with self.assertRaisesRegex(ValueError, 'does not exist'):
                reference.build('missing')
            cache_key = reference.IS_CHANGED('photo-1')
            history.add_entries({'subject': 'Updated'}, photo_id='photo-1', overwrite=True)
            self.assertNotEqual(reference.IS_CHANGED('photo-1'), cache_key)
            self.assertEqual(reference.build('photo-1'), ('Subject:\nUpdated',))


class TestImages(unittest.TestCase):
    def test_local_example_lookup_uses_supported_files_only(self):
        import sys
        import types
        from unittest.mock import patch
        package = types.ModuleType('testimages')
        package.__path__ = [str(ROOT)]
        with patch.dict(sys.modules, {'testimages': package,
                                      'testimages.history': load('history_for_images', 'history.py')}):
            spec = importlib.util.spec_from_file_location('testimages.images', ROOT / 'images.py')
            images = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(images)
        with tempfile.TemporaryDirectory() as directory:
            images.IMAGE_DIR = Path(directory) / 'images'
            self.assertEqual(images.photo_images(), {})
            images.IMAGE_DIR.mkdir()
            (images.IMAGE_DIR / 'photo-1.jpg').write_bytes(b'jpg')
            (images.IMAGE_DIR / 'photo-1.png').write_bytes(b'png')
            (images.IMAGE_DIR / 'photo-2.webp').write_bytes(b'webp')
            (images.IMAGE_DIR / 'invalid name.jpg').write_bytes(b'bad')
            (images.IMAGE_DIR / 'photo-3.svg').write_text('<svg/>')
            (images.IMAGE_DIR / 'linked.jpg').symlink_to(images.IMAGE_DIR / 'photo-1.jpg')
            found = images.photo_images()
            self.assertEqual(set(found), {'photo-1', 'photo-2'})
            self.assertEqual(found['photo-1'].name, 'photo-1.png')


if __name__ == '__main__':
    unittest.main()
