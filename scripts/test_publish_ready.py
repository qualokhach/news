import unittest, hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import publish_ready
from content_quality import normalize_evidence_text

class PublishReadyTests(unittest.TestCase):
    def article(self):
        body=[]
        for i in range(7):
            body.append((f"Đoạn {i+1} nêu dữ kiện cụ thể về sự kiện, chủ thể, mốc thời gian và phạm vi được tài liệu chính thức xác nhận. "
                         f"Phần này đối chiếu con số và diễn biến với dữ liệu liên quan, giải thích ý nghĩa thực tế và chỉ rõ giới hạn của kết luận. ")*12)
        urls=["https://www.bbc.co.uk/news/a","https://www.reuters.com/world/b"]
        refs=[
            {"name":"BBC","url":urls[0],"is_primary":False,"access_status":"UNVERIFIED","terms_status":"UNVERIFIED","commercial_use_status":"UNVERIFIED","research_mode":"LIMITED_FACTUAL_REFERENCE","reuse_mode":"FACTUAL_CITATION_ONLY"},
            {"name":"Reuters","url":urls[1],"is_primary":False,"access_status":"UNVERIFIED","terms_status":"UNVERIFIED","commercial_use_status":"UNVERIFIED","research_mode":"LIMITED_FACTUAL_REFERENCE","reuse_mode":"FACTUAL_CITATION_ONLY"}
        ]
        evidence_pages={
            "https://www.bbc.co.uk/news/a": (
                "Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể. "
                "Dữ kiện chính thứ hai được hai nguồn độc lập xác nhận. "
                "Bối cảnh thứ ba làm rõ phạm vi thông tin."
            ),
            "https://www.reuters.com/world/b": (
                "Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể. "
                "Dữ kiện chính thứ hai được hai nguồn độc lập xác nhận."
            )
        }
        self.evidence_pages=evidence_pages
        ledger=[
            {"claim":"Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể.","source_urls":urls,"evidence_snippet":"Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể."},
            {"claim":"Dữ kiện chính thứ hai được hai nguồn độc lập xác nhận.","source_urls":urls,"evidence_snippet":"Dữ kiện chính thứ hai được hai nguồn độc lập xác nhận."},
            {"claim":"Bối cảnh thứ ba làm rõ phạm vi thông tin.","source_urls":[urls[0]],"evidence_snippet":"Bối cảnh thứ ba làm rõ phạm vi thông tin."}
        ]
        for fact in ledger:
            evidence_items=[]
            proofs=[]
            for src in fact["source_urls"]:
                if fact["evidence_snippet"] not in evidence_pages.get(src,""):
                    continue
                evidence_items.append({"source_url":src,"snippet":fact["evidence_snippet"],"locator":"Test source excerpt"})
                page_norm=normalize_evidence_text(evidence_pages[src])
                snippet_norm=normalize_evidence_text(fact["evidence_snippet"])
                proofs.append({
                    "source_url":src,
                    "page_sha256":hashlib.sha256(page_norm.encode("utf-8")).hexdigest(),
                    "snippet_sha256":hashlib.sha256(snippet_norm.encode("utf-8")).hexdigest(),
                    "verified_at":datetime.now(timezone.utc).isoformat(),
                    "match_method":"exact_normalized_substring"
                })
            fact["evidence_by_source"]=evidence_items
            fact["evidence_verifications"]=proofs
        return {
            "id":"publish-ready-test","title":"Sự kiện được xác nhận qua hai nguồn độc lập",
            "summary":"Bài viết đối chiếu dữ kiện và bối cảnh từ hai nguồn độc lập.",
            "body":body,"editorial_value":"Đối chiếu hai nguồn độc lập. Phân biệt dữ kiện đã xác nhận với phần còn chưa rõ.",
            "content_type":"short_explainer",
            "risk_level":"R1","quality_status":"PASS","quality_version":"1.5",
            "fact_ledger":ledger,
            "source_references":refs,"verification_timestamp":datetime.now(timezone.utc).isoformat(),
            "freshness_ttl_hours":24
        }

    def test_final_source_check_uses_small_get_range_not_head(self):
        class Response:
            status=206
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n=-1): return b'page'
        with patch.object(publish_ready,'robots_allowed',return_value=True), \
             patch.object(publish_ready,'urlopen',return_value=Response()) as opener:
            ok,reason=publish_ready.check_source_access('https://publisher.example/story')
        self.assertTrue(ok,reason)
        request=opener.call_args.args[0]
        self.assertEqual(request.get_method(),'GET')
        self.assertEqual(request.get_header('Range'),'bytes=0-4095')

    def test_candidate_passes_when_quality_and_sources_are_valid(self):
        article=self.article()
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")), \
             patch.object(publish_ready.research_pipeline,"extract_page",side_effect=lambda url,access_mode=None:self.evidence_pages[url]):
            ok,errors,stats=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertTrue(ok,errors)
        self.assertEqual(len(stats["source_access"]),2)

    def test_factual_citation_does_not_require_commercial_reuse_license(self):
        article=self.article()
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")), \
             patch.object(publish_ready.research_pipeline,"extract_page",side_effect=lambda url,access_mode=None:self.evidence_pages[url]):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertTrue(ok,errors)

    def test_candidate_fails_if_evidence_snippet_changes_after_verification(self):
        article=self.article()
        article["fact_ledger"][0]["evidence_snippet"]="Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể được xác nhận trong hồ sơ."
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any("trích đoạn" in e for e in errors))

    def test_candidate_fails_if_evidence_disappears_from_live_source_before_publish(self):
        article=self.article()
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")), \
             patch.object(publish_ready.research_pipeline,"extract_page",return_value="Nội dung trang nguồn đã thay đổi và không còn trích đoạn cũ."):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any("không còn xuất hiện" in e for e in errors))

    def test_candidate_fails_when_source_is_explicitly_blocked(self):
        article=self.article()
        article['source_references'][0]['terms_status']='BLOCKED'
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any('bị chặn' in e for e in errors))

    def test_candidate_fails_when_unlicensed_content_reuse_is_declared(self):
        article=self.article()
        article['source_references'][0]['reuse_mode']='FULL_TEXT_REUSE'
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any('tái sử dụng' in e for e in errors))

    def test_candidate_fails_without_explicit_quality_pass(self):
        article=self.article()
        article['quality_status']='HOLD'
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any('QA PASS' in e for e in errors))

    def test_candidate_fails_when_evidence_ttl_expired(self):
        article=self.article()
        article["verification_timestamp"]=(datetime.now(timezone.utc)-timedelta(hours=48)).isoformat()
        with patch.object(publish_ready,"check_source_access",return_value=(True,"HTTP 200")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any("freshness_ttl" in e for e in errors))

    def test_candidate_fails_when_source_access_is_blocked(self):
        article=self.article()
        with patch.object(publish_ready,"check_source_access",return_value=(False,"HTTP 403")):
            ok,errors,_=publish_ready.validate_candidate(article,datetime.now(timezone.utc))
        self.assertFalse(ok)
        self.assertTrue(any("không truy cập được" in e for e in errors))

if __name__=="__main__":
    unittest.main()
