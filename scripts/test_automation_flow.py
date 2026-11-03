"""End-to-end offline simulation of RSS discovery -> research -> ready queue -> publish."""
import json, os, tempfile, unittest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import news_pipeline
import publish_ready
import write_candidates

class AutomaticResearchPublishFlowTests(unittest.TestCase):
    def test_research_stages_candidate_without_calling_ai_or_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            cfg=base/'config'; data=base/'data'
            cfg.mkdir(); data.mkdir()
            now=datetime.now(timezone.utc)
            pub=now-timedelta(minutes=10)
            feeds=[{
                'name':'Example RSS','url':'https://publisher-one.example/rss','category':'vietnam',
                'enabled':True,'status':'discovery_only','discovery_access_status':'DISCOVERY_ONLY',
                'terms_status':'UNVERIFIED','commercial_use_status':'UNVERIFIED'
            }]
            (cfg/'feeds.json').write_text(json.dumps(feeds),encoding='utf-8')
            (data/'articles.json').write_text('[]',encoding='utf-8')
            (data/'archive_articles.json').write_text('[]',encoding='utf-8')
            (data/'archive_catalog.json').write_text('[]',encoding='utf-8')
            (data/'pending.json').write_text('[]',encoding='utf-8')
            (data/'research_queue.json').write_text('[]',encoding='utf-8')
            (data/'seen_items.json').write_text('{"items":{},"last_run":null}',encoding='utf-8')
            (data/'publish_log.json').write_text('[]',encoding='utf-8')

            rss=(f'<rss version="2.0"><channel>'
                 f'<item><title>Việt Nam công bố kế hoạch mở rộng giao thông công cộng</title>'
                 f'<link>https://publisher-one.example/story</link><pubDate>{format_datetime(pub)}</pubDate></item>'
                 f'<item><title>Việt Nam công bố kế hoạch mở rộng giao thông công cộng với chi tiết mới</title>'
                 f'<link>https://publisher-two.example/story</link><pubDate>{format_datetime(pub)}</pubDate></item>'
                 f'</channel></rss>').encode()
            evidence=("Việt Nam công bố kế hoạch mở rộng giao thông công cộng. "
                      "Thông tin nêu cơ quan thực hiện, phạm vi dự án, thời điểm công bố và tiến độ dự kiến. "
                      "Các nội dung này được trình bày trong thông báo công khai, có thể đối chiếu với tài liệu gốc. "
                      "Kế hoạch mở rộng giao thông công cộng được công bố trong ngày 31 tháng 10. "
                      "Phạm vi dự án được mô tả trong thông báo công khai của cơ quan thực hiện. "
                      "Tiến độ dự kiến được nêu trong thông tin công bố về kế hoạch. ")*12
            paragraph_seed=("Bài viết phân tích kế hoạch giao thông công cộng dựa trên các dữ kiện đã công bố. "
                            "Phần này giải thích bối cảnh, phạm vi triển khai và trách nhiệm của cơ quan liên quan. "
                            "Các thông tin được phân biệt giữa nội dung đã xác nhận và chi tiết chưa có tài liệu độc lập. ")
            body=[
                f"Đoạn {i+1}. {paragraph_seed} "
                + [
                    "Phần thứ nhất làm rõ thời điểm công bố và mục tiêu của kế hoạch.",
                    "Phần thứ hai phân tích phạm vi địa lý và nhóm người sử dụng được đề cập.",
                    "Phần thứ ba đối chiếu tiến độ dự kiến với trách nhiệm thực hiện.",
                    "Phần thứ tư nêu giới hạn dữ liệu và những nội dung chưa được xác nhận.",
                    "Phần cuối đánh giá tác động có thể kiểm chứng từ các thông tin đã công bố."
                ][i]
                + (" Các dữ kiện được trình bày theo trình tự, không suy đoán thêm nguyên nhân hoặc kết quả. " * 5)
                for i in range(5)
            ]
            urls=['https://publisher-one.example/story','https://publisher-two.example/story']
            def source_info_test(url):
                from urllib.parse import urlsplit
                host=urlsplit(url).hostname or ''
                return {'name':host,'source_type':'Báo chí','is_primary':False,
                        'is_primary_for_claim':False,'source_family':host,
                        'directory_access_status':'not_listed' if host=='publisher-one.example' else 'listed',
                        'access_status':'UNVERIFIED','terms_status':'UNVERIFIED',
                        'commercial_use_status':'UNVERIFIED','terms_url':'','robots_url':'',
                        'allowed_fields':'','license_notes':'Unverified'}
            ai_result={
                'publish':True,
                'title':'Việt Nam công bố kế hoạch mở rộng giao thông công cộng',
                'summary':'Kế hoạch mới xác định phạm vi mở rộng và các mốc triển khai; một số chi tiết cần tiếp tục đối chiếu.',
                'category':'vietnam','seo_title':'Kế hoạch mở rộng giao thông công cộng',
                'meta_description':'Các dữ kiện chính về kế hoạch mở rộng giao thông công cộng.',
                'keywords':['giao thông công cộng','mở rộng','Việt Nam','kế hoạch'],
                'body':body,'source_index':0,'content_type':'short_explainer','data_type':'general',
                'editorial_value':'Bài viết đối chiếu hai nguồn độc lập để làm rõ phạm vi thông tin. Phần phân tích chỉ ra những chi tiết đã xác nhận và các giới hạn còn lại.',
                'risk_level':'R1','freshness_ttl_hours':24,
                'fact_ledger':[
                    {'claim':'Kế hoạch mở rộng giao thông công cộng được công bố trong ngày 31 tháng 10.',
                     'source_urls':urls,'evidence_snippet':'Kế hoạch mở rộng giao thông công cộng được công bố trong ngày 31 tháng 10.','evidence_locator':'Đoạn mở đầu'},
                    {'claim':'Phạm vi dự án được mô tả trong thông báo công khai của cơ quan thực hiện.',
                     'source_urls':urls,'evidence_snippet':'Phạm vi dự án được mô tả trong thông báo công khai của cơ quan thực hiện.','evidence_locator':'Mục phạm vi dự án'},
                    {'claim':'Tiến độ dự kiến được nêu trong thông tin công bố về kế hoạch.',
                     'source_urls':[urls[0]],'evidence_snippet':'Tiến độ dự kiến được nêu trong thông tin công bố về kế hoạch.','evidence_locator':'Mục tiến độ'}
                ]
            }

            env={
                'GEMINI_API_KEY':'mock-key',
                'NEWS_PUBLIC_FACTUAL_RESEARCH':'1',
                'NEWS_INITIAL_WINDOW_START':(now-timedelta(hours=2)).isoformat()
            }
            with patch.object(news_pipeline,'ROOT',base), \
                 patch.object(news_pipeline,'FEEDS',cfg/'feeds.json'), \
                 patch.object(news_pipeline,'ARTICLES',data/'articles.json'), \
                 patch.object(news_pipeline,'ARCHIVE',data/'archive_articles.json'), \
                 patch.object(news_pipeline,'PENDING',data/'pending.json'), \
                 patch.object(news_pipeline,'SEEN',data/'seen_items.json'), \
                 patch.object(news_pipeline,'RESEARCH_QUEUE',data/'research_queue.json'), \
                 patch.object(news_pipeline,'robots_allowed',return_value=True), \
                 patch.object(news_pipeline,'fetch',return_value=rss), \
                 patch.object(news_pipeline,'research_access_mode',return_value='LIMITED_FACTUAL_REFERENCE'), \
                 patch.object(news_pipeline,'source_info',side_effect=source_info_test), \
                 patch.object(news_pipeline,'extract_page',return_value=evidence), \
                 patch.object(news_pipeline,'generate_with_fallback',side_effect=AssertionError('Research must not call AI')), \
                 patch.object(news_pipeline,'find_licensed_image',return_value=None), \
                 patch.dict(os.environ,env,clear=False):
                news_pipeline.main()

            queue=json.loads((data/'research_queue.json').read_text(encoding='utf-8'))
            self.assertEqual(len(queue),1)
            self.assertEqual(queue[0]['status'],'WRITING_PENDING')
            self.assertIn('group',queue[0])
            self.assertIn('evidence_pages',queue[0])
            self.assertFalse(queue[0].get('article'))
            published=json.loads((data/'articles.json').read_text(encoding='utf-8'))
            self.assertEqual(published,[])


    def test_writing_preserves_research_sealed_multilingual_sources(self):
        candidate={
            "lead_title":"NASA centre anniversary and historical programme",
            "group":[
                {"source_url":"https://fr.example/story","source_name":"French source",
                 "discovery_title":"Le centre spatial célèbre son anniversaire"},
                {"source_url":"https://jp.example/story","source_name":"Japanese source",
                 "discovery_title":"宇宙センターが設立記念日を迎える"}
            ],
            "evidence_pages":{
                "https://fr.example/story":"Le centre spatial célèbre son anniversaire et rappelle sa création.",
                "https://jp.example/story":"宇宙センターは設立記念日を迎え、歴史を振り返った。"
            },
            "research_dossier":{"source_inventory":[
                {"url":"https://fr.example/story","family":"fr-example","is_primary":False},
                {"url":"https://jp.example/story","family":"jp-example","is_primary":False}
            ]}
        }
        group,evidence,independent,has_primary=write_candidates._filter_candidate_evidence(candidate)
        self.assertEqual(len(group),2)
        self.assertEqual(len(evidence),2)
        self.assertEqual(independent,2)
        self.assertFalse(has_primary)

    def test_researched_multilingual_dossier_can_be_written_without_second_evidence_gate(self):
        url1="https://alpha.example/report"
        url2="https://beta.example/report"
        excerpts=[
            (url1,"The ministry confirmed that the programme will begin in the northern region."),
            (url2,"Local authorities described the implementation schedule and participating agencies."),
            (url1,"The published plan sets out the programme's initial scope and review process.")
        ]
        group=[
            {"source_url":url1,"source_name":"Alpha","discovery_title":"Programme implementation update",
             "source_published_at":"2026-11-03T08:00:00+00:00","research_mode":"LIMITED_FACTUAL_REFERENCE"},
            {"source_url":url2,"source_name":"Beta","discovery_title":"Programme implementation schedule",
             "source_published_at":"2026-11-03T08:10:00+00:00","research_mode":"LIMITED_FACTUAL_REFERENCE"}
        ]
        pages={url1:excerpts[0][1]+" "+excerpts[2][1],url2:excerpts[1][1]}
        ledger=[]
        claims=[
            "Cơ quan quản lý xác nhận chương trình sẽ bắt đầu tại khu vực phía bắc.",
            "Chính quyền địa phương mô tả lịch triển khai và các cơ quan tham gia.",
            "Kế hoạch công bố nêu phạm vi ban đầu và quy trình rà soát chương trình."
        ]
        for claim,(url,excerpt) in zip(claims,excerpts):
            ledger.append({"claim":claim,"source_claim":excerpt,"source_urls":[url],
                           "evidence_snippet":excerpt,"evidence_locator":"paragraph 1",
                           "evidence_by_source":[{"source_url":url,"snippet":excerpt,"locator":"paragraph 1"}],
                           "importance":"core"})
        body=[
            "Thông tin được công bố cho thấy chương trình đã bước sang giai đoạn triển khai cụ thể. Cơ quan quản lý xác nhận phạm vi khởi động tại khu vực phía bắc, trong khi tài liệu liên quan mô tả cách các đơn vị địa phương tham gia thực hiện. Những dữ kiện này giúp xác định đây là kế hoạch có phạm vi và đầu mối triển khai, thay vì một đề xuất mới dừng ở mức định hướng.",
            "Lịch thực hiện và danh sách cơ quan tham gia là hai nội dung cần được đọc cùng nhau. Lịch cho biết trình tự tổ chức, còn vai trò của các đơn vị địa phương cho thấy trách nhiệm triển khai được phân bổ ở cấp thực hiện. Hồ sơ công bố cũng nêu phạm vi ban đầu và quy trình rà soát, qua đó xác định những nội dung sẽ được xem xét trong quá trình thực hiện.",
            "Tuy nhiên, các tài liệu hiện có chưa cung cấp đầy đủ kết quả triển khai thực tế hoặc đánh giá tác động sau khi chương trình vận hành. Vì vậy, có thể xác nhận phạm vi, lịch trình và cơ chế tổ chức đã được mô tả, nhưng chưa nên kết luận về hiệu quả cuối cùng. Những kết quả tiếp theo cần được đánh giá dựa trên báo cáo thực hiện và dữ liệu được công bố sau đó."
        ]
        obj={"publish":True,"title":"Chương trình mới bước vào giai đoạn triển khai",
             "summary":"Hồ sơ công bố xác định phạm vi khởi động, lịch thực hiện và vai trò của các cơ quan địa phương.",
             "category":"vietnam","content_type":"quick_update","body":body,
             "editorial_value":"Bài viết phân biệt phạm vi đã được công bố với kết quả triển khai thực tế. Bài cũng làm rõ vai trò của lịch trình và các đơn vị địa phương trong hồ sơ.",
             "risk_level":"R1","fact_ledger":ledger,"source_index":0}
        article=news_pipeline.make_article(obj,group,pages)
        self.assertIsNotNone(article)
        self.assertGreaterEqual(article["word_count"],180)
        self.assertEqual(len(article["fact_ledger"]),3)

    def test_research_workflow_commits_pending_feedback_from_embedded_writer(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/research-news.yml').read_text(encoding='utf-8')
        self.assertIn('git add data/research_queue.json data/pending.json data/seen_items.json',workflow)


if __name__=='__main__':
    unittest.main(verbosity=2)
