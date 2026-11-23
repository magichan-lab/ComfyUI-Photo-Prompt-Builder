import copy
import importlib.util
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
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
        self.original_db = self.h.DB_FILE
        self.h.DB_FILE = Path(self.temp.name) / 'history.sqlite3'
        self.original = self.h.FILE
        self.original_template = self.h.TEMPLATE_FILE
        self.h.FILE = Path(self.temp.name) / 'history.json'
        self.h.TEMPLATE_FILE = Path(self.temp.name) / 'template.json'
        template = ROOT / 'data' / 'prompt_history_template.json'
        self.h.TEMPLATE_FILE.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')

    def tearDown(self):
        self.h.DB_FILE = self.original_db
        self.h.FILE = self.original
        self.h.TEMPLATE_FILE = self.original_template
        self.temp.cleanup()

    def test_missing_history_uses_template_then_saved_history(self):
        self.h.TEMPLATE_FILE.write_text(
            '{"version": 2, "history": {"subject": [{"text": "Default", "photo_ids": []}]}}',
            encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['Default'])
        self.assertTrue(self.h.DB_FILE.exists())
        self.assertFalse(self.h.FILE.exists())
        self.h.add_entries({'subject': 'Saved'})
        self.assertEqual(self.h.read_history()['subject'], ['Saved', 'Default'])
        self.h.TEMPLATE_FILE.write_text('{"version": 2, "history": {}}', encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['Saved', 'Default'])

    def test_add_deduplicate_delete(self):
        self.h.add_entries({'subject': 'A', 'appearance': 'White shirt'})
        self.h.add_entries({'subject': 'B'})
        self.h.add_entries({'subject': 'A'})
        self.assertEqual(self.h.read_history()['subject'], ['A', 'B'])
        self.assertEqual(self.h.read_history()['appearance'], ['White shirt'])
        self.h.delete_entry('subject', 'A')
        self.assertEqual(self.h.read_history()['subject'], ['B'])
        self.h.clear_field('subject')
        self.assertEqual(self.h.read_history()['subject'], [])

    def test_invalid_and_unicode(self):
        self.h.add_entries({'environment': '東京・夕暮れ'})
        self.assertEqual(self.h.read_history()['environment'], ['東京・夕暮れ'])
        with self.assertRaises(ValueError):
            self.h.add_entries({'unknown': 'x'})

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
        saved = json.dumps(self.h.export_data())
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
        self.assertNotIn('delete-me', json.dumps(self.h.export_data()))
        with self.assertRaises(ValueError):
            self.h.delete_photo_id('delete-me')

    def test_all_entries_are_retained(self):
        self.h.add_entries({'subject': 'Pinned'}, photo_id='pin')
        self.h.add_entries({'subject': 'One'})
        self.h.add_entries({'subject': 'Two'})
        self.assertEqual(self.h.read_history()['subject'], ['Two', 'One', 'Pinned'])
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
        before = self.h.export_data()
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
            self.assertEqual(self.h.export_data(), before)


    def test_migration_preserves_v2_order_ids_and_original(self):
        data = self.h._empty()
        data['history']['subject'] = [
            {'text': '東京', 'photo_ids': ['z-last', 'a-first']},
            {'text': 'Older', 'photo_ids': ['old']},
        ]
        data['history']['lighting'] = [{'text': '東京', 'photo_ids': ['z-last']}]
        source = json.dumps(data, ensure_ascii=False)
        self.h.FILE.write_text(source, encoding='utf-8')
        self.assertEqual(self.h.export_data(), data)
        self.assertEqual(self.h.FILE.read_text(encoding='utf-8'), source)
        self.h.add_entries({'subject': 'New'}, return_state=False)
        self.h.FILE.write_text('invalid now; must not be reimported', encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['New', '東京', 'Older'])
        with sqlite3.connect(self.h.DB_FILE) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM texts WHERE text = ?', ('東京',)).fetchone()[0], 1)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_failed_migration_is_rolled_back_and_can_be_retried(self):
        source = '{bad JSON'
        self.h.FILE.write_text(source, encoding='utf-8')
        with self.assertRaises(RuntimeError):
            self.h.migrate()
        self.assertEqual(self.h.FILE.read_text(encoding='utf-8'), source)
        with sqlite3.connect(self.h.DB_FILE) as conn:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
        self.h.FILE.write_text('{"version": 1, "history": {"subject": ["Recovered"]}}', encoding='utf-8')
        self.assertEqual(self.h.read_history()['subject'], ['Recovered'])

    def test_migration_rejects_invalid_associations_without_losing_source(self):
        data = self.h._empty()
        data['history']['subject'] = [{'text': 'A', 'photo_ids': ['same']},
                                      {'text': 'B', 'photo_ids': ['same']}]
        source = json.dumps(data)
        self.h.FILE.write_text(source, encoding='utf-8')
        with self.assertRaises(ValueError):
            self.h.migrate()
        self.assertEqual(self.h.FILE.read_text(encoding='utf-8'), source)

    def test_cli_migration_is_idempotent(self):
        self.h.FILE.write_text('{"version": 1, "history": {"subject": ["Imported"]}}', encoding='utf-8')
        command = [sys.executable, str(ROOT / 'migrate_history.py'), '--source', str(self.h.FILE),
                   '--database', str(self.h.DB_FILE)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.h.add_entries({'subject': 'Keep'}, return_state=False)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.h.read_history()['subject'], ['Keep', 'Imported'])

    def test_large_history_pagination_and_indexed_lookup(self):
        data = self.h._empty()
        data['history']['subject'] = [
            {'text': f'Entry {i}', 'photo_ids': [f'photo-{i}'] if i % 10 == 0 else []}
            for i in range(5000)
        ]
        self.h.import_data(data)
        collected = []
        cursor = None
        while True:
            page = self.h.read_history_page('subject', cursor, page_size=127)
            self.assertLessEqual(len(page['items']), 127)
            self.assertEqual(page['has_photo_id'], [int(text.split()[1]) % 10 == 0 for text in page['items']])
            collected.extend(page['items'])
            cursor = page['next_cursor']
            if cursor is None:
                break
        self.assertEqual(collected, [f'Entry {i}' for i in range(5000)])
        self.assertEqual(self.h.read_photo_id('photo-4990'), {'subject': 'Entry 4990'})
        self.assertIsNone(self.h.read_photo_id('missing'))
        self.assertEqual(len(self.h.list_photo_ids()), 500)
        with sqlite3.connect(self.h.DB_FILE) as conn:
            plan = str(conn.execute('EXPLAIN QUERY PLAN SELECT t.text, h.position FROM history h '
                'JOIN texts t ON t.id = h.text_id WHERE h.field = ? AND h.position < ? '
                'ORDER BY h.position DESC, h.text_id LIMIT ?', ('subject', 2500, 101)).fetchall())
            self.assertIn('history_recent', plan)
            self.assertNotIn('TEMP B-TREE', plan)
        with patch.object(self.h, '_state', side_effect=AssertionError('Autosave loaded full state')):
            self.h.add_entries({'subject': 'Autosaved'}, return_state=False)
        self.assertEqual(len(self.h.read_history()['subject']), 5001)

    def test_history_page_photo_id_status_tracks_field_and_deletion(self):
        data = self.h._empty()
        data['history']['subject'] = [
            {'text': 'Assigned', 'photo_ids': ['one', 'two']},
            {'text': 'Shared', 'photo_ids': []},
        ]
        data['history']['pose'] = [{'text': 'Shared', 'photo_ids': ['one']}]
        self.h.import_data(data)
        page = self.h.read_history_page('subject')
        self.assertEqual(page['items'], ['Assigned', 'Shared'])
        self.assertEqual(page['has_photo_id'], [True, False])
        self.assertEqual(self.h.read_history_page('pose')['has_photo_id'], [True])
        self.h.delete_photo_id('one')
        self.assertEqual(self.h.read_history_page('subject')['has_photo_id'], [True, False])
        self.assertEqual(self.h.read_history_page('pose')['has_photo_id'], [False])
        self.h.delete_photo_id('two')
        self.assertEqual(self.h.read_history_page('subject')['has_photo_id'], [False, False])

    def test_cascade_and_shared_text_cleanup(self):
        self.h.add_entries({'subject': 'Shared', 'pose': 'Shared'}, photo_id='one')
        self.h.delete_entry('subject', 'Shared')
        self.assertEqual(self.h.read_photo_id('one'), {'pose': 'Shared'})
        with sqlite3.connect(self.h.DB_FILE) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM texts').fetchone()[0], 1)
        self.h.clear_field('pose')
        with sqlite3.connect(self.h.DB_FILE) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM texts').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM photo_fields').fetchone()[0], 0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_concurrent_writes_do_not_lose_entries(self):
        def save(i):
            self.h.add_entries({'subject': f'Entry {i}'}, photo_id=f'id-{i}', return_state=False)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(save, range(40)))
        self.assertEqual(set(self.h.read_history()['subject']), {f'Entry {i}' for i in range(40)})
        self.assertEqual(len(self.h.read_photo_ids()), 40)
        with sqlite3.connect(self.h.DB_FILE) as conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_import_failure_rolls_back_entire_database(self):
        self.h.add_entries({'subject': 'Keep'}, photo_id='keep')
        before = self.h.export_data()
        with patch.object(self.h, '_insert_backup', side_effect=RuntimeError('Interrupted')):
            with self.assertRaises(RuntimeError):
                self.h.import_data(self.h._empty())
        self.assertEqual(self.h.export_data(), before)


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
        self.assertNotIn('history_limit', inputs)
        for field in ('appearance', 'hair_makeup', 'pose', 'expression'):
            self.assertIn(field, inputs)
            self.assertIn(f'use_{field}', inputs)

    def test_reference_reads_current_combination_without_writing(self):
        import sys
        import types
        from unittest.mock import patch
        history = load('history_for_reference', 'history.py')
        with tempfile.TemporaryDirectory() as directory:
            history.DB_FILE = Path(directory) / 'history.sqlite3'
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
            before = history.export_data()
            self.assertEqual(reference.build('photo-1'),
                             ('Subject:\nA woman\n\nLighting:\nSoft light',))
            self.assertEqual(history.export_data(), before)
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
            self.assertEqual(history.export_data(), before)
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
