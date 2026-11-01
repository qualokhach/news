import unittest
import upgrade_legacy_articles as legacy

class LegacyUpgradeTests(unittest.TestCase):
    def test_update_preserves_id_slug_and_historical_dates(self):
        original={
            "id":"stable-id","slug":"stable-slug","collection":"archive",
            "published_at":"2026-10-20T10:00:00+00:00",
            "fetched_at":"2026-10-22T10:00:00+00:00",
            "appnho_published_at":"2026-10-22T10:00:00+00:00",
            "editorial_note":"internal-only"
        }
        rewritten={
            "id":"generated-new-id","slug":"generated-new-slug","collection":"current",
            "published_at":"2026-10-31T10:00:00+00:00","fetched_at":"2026-10-31T10:00:00+00:00",
            "title":"Bài viết đã được nâng cấp","summary":"Tóm tắt mới",
            "body":["Đoạn nội dung mới"],"quality_version":"1.5","quality_status":"PASS",
            "word_count":700
        }
        result=legacy.update_article(original,rewritten)
        self.assertEqual(result["id"],"stable-id")
        self.assertEqual(result["slug"],"stable-slug")
        self.assertEqual(result["published_at"],"2026-10-20T10:00:00+00:00")
        self.assertEqual(result["appnho_published_at"],"2026-10-22T10:00:00+00:00")
        self.assertEqual(result["collection"],"archive")
        self.assertNotIn("editorial_note",result)
        self.assertEqual(result["legacy_upgrade_status"],"PASS")

if __name__=="__main__":
    unittest.main()
