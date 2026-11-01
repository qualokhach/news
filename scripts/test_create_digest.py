import unittest
from datetime import datetime, timezone, timedelta
from create_digest import appnho_rows, choose_digest_items

class DigestLegacyEligibilityTests(unittest.TestCase):
    def test_legacy_supplements_require_completed_upgrade_and_quality_pass(self):
        now=datetime(2026,10,31,12,0,tzinfo=timezone.utc)
        old_date=(now-timedelta(days=2)).isoformat()
        rows=[
            {"id":"legacy-pass","title":"Bài cũ đã nâng cấp","summary":"Tóm tắt bài cũ đã được kiểm chứng đầy đủ và đủ dài.",
             "content_type":"news","quality_version":"1.5","quality_status":"PASS",
             "legacy_upgrade_status":"PASS","appnho_published_at":old_date,"published_at":old_date},
            {"id":"legacy-pending","title":"Bài cũ chưa nâng cấp","summary":"Tóm tắt bài cũ chưa được nâng cấp và chưa được xác minh.",
             "content_type":"news","quality_version":"1.5","quality_status":"PASS",
             "legacy_upgrade_status":"PENDING","appnho_published_at":old_date,"published_at":old_date},
            {"id":"legacy-hold","title":"Bài cũ đang HOLD","summary":"Tóm tắt bài cũ đang bị giữ lại để kiểm tra chứng cứ.",
             "content_type":"news","quality_version":"1.5","quality_status":"PASS",
             "legacy_upgrade_status":"HOLD","appnho_published_at":old_date,"published_at":old_date},
            {"id":"new-pass","title":"Bài mới đạt chuẩn","summary":"Tóm tắt bài mới đã qua kiểm tra chất lượng và đủ điều kiện.",
             "content_type":"news","quality_version":"1.5","quality_status":"PASS",
             "appnho_published_at":now.isoformat(),"published_at":now.isoformat()},
        ]
        fresh,older=appnho_rows(rows,now)
        self.assertEqual([x["id"] for x in fresh],["new-pass"])
        self.assertEqual([x["id"] for x in older],["legacy-pass"])

    def test_digest_supplements_old_pass_articles_only_when_fresh_count_is_short(self):
        fresh=[{"id":str(i),"title":["Ngân hàng trung ương điều chỉnh lãi suất","Nhà máy điện gió khánh thành ở miền Trung","Đội tuyển giành vé vào chung kết","Cảng biển công bố sản lượng hàng hóa quý mới"][i],"event_key":""} for i in range(4)]
        older=[{"id":"old-1","title":"Hội đồng trường đại học công bố chương trình học bổng mới","event_key":""},
               {"id":"old-2","title":"Mưa lớn gây ngập cục bộ tại một số tuyến phố","event_key":""}]
        chosen,supplements=choose_digest_items(fresh,older,minimum=6,maximum=10)
        self.assertEqual(len(chosen),6)
        self.assertEqual(supplements,2)

if __name__=="__main__":
    unittest.main(verbosity=2)
