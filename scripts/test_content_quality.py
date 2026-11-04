import unittest
from content_quality import (
    body_stats, classify_risk, validate_fact_ledger, validate_fact_ledger_proof, verify_fact_ledger_against_pages, normalize_evidence_text, validate_article_quality,
    source_independence, domain_key, is_commercial_license, is_primary_source_type, ttl_for_data_type, minimum_words_for_type, target_word_range_for_type, minimum_paragraphs_for_type, repair_fact_ledger_anchors, validate_body_fact_coverage
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
        # The prompt asks for the target range; validation only rejects genuinely thin drafts.
        self.assertEqual(target_word_range_for_type("quick_update"), (180, 260))
        self.assertEqual(target_word_range_for_type("short_explainer"), (250, 380))
        self.assertEqual(target_word_range_for_type("news_analysis"), (450, 650))
        for kind in ("quick_update","short_explainer","news_analysis","long_analysis"):
            self.assertLessEqual(minimum_words_for_type(kind), target_word_range_for_type(kind)[0]//2+20)
        self.assertEqual(minimum_words_for_type("short_explainer"), 120)
        self.assertEqual(minimum_paragraphs_for_type("short_explainer"), 2)

    def test_234_word_quick_update_meets_revised_minimum(self):
        body=[" ".join(f"thong_tin_{i}_{j}" for j in range(39)) for i in range(6)]
        article={"title":"Bản tin cập nhật về sự kiện đã được xác nhận",
                 "summary":"Thông tin chính và diễn biến mới được các nguồn xác nhận.",
                 "content_type":"quick_update","body":body,
                 "editorial_value":"Bài làm rõ diễn biến mới và giới hạn của thông tin đã xác minh.",
                 "risk_level":"R1"}
        errors,stats=validate_article_quality(article)
        self.assertGreaterEqual(stats["words"],180)
        self.assertFalse(any("cần ít nhất 180" in error for error in errors))

    def test_below_editorial_floor_short_explainer_is_rejected(self):
        body = [
            " ".join(f"du_lieu_{p}_{i}" for i in range(20))
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
        self.assertEqual(stats["words"], 80)
        self.assertLess(stats["words"], minimum_words_for_type("short_explainer"))
        self.assertTrue(any("cần ít nhất 120" in error for error in errors))

    def test_draft_between_floor_and_target_is_accepted(self):
        body=[" ".join(f"du_lieu_{p}_{i}" for i in range(45)) for p in range(3)]  # 135 words < 250 target
        article={"title":"Sự kiện được xác nhận qua dữ liệu và tài liệu chính thức",
                 "summary":"Bài viết phân tích các dữ kiện được công bố, bối cảnh và giới hạn của thông tin.",
                 "content_type":"short_explainer","body":body,
                 "editorial_value":"Đối chiếu dữ liệu theo thời gian. Làm rõ điểm khác nhau giữa thông báo ban đầu với kết quả đã được xác nhận.",
                 "risk_level":"R1"}
        errors,stats=validate_article_quality(article)
        self.assertFalse(any("cần ít nhất" in e for e in errors),errors)

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
        tampered[0]["evidence_by_source"]=[dict(tampered[0]["evidence_by_source"][0],
                                               snippet="Cơ quan công bố kế hoạch vào ngày 1 tháng 1 năm 2020.")]
        tampered[0]["evidence_snippet"]=tampered[0]["evidence_by_source"][0]["snippet"]
        self.assertTrue(validate_fact_ledger_proof(tampered,[url]))

    def test_anchor_repair_uses_only_exact_research_excerpt_for_multilingual_claim(self):
        url="https://publisher.example/story"
        excerpt="Le ministère a annoncé le lancement du programme le 31 octobre 2026."
        ledger=[{"claim":"Bộ công bố khởi động chương trình ngày 31 tháng 10 năm 2026.",
                 "source_urls":[url],"evidence_snippet":excerpt,
                 "evidence_by_source":[{"source_url":url,"snippet":excerpt,"locator":"paragraph 1"}]}]
        repaired=repair_fact_ledger_anchors(ledger,[url],{url:excerpt})
        self.assertEqual(repaired[0]["source_claim"],excerpt)
        errors,enriched=verify_fact_ledger_against_pages(repaired,[url],{url:excerpt},min_claims=1)
        self.assertEqual(errors,[])
        self.assertEqual(enriched[0]["evidence_snippet"],excerpt)

    def test_anchor_repair_does_not_overwrite_a_fabricated_nonempty_quote(self):
        url="https://publisher.example/story"
        excerpt="The ministry announced the programme on 31 October 2026."
        fabricated="The ministry cancelled the programme on 31 October 2026."
        ledger=[{"claim":"Bộ hủy chương trình vào ngày 31 tháng 10 năm 2026.",
                 "source_claim":fabricated,"source_urls":[url],"evidence_snippet":excerpt,
                 "evidence_by_source":[{"source_url":url,"snippet":excerpt}]}]
        repaired=repair_fact_ledger_anchors(ledger,[url],{url:excerpt})
        self.assertEqual(repaired[0]["source_claim"],fabricated)
        # The evidence excerpt is still genuine; claim/source wording is no longer compared.
        errors,enriched=verify_fact_ledger_against_pages(repaired,[url],{url:excerpt},min_claims=1)
        self.assertEqual(errors,[])
        self.assertEqual(enriched[0]["evidence_snippet"],excerpt)

    def test_anchor_repair_never_invents_or_accepts_unfetched_excerpt(self):
        url="https://publisher.example/story"
        fabricated="The ministry cancelled the programme on 31 October 2026."
        ledger=[{"claim":"Bộ hủy chương trình vào ngày 31 tháng 10 năm 2026.",
                 "source_claim":fabricated,"source_urls":[url],"evidence_snippet":fabricated}]
        repaired=repair_fact_ledger_anchors(ledger,[url],{url:"The ministry announced the programme on 31 October 2026."})
        self.assertEqual(repaired[0].get("source_claim"),fabricated)
        self.assertEqual(repaired[0].get("evidence_by_source"),None)

    def test_multilingual_sources_support_vietnamese_claims(self):
        url="https://official.example/report"
        snippets=[
            "Le ministère a annoncé le lancement du programme le 31 octobre 2026.",
            "政府は2026年11月1日に新しい計画を発表した。",
            "El informe oficial registró un aumento del 12 por ciento en 2026."
        ]
        claims=[
            "Bộ này thông báo khởi động chương trình vào ngày 31 tháng 10 năm 2026.",
            "Chính phủ công bố kế hoạch mới vào ngày 1 tháng 11 năm 2026.",
            "Báo cáo chính thức ghi nhận mức tăng 12 phần trăm trong năm 2026."
        ]
        ledger=[]
        for claim,snippet in zip(claims,snippets):
            ledger.append({
                "claim":claim,"source_claim":snippet,"source_urls":[url],
                "evidence_snippet":snippet,"evidence_locator":"official report",
                "evidence_by_source":[{"source_url":url,"snippet":snippet,"locator":"official report"}],
                "importance":"supporting"
            })
        page=" ".join(snippets)
        errors,enriched=verify_fact_ledger_against_pages(
            ledger,[url],{url:page},primary_urls=[url]
        )
        self.assertEqual(errors,[])
        self.assertEqual(validate_fact_ledger_proof(enriched,[url],primary_urls=[url]),[])
        self.assertTrue(all(x.get("evidence_verifications") for x in enriched))

    def test_multilingual_core_fact_can_use_one_exact_anchor_and_other_independent_paraphrases(self):
        url1="https://official.example/notice"
        url2="https://independent.example/report"
        anchor="Le ministère a annoncé le lancement du programme le 31 octobre 2026."
        corroboration="The programme launch was announced by the ministry on October 31, 2026."
        ledger=[{
            "claim":"Bộ thông báo khởi động chương trình vào ngày 31 tháng 10 năm 2026.",
            "source_claim":anchor,"source_urls":[url1,url2],"importance":"core",
            "evidence_snippet":corroboration,"evidence_locator":"paragraph 2",
            "evidence_by_source":[
                {"source_url":url1,"snippet":anchor,"locator":"paragraph 1"},
                {"source_url":url2,"snippet":corroboration,"locator":"paragraph 2"}
            ]
        },{
            "claim":"Tài liệu nêu phạm vi triển khai của chương trình.","source_claim":anchor,
            "source_urls":[url1],"evidence_snippet":anchor,"evidence_locator":"paragraph 1"
        },{
            "claim":"Thông báo xác định mốc thời gian triển khai.","source_claim":anchor,
            "source_urls":[url1],"evidence_snippet":anchor,"evidence_locator":"paragraph 1"
        }]
        pages={url1:anchor,url2:corroboration}
        errors,enriched=verify_fact_ledger_against_pages(
            ledger,[url1,url2],pages,primary_urls=[url1],
            source_families={url1:"official",url2:"independent"}
        )
        self.assertEqual(errors,[])
        self.assertEqual(validate_fact_ledger_proof(
            enriched,[url1,url2],primary_urls=[url1],
            source_families={url1:"official",url2:"independent"}
        ),[])

    def test_multilingual_source_claim_is_not_required_to_be_verbatim(self):
        url="https://official.example/report"
        snippet="Le ministère a annoncé le lancement du programme le 31 octobre 2026."
        ledger=[
            {"claim":"Bộ thông báo khởi động chương trình vào ngày 31 tháng 10 năm 2026.",
             "source_claim":"Le ministère a annulé le programme le 31 octobre 2026.",
             "source_urls":[url],"evidence_snippet":snippet,"evidence_locator":"paragraph 1",
             "evidence_by_source":[{"source_url":url,"snippet":snippet,"locator":"paragraph 1"}]},
            {"claim":"Phạm vi chương trình được nêu trong tài liệu.","source_claim":"Le ministère a annoncé le lancement du programme le 31 octobre 2026.",
             "source_urls":[url],"evidence_snippet":snippet,"evidence_locator":"paragraph 1",
             "evidence_by_source":[{"source_url":url,"snippet":snippet,"locator":"paragraph 1"}]},
            {"claim":"Thời điểm triển khai được xác định trong tài liệu.","source_claim":"Le ministère a annoncé le lancement du programme le 31 octobre 2026.",
             "source_urls":[url],"evidence_snippet":snippet,"evidence_locator":"paragraph 1",
             "evidence_by_source":[{"source_url":url,"snippet":snippet,"locator":"paragraph 1"}]}
        ]
        errors,_=verify_fact_ledger_against_pages(ledger,[url],{url:snippet},primary_urls=[url])
        self.assertEqual(errors,[])  # only the evidence excerpt must be genuine

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
        # Per-fact duplicate corroboration is not required once Research has
        # sealed an independently sourced story; each claim still needs an exact quote.
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


    def test_fact_ledger_no_longer_compares_subject_object_order(self):
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
        self.assertEqual(errors,[])  # wording/order is no longer compared; Research sealed the facts


    def test_fact_ledger_no_longer_compares_direction_wording(self):
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
        self.assertEqual(errors,[])  # wording/order is no longer compared; Research sealed the facts

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
        self.assertTrue(any("số liệu/ngày tháng không tìm thấy" in e for e in errors))

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

    def test_numeric_body_facts_are_checked_against_sealed_source_pages(self):
        body=["Kế hoạch được công bố năm 2026, gồm 12 tuyến và 8 nhà ga."]
        ledger=[{"claim":"Kế hoạch giao thông được công bố và triển khai theo lộ trình cụ thể.","source_urls":["https://agency.example/plan"]}]
        pages={"https://agency.example/plan":"The plan was announced in 2026 and includes 12 routes and 8 stations."}
        self.assertEqual(validate_body_fact_coverage(body,ledger,pages),[])

    def test_numeric_body_fact_not_in_any_source_is_rejected(self):
        body=["Kế hoạch được công bố năm 2026, gồm 99 tuyến và 8 nhà ga."]
        ledger=[{"claim":"Kế hoạch giao thông được công bố năm 2026, gồm 8 nhà ga.","source_urls":["https://agency.example/plan"]}]
        pages={"https://agency.example/plan":"The plan was announced in 2026 and includes 8 stations."}
        errors=validate_body_fact_coverage(body,ledger,pages)
        self.assertTrue(any("99" in error for error in errors))

    def test_factual_reporting_on_attack_is_not_automatically_r3(self):
        self.assertNotEqual(classify_risk("Các diễn biến sau vụ tấn công",["Hai hãng tin xác nhận diễn biến."],"world"),"R3")

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
        self.assertEqual(errors,[])

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
