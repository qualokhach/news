import unittest
from content_quality import (
    body_stats, classify_risk, validate_fact_ledger, validate_fact_ledger_proof, verify_fact_ledger_against_pages, normalize_evidence_text, validate_article_quality,
    source_independence, domain_key, is_commercial_license, is_primary_source_type, ttl_for_data_type, minimum_words_for_type, target_word_range_for_type, minimum_paragraphs_for_type
)

class ContentQualityTests(unittest.TestCase):
    def sample_article(self):
        body=[]
        for i in range(7):
            body.append(
                f"Đoạn {i+1} trình bày một dữ kiện riêng về sự kiện, nêu rõ chủ thể, thời điểm và bối cảnh được tài liệu xác nhận. "
                f"Tài liệu nguồn mô tả diễn biến, phạm vi, các mốc thời gian và những thay đổi đã được xác nhận bằng hồ sơ cụ thể. "
                f"Phần giải thích thứ {i+1} đối chiếu thông tin này với bối cảnh liên quan, dữ liệu trước đó, nhóm chịu tác động và chỉ ra giới hạn của kết luận."
            )
        return {
            "title":"Sự kiện được xác nhận qua dữ liệu và tài liệu chính thức",
            "summary":"Bài viết phân tích các dữ kiện được công bố, bối cảnh và giới hạn của thông tin.",
            "body":body,
            "editorial_value":"Đối chiếu dữ liệu theo thời gian. Làm rõ điểm khác nhau giữa thông báo ban đầu với kết quả đã được xác nhận.",
            "risk_level":"R1"
        }


    def test_minimum_word_floor_matches_editorial_target_lower_bound(self):
        self.assertEqual(minimum_words_for_type("short_explainer"), 500)
        self.assertEqual(target_word_range_for_type("short_explainer"), (500, 650))
        self.assertEqual(minimum_paragraphs_for_type("short_explainer"), 3)
        self.assertEqual(minimum_words_for_type("news_analysis"), 800)
        self.assertEqual(target_word_range_for_type("news_analysis"), (800, 1000))

    def test_below_editorial_floor_short_explainer_is_rejected(self):
        body = [
            " ".join(f"du_lieu_{p}_{i}" for i in range(76))
            for p in range(4)
        ]
        article = {
            "title": "Sự kiện được xác nhận qua dữ liệu và tài liệu chính thức",
            "summary": "Bài viết phân tích các dữ kiện được công bố, bối cảnh và giới hạn của thông tin.",
            "content_type": "short_explainer",
            "body": body,
            "editorial_value": "Đối chiếu dữ liệu theo thời gian. Làm rõ điểm khác nhau giữa thông báo ban đầu với kết quả đã được xác nhận.",
            "risk_level": "R1",
        }
        errors, stats = validate_article_quality(article)
        self.assertEqual(stats["words"], 304)
        self.assertLess(stats["words"], minimum_words_for_type("short_explainer"))
        self.assertLess(stats["words"], target_word_range_for_type("short_explainer")[0])
        self.assertTrue(any("cần ít nhất 500" in error for error in errors))

    def test_primary_source_type_is_not_overbroad(self):
        self.assertTrue(is_primary_source_type('Cổng thông tin chính thức'))
        self.assertFalse(is_primary_source_type('Viện nghiên cứu'))
        self.assertFalse(is_primary_source_type('Tạp chí khoa học'))
        self.assertFalse(is_primary_source_type('Tổ chức quốc tế'))

    def test_ttl_policy_is_type_and_risk_specific(self):
        self.assertEqual(ttl_for_data_type('market_price','R1'),2)
        self.assertEqual(ttl_for_data_type('historical','R1'),8760)
        self.assertEqual(ttl_for_data_type('historical','R3'),6)

    def test_commercial_license_whitelist_rejects_nc_and_nd(self):
        self.assertTrue(is_commercial_license('CC BY 4.0'))
        self.assertTrue(is_commercial_license('CC0 1.0'))
        self.assertFalse(is_commercial_license('CC BY-NC-SA 4.0'))
        self.assertFalse(is_commercial_license('CC BY-ND 4.0'))
        self.assertFalse(is_commercial_license('Unknown license'))

    def test_domain_key_normalizes_www_and_country_domains(self):
        self.assertEqual(domain_key("https://www.bbc.co.uk/news"),"bbc.co.uk")
        self.assertEqual(domain_key("https://www.nasa.gov/news"),"nasa.gov")

    def test_fact_ledger_rejects_unlisted_url(self):
        allowed=["https://example.com/a"]
        ledger=[{"claim":"Một dữ kiện đủ dài để kiểm tra trong nguồn","source_urls":["https://evil.example/a"]}]*3
        errors=validate_fact_ledger(ledger,allowed)
        self.assertTrue(any("URL ngoài" in x for x in errors))

    def test_fact_ledger_requires_three_claims(self):
        self.assertTrue(validate_fact_ledger([{"claim":"Dữ kiện đủ dài để kiểm tra","source_urls":["https://example.com/a"]}],["https://example.com/a"]))

    def test_fact_ledger_requires_snippet_to_exist_verbatim_in_fetched_source(self):
        url="https://publisher.example/story"
        ledger=[
            {"claim":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.",
             "source_urls":[url],"evidence_snippet":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.","evidence_locator":"Đoạn 1"},
            {"claim":"Phạm vi dự án được mô tả trong thông báo chính thức.",
             "source_urls":[url],"evidence_snippet":"Phạm vi dự án được mô tả trong thông báo chính thức.","evidence_locator":"Đoạn 2"},
            {"claim":"Tiến độ dự kiến được nêu trong văn bản công bố.",
             "source_urls":[url],"evidence_snippet":"Tiến độ dự kiến được nêu trong văn bản công bố.","evidence_locator":"Đoạn 3"}
        ]
        page=("Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026. "
              "Phạm vi dự án được mô tả trong thông báo chính thức. "
              "Tiến độ dự kiến được nêu trong văn bản công bố.")
        errors,enriched=verify_fact_ledger_against_pages(ledger,[url],{url:page})
        self.assertEqual(errors,[])
        self.assertTrue(all(x["evidence_verifications"] for x in enriched))
        self.assertEqual(validate_fact_ledger_proof(enriched,[url]),[])
        # Recheck also applies to candidates already prepared by an older pipeline version.
        tampered=[dict(x) for x in enriched]
        tampered[0]=dict(tampered[0])
        tampered[0]["claim"]="Kế hoạch được cơ quan công bố vào ngày 31 tháng 10 năm 2026."
        self.assertTrue(validate_fact_ledger_proof(tampered,[url]))

    def test_core_fact_requires_two_independent_verified_source_families(self):
        from datetime import datetime, timezone
        from hashlib import sha256
        url1="https://one.example/a"; url2="https://two.example/b"
        snippet="Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026."
        page1=normalize_evidence_text(snippet); page2=normalize_evidence_text(snippet)
        ledger=[{
            "claim":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.",
            "source_urls":[url1,url2],"evidence_snippet":snippet,"importance":"core",
            "evidence_by_source":[{"source_url":url1,"snippet":snippet},{"source_url":url2,"snippet":snippet}]
        },{
            "claim":"Phạm vi dự án được mô tả trong thông báo chính thức.",
            "source_urls":[url1],"evidence_snippet":"Phạm vi dự án được mô tả trong thông báo chính thức.",
            "importance":"supporting"
        },{
            "claim":"Tiến độ dự kiến được nêu trong văn bản công bố.",
            "source_urls":[url1],"evidence_snippet":"Tiến độ dự kiến được nêu trong văn bản công bố.",
            "importance":"supporting"
        }]
        pages={url1:snippet+" Phạm vi dự án được mô tả trong thông báo chính thức. Tiến độ dự kiến được nêu trong văn bản công bố.",
               url2:snippet}
        errors,enriched=verify_fact_ledger_against_pages(ledger,[url1,url2],pages,
            source_families={url1:"shared-wire",url2:"shared-wire"})
        self.assertTrue(any("hai nguồn độc lập" in e for e in errors))
        errors,enriched=verify_fact_ledger_against_pages(ledger,[url1,url2],pages,
            source_families={url1:"family-one",url2:"family-two"})
        self.assertEqual(errors,[])
        self.assertEqual(validate_fact_ledger_proof(enriched,[url1,url2],
            source_families={url1:"family-one",url2:"family-two"}),[])

    def test_fact_ledger_rejects_fabricated_snippet_not_in_source_page(self):
        url="https://publisher.example/story"
        ledger=[
            {"claim":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.",
             "source_urls":[url],"evidence_snippet":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.","evidence_locator":"Đoạn 1"},
            {"claim":"Phạm vi dự án được mô tả trong thông báo chính thức.",
             "source_urls":[url],"evidence_snippet":"Phạm vi dự án được mô tả trong thông báo chính thức.","evidence_locator":"Đoạn 2"},
            {"claim":"Tiến độ dự kiến được nêu trong văn bản công bố.",
             "source_urls":[url],"evidence_snippet":"Tiến độ dự kiến được nêu trong văn bản công bố.","evidence_locator":"Đoạn 3"}
        ]
        errors,_=verify_fact_ledger_against_pages(ledger,[url],{url:"Trang nguồn chỉ nói về thời tiết và giao thông trong khu vực."})
        self.assertTrue(any("không có trích đoạn nguyên văn" in x for x in errors))

    def test_fact_ledger_rejects_claim_number_not_in_source_excerpt(self):
        url="https://publisher.example/story"
        ledger=[
            {"claim":"Cơ quan công bố kế hoạch với tổng vốn 31 tỷ đồng.",
             "source_urls":[url],"evidence_snippet":"Cơ quan công bố kế hoạch với tổng vốn 13 tỷ đồng.","evidence_locator":"Đoạn 1"},
            {"claim":"Phạm vi dự án được mô tả trong thông báo chính thức.",
             "source_urls":[url],"evidence_snippet":"Phạm vi dự án được mô tả trong thông báo chính thức.","evidence_locator":"Đoạn 2"},
            {"claim":"Tiến độ dự kiến được nêu trong văn bản công bố.",
             "source_urls":[url],"evidence_snippet":"Tiến độ dự kiến được nêu trong văn bản công bố.","evidence_locator":"Đoạn 3"}
        ]
        page=" ".join(x["evidence_snippet"] for x in ledger)
        errors,_=verify_fact_ledger_against_pages(ledger,[url],{url:page})
        self.assertTrue(any("không có trích đoạn nguyên văn" in x for x in errors))


    def test_fact_ledger_rejects_swapped_subject_and_object_even_when_all_tokens_match(self):
        url="https://publisher.example/story"
        page=(
            "Công ty A mua Công ty B vào ngày 31 tháng 10 năm 2026. "
            "Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026. "
            "Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026."
        )
        ledger=[
            {"claim":"Công ty B mua Công ty A vào ngày 31 tháng 10 năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty A mua Công ty B vào ngày 31 tháng 10 năm 2026.",
             "evidence_locator":"Đoạn 1"},
            {"claim":"Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026.",
             "evidence_locator":"Đoạn 2"},
            {"claim":"Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026.",
             "evidence_locator":"Đoạn 3"}
        ]
        errors,_=verify_fact_ledger_against_pages(ledger,[url],{url:page})
        self.assertTrue(any("thứ tự/quan hệ" in e for e in errors))


    def test_fact_ledger_rejects_opposite_direction_even_when_numbers_match(self):
        url="https://publisher.example/earnings"
        page=(
            "Doanh thu của doanh nghiệp tăng 12 phần trăm trong quý ba năm 2026. "
            "Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026. "
            "Phạm vi dự án được mô tả trong thông báo chính thức."
        )
        ledger=[
            {"claim":"Doanh thu của doanh nghiệp giảm 12 phần trăm trong quý ba năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Doanh thu của doanh nghiệp tăng 12 phần trăm trong quý ba năm 2026.",
             "evidence_locator":"Đoạn 1"},
            {"claim":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Cơ quan công bố kế hoạch vào ngày 31 tháng 10 năm 2026.",
             "evidence_locator":"Đoạn 2"},
            {"claim":"Phạm vi dự án được mô tả trong thông báo chính thức.",
             "source_urls":[url],
             "evidence_snippet":"Phạm vi dự án được mô tả trong thông báo chính thức.",
             "evidence_locator":"Đoạn 3"}
        ]
        errors,_=verify_fact_ledger_against_pages(ledger,[url],{url:page})
        self.assertTrue(any("thứ tự/quan hệ" in e for e in errors))

    def test_fact_ledger_accepts_same_direction_claim(self):
        url="https://publisher.example/story"
        page=(
            "Công ty A mua Công ty B vào ngày 31 tháng 10 năm 2026. "
            "Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026. "
            "Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026."
        )
        ledger=[
            {"claim":"Công ty A mua Công ty B vào ngày 31 tháng 10 năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty A mua Công ty B vào ngày 31 tháng 10 năm 2026.",
             "evidence_locator":"Đoạn 1"},
            {"claim":"Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty C công bố kế hoạch đầu tư vào ngày 1 tháng 11 năm 2026.",
             "evidence_locator":"Đoạn 2"},
            {"claim":"Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026.",
             "source_urls":[url],
             "evidence_snippet":"Công ty D ghi nhận doanh thu tăng 12 phần trăm trong quý ba năm 2026.",
             "evidence_locator":"Đoạn 3"}
        ]
        errors,enriched=verify_fact_ledger_against_pages(ledger,[url],{url:page})
        self.assertEqual(errors,[])
        self.assertTrue(all(x.get("evidence_verifications") for x in enriched))

    def test_article_body_rejects_numeric_fact_missing_from_ledger(self):
        article=self.sample_article()
        article["fact_ledger"]=[
            {"claim":"Một dữ kiện cốt lõi được ghi nhận với con số 12."}
        ]
        article["body"][0]="Báo cáo ghi nhận mức tăng 35 phần trăm trong quý ba."
        errors,_=validate_article_quality(article,min_words=50,min_paragraphs=6)
        self.assertTrue(any("số liệu/ngày tháng chưa xuất hiện" in e for e in errors))

    def test_primary_candidate_is_recognized_for_research_preflight(self):
        count,has_primary,_=source_independence([
            {"url":"https://official.example/notice","is_primary":True,
             "is_primary_for_claim":True}
        ])
        self.assertEqual(count,1)
        self.assertTrue(has_primary)

    def test_quality_gate_accepts_nonrepetitive_article(self):
        article=self.sample_article()
        errors,stats=validate_article_quality(article,min_words=50,min_paragraphs=6)
        self.assertEqual(errors,[])
        self.assertGreaterEqual(stats["unique_paragraph_ratio"],0.85)

    def test_quality_gate_flags_generic_filler(self):
        article=self.sample_article()
        article["body"][0]="Đây là điểm quan trọng khi đánh giá thông tin. "+article["body"][0]
        errors,_=validate_article_quality(article,min_words=50,min_paragraphs=6)
        self.assertTrue(any("khuôn mẫu" in x for x in errors))

    def test_risk_classification_escalates_financial_advice(self):
        self.assertEqual(classify_risk("Khuyến nghị đầu tư cổ phiếu",["Nên mua cổ phiếu ngay"],"world"),"R3")


    def test_core_fact_requires_independent_corroboration_when_multiple_sources_exist(self):
        allowed=["https://one.example/a","https://two.example/b"]
        ledger=[
            {"claim":"Dữ kiện cốt lõi đủ dài để kiểm tra trong nguồn.","source_urls":[allowed[0]],"evidence_snippet":"Dữ kiện cốt lõi đủ dài để kiểm tra trong nguồn.","importance":"core"},
            {"claim":"Dữ kiện hỗ trợ thứ hai có căn cứ rõ ràng.","source_urls":[allowed[0]],"evidence_snippet":"Dữ kiện hỗ trợ thứ hai có căn cứ rõ ràng.","importance":"supporting"},
            {"claim":"Dữ kiện hỗ trợ thứ ba có căn cứ rõ ràng.","source_urls":[allowed[1]],"evidence_snippet":"Dữ kiện hỗ trợ thứ ba có căn cứ rõ ràng.","importance":"supporting"}
        ]
        errors=validate_fact_ledger(ledger,allowed)
        self.assertTrue(any("chưa được đối chiếu độc lập" in x for x in errors))

    def test_core_fact_from_primary_source_can_stand_alone(self):
        url="https://official.example/notice"
        ledger=[
            {"claim":"Dữ kiện cốt lõi được công bố trong văn bản chính thức.","source_urls":[url],"evidence_snippet":"Dữ kiện cốt lõi được công bố trong văn bản chính thức.","importance":"core"},
            {"claim":"Dữ kiện hỗ trợ thứ hai được ghi trong cùng văn bản.","source_urls":[url],"evidence_snippet":"Dữ kiện hỗ trợ thứ hai được ghi trong cùng văn bản.","importance":"supporting"},
            {"claim":"Dữ kiện hỗ trợ thứ ba được ghi trong cùng văn bản.","source_urls":[url],"evidence_snippet":"Dữ kiện hỗ trợ thứ ba được ghi trong cùng văn bản.","importance":"supporting"}
        ]
        self.assertEqual(validate_fact_ledger(ledger,[url],primary_urls=[url]),[])


    def test_source_page_must_match_topic_title(self):
        from content_quality import evidence_matches_title
        self.assertTrue(evidence_matches_title("NASA công bố sứ mệnh nghiên cứu Mặt Trăng","NASA công bố sứ mệnh nghiên cứu Mặt Trăng với lịch trình mới."))
        self.assertFalse(evidence_matches_title("NASA công bố sứ mệnh nghiên cứu Mặt Trăng","Một giải đấu bóng đá diễn ra cuối tuần này."))
        # Two generic shared words are not enough to establish page relevance.
        self.assertFalse(evidence_matches_title(
            "Sunoco faces earnings test after profit miss revenue drop ahead",
            "A report says earnings may drop after a test, but it concerns an unrelated sports team."
        ))

    def test_r3_personal_advice_is_flagged(self):
        from content_quality import validate_r3_content
        self.assertTrue(validate_r3_content("Tin về thị trường",["Bạn nên mua cổ phiếu ngay hôm nay."]))

    def test_syndicated_domains_in_same_family_count_as_one_source(self):
        refs=[
            {"url":"https://paper-one.example/story","source_family":"shared-wire"},
            {"url":"https://paper-two.example/story","source_family":"shared-wire"},
            {"url":"https://independent.example/story","source_family":"independent"}
        ]
        count,primary,families=source_independence(refs)
        self.assertEqual(count,2)
        self.assertEqual(set(families),{"shared-wire","independent"})

    def test_source_independence_counts_distinct_domains(self):
        refs=[
            {"url":"https://www.bbc.co.uk/news","is_primary":False},
            {"url":"https://www.reuters.com/world","is_primary":False},
            {"url":"https://www.nasa.gov/news","is_primary":True,"is_primary_for_claim":True}
        ]
        count,primary,domains=source_independence(refs)
        self.assertEqual(count,3)
        self.assertTrue(primary)

if __name__=="__main__":
    unittest.main()
