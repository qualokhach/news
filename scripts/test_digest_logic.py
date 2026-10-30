import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('create_digest.py')
spec = importlib.util.spec_from_file_location('create_digest', MODULE_PATH)
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)


class DigestSelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)

    def story(self, n, hours, category='world'):
        dt = self.now - timedelta(hours=hours)
        return {
            'id': f'story-{n}', 'title': f'Tin {n}', 'summary': f'Tóm tắt tin {n}',
            'category': category, 'published_at': dt.isoformat(),
            'source_url': f'https://source.example/{n}', 'source_name': 'Nguồn thử nghiệm'
        }

    def test_prefers_fresh_stories_and_caps_at_ten(self):
        rows = [self.story(i, i) for i in range(1, 13)]
        chosen, fresh_count, supplement_count = digest.choose_items(rows, self.now)
        self.assertEqual(len(chosen), 10)
        self.assertEqual(fresh_count, 12)
        self.assertEqual(supplement_count, 0)
        self.assertTrue(all((self.now - digest.parse_datetime(x['published_at'])).total_seconds() <= 24*3600 for x in chosen))

    def test_supplements_only_when_fresh_pool_below_six(self):
        rows = [self.story(i, i) for i in range(1, 5)] + [self.story(i, 30+i) for i in range(5, 10)]
        chosen, fresh_count, supplement_count = digest.choose_items(rows, self.now)
        self.assertEqual(len(chosen), 6)
        self.assertEqual(fresh_count, 4)
        self.assertEqual(supplement_count, 2)
        self.assertEqual([x['id'] for x in chosen[:4]], ['story-1', 'story-2', 'story-3', 'story-4'])

    def test_does_not_publish_when_total_pool_below_six(self):
        rows = [self.story(i, i) for i in range(1, 4)]
        chosen, fresh_count, supplement_count = digest.choose_items(rows, self.now)
        self.assertEqual(len(chosen), 3)
        self.assertEqual(fresh_count, 3)
        self.assertEqual(supplement_count, 0)

    def test_raw_feed_leads_are_not_used(self):
        # The selection module only receives published article records; pending RSS leads are never read.
        self.assertFalse(hasattr(digest, 'PENDING'))


if __name__ == '__main__':
    unittest.main()
