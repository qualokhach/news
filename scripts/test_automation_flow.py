"""End-to-end offline simulation of RSS discovery -> research -> ready queue -> publish."""
import json, os, tempfile, unittest
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

import news_pipeline
import publish_ready

class AutomaticResearchPublishFlowTests(unittest.TestCase):
    def test_candidate_can_be_researched_queued_and_published(self):
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
                      "Tiến độ dự kiến được nêu trong thông tin công bố về kế hoạch. ")*5
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
                 patch.object(news_pipeline,'generate_with_fallback',return_value=(ai_result,'Gemini:gemini-3.5-flash-lite')), \
                 patch.object(news_pipeline,'find_licensed_image',return_value=None), \
                 patch.dict(os.environ,env,clear=False):
                news_pipeline.main()

            queue=json.loads((data/'research_queue.json').read_text(encoding='utf-8'))
            self.assertEqual(len(queue),1)
            self.assertEqual(queue[0]['status'],'READY')
            article=queue[0]['article']
            self.assertEqual(article['quality_status'],'PASS')
            self.assertEqual(len(article['source_references']),2)
            self.assertTrue(all(x['research_mode']=='LIMITED_FACTUAL_REFERENCE' for x in article['source_references']))
            self.assertTrue(all(x['reuse_mode']=='FACTUAL_CITATION_ONLY' for x in article['source_references']))

            with patch.object(publish_ready,'QUEUE',data/'research_queue.json'), \
                 patch.object(publish_ready,'ARTICLES',data/'articles.json'), \
                 patch.object(publish_ready,'PENDING',data/'pending.json'), \
                 patch.object(publish_ready,'SEEN',data/'seen_items.json'), \
                 patch.object(publish_ready,'LOG',data/'publish_log.json'), \
                 patch.object(publish_ready,'check_source_access',return_value=(True,'HTTP 200')), \
                 patch.object(publish_ready.research_pipeline,'extract_page',return_value=evidence):
                publish_ready.main()

            published=json.loads((data/'articles.json').read_text(encoding='utf-8'))
            queue_after=json.loads((data/'research_queue.json').read_text(encoding='utf-8'))
            self.assertEqual(len(published),1)
            self.assertEqual(queue_after[0]['status'],'PUBLISHED')
            self.assertTrue(published[0]['appnho_published_at'])

if __name__=='__main__':
    unittest.main(verbosity=2)
