import unittest
from datetime import datetime, timezone, timedelta
from create_digest import pending_rows, appnho_rows, choose_items

class DigestLogicTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)

    def pending(self, ident, hours, title=None, summary="Tóm tắt đã biên tập", url=None, status="queued"):
        return {"id": ident, "status": status, "discovery_title": title or ident,
                "discovery_summary": summary,
                "source_published_at": (self.now-timedelta(hours=hours)).isoformat(),
                "source_url": url or "https://source.example/"+ident, "category":"vietnam"}

    def article(self, ident, hours, title=None, summary="Tóm tắt đã biên tập", url=None):
        return {"id":ident, "title":title or ident, "summary":summary,
                "published_at":(self.now-timedelta(hours=hours)).isoformat(),
                "source_url":url or "https://appnho.example/"+ident, "body":[]}

    def test_fresh_24h_priority_and_six_minimum_supplement(self):
        fresh=pending_rows([self.pending(f"new{i}",i) for i in range(4)], set(), self.now)
        old=appnho_rows([self.article(f"old{i}",48+i) for i in range(5)], [], [], self.now)
        chosen, fresh_count, supplements=choose_items(fresh, old)
        self.assertEqual(fresh_count,4)
        self.assertEqual(len(chosen),6)
        self.assertEqual(supplements,2)
        self.assertEqual([x["title"] for x in chosen[:4]],[f"new{i}" for i in range(4)])

    def test_no_publish_when_less_than_six_even_after_archive(self):
        fresh=pending_rows([self.pending("a",1),self.pending("b",2)],set(),self.now)
        chosen,_,_=choose_items(fresh,[])
        self.assertLess(len(chosen),6)

    def test_deduplicate_title_and_source_url(self):
        rows=pending_rows([
            self.pending("a",1,"Same title"),
            self.pending("b",2,"Same title"),
            self.pending("c",3,"Other",url="https://source.example/a")
        ],set(),self.now)
        self.assertEqual(len(rows),1)

    def test_body_fallback_when_summary_missing(self):
        row=self.article("a",1,summary="",)
        row["body"]=["Đoạn một","Đoạn hai"]
        rows=appnho_rows([row],[],[],self.now)
        self.assertEqual(rows[0]["summary"],"Đoạn một Đoạn hai")

    def test_digest_items_retain_appnho_article_urls(self):
        rows=appnho_rows([self.article(f"a{i}",i) for i in range(6)],[],[],self.now)
        self.assertTrue(all(x["url"].startswith("https://www.appnho.io.vn/news/article.html?id=") for x in rows))

    def test_reject_stale_future_and_published_pending_items(self):
        rows=pending_rows([
            self.pending("stale",25), self.pending("future",-1),
            self.pending("done",1,status="published")
        ],set(),self.now)
        self.assertEqual(rows,[])

if __name__ == "__main__":
    unittest.main()
