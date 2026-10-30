import unittest
from datetime import datetime, timezone, timedelta
from create_digest import collect_published, choose_items

class DigestLogicTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)
    def article(self, ident, hours, title=None, summary='Tóm tắt đã biên tập', url=None, body=None):
        return {'id': ident, 'title': title or ident, 'summary': summary, 'body': body or [],
                'category':'vietnam', 'published_at':(self.now-timedelta(hours=hours)).isoformat(),
                'source_url':url or 'https://source.example/'+ident}
    def test_fresh_24h_priority_and_six_minimum_supplement(self):
        active=[self.article(f'new{i}', i) for i in range(4)]
        old=[self.article(f'old{i}', 48+i) for i in range(5)]
        rows=collect_published(active, old, [], self.now)
        chosen, fresh_count, supplements=choose_items(rows, self.now)
        self.assertEqual(fresh_count, 4)
        self.assertEqual(len(chosen), 6)
        self.assertEqual(supplements, 2)
        self.assertEqual([x['id'] for x in chosen[:4]], [f'new{i}' for i in range(4)])
    def test_no_publish_when_less_than_six_even_after_archive(self):
        rows=collect_published([self.article('a',1), self.article('b',2)], [], [], self.now)
        chosen, _, _=choose_items(rows, self.now)
        self.assertLess(len(chosen), 6)
    def test_deduplicate_title_and_source_url(self):
        rows=collect_published([self.article('a',1,'Same title'), self.article('b',2,'Same title'), self.article('c',3,'Other',url='https://source.example/a')], [], [], self.now)
        self.assertEqual(len(rows), 1)
    def test_body_fallback_when_summary_missing(self):
        rows=collect_published([self.article('a',1,summary='',body=['Đoạn một','Đoạn hai'])], [], [], self.now)
        self.assertEqual(rows[0]['summary'], 'Đoạn một Đoạn hai')
    def test_digest_items_keep_article_urls(self):
        rows=collect_published([self.article(f'n{i}',i) for i in range(6)], [], [], self.now)
        chosen, _, _=choose_items(rows,self.now)
        self.assertTrue(all(x['appnho_url'].startswith('https://www.appnho.io.vn/news/article.html?id=') for x in chosen))

if __name__ == '__main__': unittest.main()
