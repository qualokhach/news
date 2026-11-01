import unittest
import news_pipeline as pipeline

class TestResearchReliabilityRepairs(unittest.TestCase):
    def test_namespaced_dublin_core_date_is_read(self):
        import xml.etree.ElementTree as ET
        root=ET.fromstring('''<item xmlns:dc="http://purl.org/dc/elements/1.1/">
          <title>Tiêu đề</title><link>https://example.vn/a</link>
          <dc:date>2026-11-01T08:30:00+07:00</dc:date>
        </item>''')
        self.assertEqual(pipeline.get_text(root,['pubDate','published','updated','date']),"2026-11-01T08:30:00+07:00")
        self.assertEqual(pipeline.parse_date(pipeline.get_text(root,['date'])),"2026-11-01T01:30:00+00:00")

    def test_atom_link_href_and_published(self):
        import xml.etree.ElementTree as ET
        root=ET.fromstring('''<entry xmlns="http://www.w3.org/2005/Atom">
          <title>Tiêu đề</title><link rel="alternate" href="https://example.vn/a"/>
          <published>2026-11-01T01:30:00Z</published>
        </entry>''')
        self.assertEqual(pipeline.get_text(root,['link']),"https://example.vn/a")
        self.assertEqual(pipeline.parse_date(pipeline.get_text(root,['published'])),"2026-11-01T01:30:00+00:00")

    def test_page_metadata_date_fallback(self):
        html='''<html><head><meta property="article:published_time" content="2026-11-01T08:30:00+07:00"></head></html>'''
        self.assertEqual(pipeline.publication_date_from_html(html),"2026-11-01T01:30:00+00:00")

    def test_common_publisher_date_formats(self):
        self.assertTrue(pipeline.parse_date("Sun, 01 Nov 2026 08:30:00 +0700"))
        self.assertTrue(pipeline.parse_date("2026-11-01 08:30:00"))
        self.assertTrue(pipeline.parse_date("1793496600"))

    def test_clear_vietnam_event_not_left_in_world(self):
        self.assertEqual(
            pipeline.normalize_vietnam_category(
                "Vụ người đàn ông ngất xỉu trên đường Cần Thơ",
                "Công an TP Cần Thơ xác nhận nguyên nhân.",
                ["Sự việc xảy ra tại Cần Thơ."],
                "world"
            ),
            "vietnam"
        )

    def test_bbc_uk_and_bbc_com_are_same_publisher_family(self):
        info=pipeline.source_info("https://www.bbc.co.uk/news/articles/example")
        self.assertEqual(info.get("source_family"),"bbc.com")

    def test_tp_hcm_dotted_name_is_detected_as_vietnam(self):
        self.assertEqual(
            pipeline.normalize_vietnam_category(
                "TP.HCM khai mạc Diễn đàn Kinh tế mùa thu 2026",
                "Sự kiện diễn ra tại TP.HCM.",
                ["Đại biểu tham dự tại Thành phố Hồ Chí Minh."],
                "world"
            ),
            "vietnam"
        )

    def test_genuine_world_story_not_forced_to_vietnam(self):
        self.assertEqual(
            pipeline.normalize_vietnam_category(
                "Spain train disaster clouds election",
                "Sự cố đường sắt tại Tây Ban Nha.",
                ["Nhà chức trách Tây Ban Nha đang điều tra."],
                "world"
            ),
            "world"
        )

if __name__ == '__main__':
    unittest.main()
