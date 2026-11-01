"""Regression tests for the current AppNho-only digest implementation."""
import unittest
from datetime import datetime, timedelta, timezone

from create_digest import appnho_rows, choose_digest_items


class DigestLogicTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 30, 5, 0, tzinfo=timezone.utc)

    def article(self, ident, hours_ago, *, title=None, quality="PASS", legacy=None,
                summary="Bài viết có phần tóm tắt biên tập đủ dài để kiểm tra điều kiện digest.",
                event_key=None):
        published = (self.now - timedelta(hours=hours_ago)).isoformat()
        row = {
            "id": ident,
            "title": title or f"Bản tin số {ident} với nội dung riêng biệt về một diễn biến đáng chú ý",
            "summary": summary,
            "body": [],
            "published_at": published,
            "appnho_published_at": published,
            "quality_version": "1.5",
            "quality_status": quality,
            "category": "vietnam",
        }
        if legacy is not None:
            row["legacy_upgrade_status"] = legacy
        if event_key:
            row["event_key"] = event_key
        return row

    def test_fresh_articles_are_prioritized_and_old_pass_articles_supplement_to_six(self):
        fresh_titles = [
            "Quốc hội thảo luận dự án luật mới trong kỳ họp tháng mười",
            "Giá vàng thế giới biến động mạnh sau quyết định của ngân hàng trung ương",
            "Đội tuyển bóng đá nữ giành chiến thắng ở trận bán kết khu vực",
            "Một tuyến cao tốc mới bắt đầu thu phí từ đầu tháng tới",
        ]
        old_titles = [
            "Bộ giáo dục công bố khung tuyển sinh đại học cho năm học mới",
            "Doanh nghiệp năng lượng tái tạo ký hợp đồng cung cấp điện dài hạn",
            "Thành phố điều chỉnh phương án phân luồng giao thông tại trung tâm",
            "Nông dân mở rộng diện tích trồng cây ăn quả phục vụ xuất khẩu",
            "Bệnh viện tuyến tỉnh đưa vào sử dụng trung tâm xét nghiệm mới",
        ]
        rows = [self.article(f"fresh-{i}", i, title=fresh_titles[i]) for i in range(4)]
        rows += [self.article(f"old-{i}", 48 + i, title=old_titles[i]) for i in range(5)]
        fresh, older = appnho_rows(rows, self.now)

        chosen, supplements = choose_digest_items(fresh, older)

        self.assertEqual(len(fresh), 4)
        self.assertEqual(len(chosen), 6)
        self.assertEqual(supplements, 2)
        self.assertEqual([item["id"] for item in chosen[:4]], [f"fresh-{i}" for i in range(4)])
        self.assertTrue(all(item["is_supplement"] for item in chosen[4:]))

    def test_digest_is_not_ready_when_fewer_than_six_eligible_articles_exist(self):
        fresh, older = appnho_rows([self.article("one", 1, title="Cơ quan khí tượng phát cảnh báo mưa lớn tại miền Trung"), self.article("two", 2, title="Một ngân hàng công bố kế hoạch mở rộng mạng lưới chi nhánh")], self.now)
        chosen, supplements = choose_digest_items(fresh, older)
        self.assertEqual(len(chosen), 2)
        self.assertEqual(supplements, 0)

    def test_similar_titles_and_same_event_are_not_repeated(self):
        rows = [
            self.article("a", 1, title="Chính phủ công bố kế hoạch phát triển kinh tế"),
            self.article("b", 2, title="Chính phủ công bố kế hoạch phát triển kinh tế", event_key="event-2"),
            self.article("c", 3, title="Một sự kiện hoàn toàn khác trong lĩnh vực giáo dục", event_key="event-3"),
            self.article("d", 4, title="Tin khác về giao thông đô thị", event_key="event-3"),
        ]
        fresh, older = appnho_rows(rows, self.now)
        chosen, _ = choose_digest_items(fresh, older)
        ids = [item["id"] for item in chosen]
        self.assertIn("a", ids)
        self.assertIn("c", ids)
        self.assertNotIn("b", ids)
        self.assertNotIn("d", ids)

    def test_missing_summary_uses_first_two_body_paragraphs(self):
        row = self.article("body-fallback", 1, summary="")
        row["body"] = ["Đoạn thứ nhất có nội dung cụ thể.", "Đoạn thứ hai bổ sung bối cảnh.", "Đoạn thứ ba."]
        fresh, _ = appnho_rows([row], self.now)
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0]["summary"], "Đoạn thứ nhất có nội dung cụ thể. Đoạn thứ hai bổ sung bối cảnh.")

    def test_digest_links_point_to_appnho_article_pages(self):
        fresh, _ = appnho_rows([self.article("story-123", 1)], self.now)
        self.assertEqual(fresh[0]["url"], "https://appnho.io.vn/news/article.html?id=story-123")

    def test_unqualified_legacy_and_non_pass_articles_are_excluded(self):
        rows = [
            self.article("pending-legacy", 50, legacy="PENDING"),
            self.article("hold-legacy", 50, legacy="HOLD"),
            self.article("failed-quality", 1, quality="HOLD"),
            self.article("no-version", 1),
        ]
        rows[-1].pop("quality_version")
        fresh, older = appnho_rows(rows, self.now)
        self.assertEqual(fresh, [])
        self.assertEqual(older, [])

    def test_future_publication_and_digest_records_are_excluded(self):
        future = self.article("future", -1)
        digest = self.article("digest", 1)
        digest["content_type"] = "news_digest"
        fresh, older = appnho_rows([future, digest], self.now)
        self.assertEqual(fresh, [])
        self.assertEqual(older, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
