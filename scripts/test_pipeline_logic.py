"""Offline unit checks for model allowlists and article archive invariants."""
import os, json, unittest
from unittest.mock import patch
import news_pipeline as n

class ProviderBudgetTests(unittest.TestCase):
    def test_gemini_calls_are_bounded_per_research_run(self):
        with patch.dict(os.environ,{"GEMINI_API_KEY":"test-key"},clear=True), \
             patch.object(n,"MODEL_DISCOVERY_CACHE",{}), \
             patch.object(n,"discover_gemini_models",return_value=["gemini-test-a","gemini-test-b"]), \
             patch.object(n,"gemini",side_effect=RuntimeError("temporary provider error")) as call, \
             patch.object(n,"MAX_GEMINI_CALLS_PER_RUN",1), \
             patch.object(n,"GEMINI_CALLS_THIS_RUN",0):
            with self.assertRaises(RuntimeError):
                n.generate_with_fallback("test prompt")
            self.assertEqual(call.call_count,1)
            self.assertEqual(n.GEMINI_CALLS_THIS_RUN,1)

class WindowBoundaryTests(unittest.TestCase):
    def test_window_is_open_at_start_and_closed_at_run_time(self):
        start='2026-10-24T06:00:00+07:00'
        end='2026-10-24T17:00:00+07:00'
        self.assertFalse(n.is_in_window('2026-10-24T06:00:00+07:00', start, end))
        self.assertTrue(n.is_in_window('2026-10-24T06:00:01+07:00', start, end))
        self.assertTrue(n.is_in_window('2026-10-24T17:00:00+07:00', start, end))
        self.assertFalse(n.is_in_window('2026-10-24T17:00:01+07:00', start, end))
    def test_missing_or_invalid_publication_date_is_not_fresh(self):
        start='2026-10-24T06:00:00+07:00'; end='2026-10-24T17:00:00+07:00'
        self.assertFalse(n.is_in_window('', start, end))
        self.assertFalse(n.is_in_window('not-a-date', start, end))

class SourceDiversityTests(unittest.TestCase):
    def test_recently_used_source_gets_lower_score(self):
        item={'source_published_at':'2026-10-25T09:00:00+00:00','category':'world','discovery_title':'Important international development with verified details','source_name':'VOV'}
        base=n.source_score(item, 1, 0)
        penalized=n.source_score(item, 1, 16)
        self.assertLess(penalized, base)
    def test_recent_usage_penalty_is_bounded(self):
        item={'source_published_at':'2026-10-25T09:00:00+00:00','category':'world','discovery_title':'Important international development with verified details','source_name':'VOV'}
        self.assertEqual(n.source_score(item, 1, 100), n.source_score(item, 1, 24))

class ModelAllowlistTests(unittest.TestCase):
    def test_gemini_selects_current_free_stable_flash_lite(self):
        os.environ['GEMINI_API_KEY']='test'
        payload={'models':[
            {'name':'models/gemini-3.5-flash-lite','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.1-flash-lite','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']},
            {'name':'models/gemini-2.5-pro','supportedGenerationMethods':['generateContent']}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_gemini_models(),['gemini-3.5-flash-lite','gemini-3.1-flash-lite'])
    def test_xai_discovers_current_grok_model_by_live_catalog_and_price(self):
        os.environ['XAI_API_KEY']='test'
        os.environ.pop('GROK_MODEL',None)
        payload={'models':[
            {'id':'grok-4.7','prompt_text_token_price':20000,'completion_text_token_price':60000},
            {'id':'grok-420-reasoning','prompt_text_token_price':20000,'completion_text_token_price':80000},
            {'id':'grok-imagine-image','prompt_text_token_price':0,'completion_text_token_price':0}]}
        with patch.object(n,'get_json',return_value=payload) as mocked:
            self.assertEqual(n.discover_xai_models(),['grok-4.7','grok-420-reasoning'])
            self.assertEqual(mocked.call_args.args[0], 'https://api.x.ai/v1/language-models')
    def test_grok_generation_uses_responses_api_and_disables_server_storage(self):
        os.environ['XAI_API_KEY']='test'
        payload={'output':[{'type':'message','content':[{'type':'output_text','text':'{"publish":false,"reason":"not enough evidence","title":"","summary":"","category":"vietnam","seo_title":"","meta_description":"","keywords":[],"body":[],"source_index":0,"fact_ledger":[],"editorial_value":"","risk_level":"R1","freshness_ttl_hours":24}'}]}]}
        with patch.object(n,'_post_json',return_value=payload) as mocked:
            result=n.xai_responses('prompt','grok-current')
            self.assertFalse(result['publish'])
            self.assertEqual(mocked.call_args.args[0],'https://api.x.ai/v1/responses')
            self.assertFalse(mocked.call_args.args[1]['store'])

    def test_openrouter_requires_zero_cost_free_variant(self):
        os.environ['OPENROUTER_API_KEY']='test'
        payload={'data':[{'id':'a/model:free','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'b/model','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'c/model:free','pricing':{'prompt':'0.1','completion':'0'},'context_length':32000}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_openrouter_models(),['a/model:free'])

class QualityPipelineTests(unittest.TestCase):
    def test_extract_page_allows_limited_factual_reference_when_enabled(self):
        html=b'<html><body><article><h1>Verified public event</h1><p>Evidence text about a public event with specific facts and context.</p></article></body></html>'
        with patch.object(n,'source_info',return_value={'access_status':'UNVERIFIED','terms_status':'UNVERIFIED'}), \
             patch.object(n,'robots_allowed',return_value=True), \
             patch.object(n,'fetch',return_value=html) as fetch_mock, \
             patch.dict(os.environ,{'NEWS_PUBLIC_FACTUAL_RESEARCH':'1'}):
            text=n.extract_page('https://publisher.example/story')
            self.assertIn('Evidence text',text)
            fetch_mock.assert_called_once()

    def test_extract_page_rejects_paywall_or_captcha_interstitial(self):
        html=b'<html><body><p>Subscribe to continue reading this article. Please sign in.</p></body></html>'
        with patch.object(n,'source_info',return_value={'access_status':'UNVERIFIED','terms_status':'UNVERIFIED'}), \
             patch.object(n,'robots_allowed',return_value=True), \
             patch.object(n,'fetch',return_value=html), \
             patch.dict(os.environ,{'NEWS_PUBLIC_FACTUAL_RESEARCH':'1'}):
            with self.assertRaises(PermissionError):
                n.extract_page('https://publisher.example/story')

    def test_unlisted_source_must_match_its_configured_rss_publisher(self):
        with patch.object(n,'source_info',return_value={
            'access_status':'UNVERIFIED','terms_status':'UNVERIFIED','directory_access_status':'not_listed'
        }), patch.object(n,'robots_allowed',return_value=True), \
             patch.dict(os.environ,{'NEWS_PUBLIC_FACTUAL_RESEARCH':'1'}):
            with self.assertRaises(PermissionError):
                n.research_access_mode('https://unrelated.example/story','publisher.example')
            self.assertEqual(n.research_access_mode('https://publisher.example/story','publisher.example'),
                             'LIMITED_FACTUAL_REFERENCE')

    def test_extract_page_blocks_explicitly_blocked_source(self):
        with patch.object(n,'source_info',return_value={'access_status':'BLOCKED','terms_status':'UNVERIFIED'}), \
             patch.object(n,'fetch') as fetch_mock, \
             patch.dict(os.environ,{'NEWS_PUBLIC_FACTUAL_RESEARCH':'1'}):
            with self.assertRaises(PermissionError):
                n.extract_page('https://publisher.example/story')
            fetch_mock.assert_not_called()

    def test_parse_ai_json_requires_fact_ledger_and_editorial_value(self):
        with self.assertRaises(ValueError):
            n.parse_ai_json('{"publish":true,"title":"x"}')

    def test_make_article_requires_independent_sources_and_fact_ledger(self):
        group=[
            {'source_name':'BBC News','source_url':'https://www.bbc.co.uk/news/story-a','source_published_at':'2026-10-31T01:00:00+00:00'},
            {'source_name':'Reuters','source_url':'https://www.reuters.com/world/story-a','source_published_at':'2026-10-31T01:00:00+00:00'}
        ]
        paragraph_template=("Sự kiện được ghi nhận tại thời điểm cụ thể với chủ thể và dữ kiện có thể kiểm tra. "
                            "Tài liệu nguồn mô tả diễn biến, phạm vi và những thay đổi đã được xác nhận. "
                            "Phần phân tích đối chiếu dữ kiện này với bối cảnh liên quan, không suy diễn vượt quá chứng cứ. ")
        body=[f"Đoạn {i+1}. "+paragraph_template*(14+i%2) for i in range(7)]
        urls=[x['source_url'] for x in group]
        obj={
            'publish':True,'title':'Diễn biến quốc tế được xác nhận qua hai nguồn độc lập',
            'summary':'Hai nguồn độc lập xác nhận các mốc chính của sự kiện và những giới hạn cần lưu ý.',
            'category':'world','seo_title':'Diễn biến quốc tế được xác nhận','meta_description':'Thông tin và bối cảnh sự kiện.',
            'keywords':['quốc tế','sự kiện','nguồn độc lập','dữ kiện'],'body':body,'source_index':0,
            'editorial_value':'Đối chiếu hai nguồn độc lập. Phân biệt dữ kiện đã xác nhận với phần còn chưa rõ.',
            'content_type':'short_explainer','data_type':'general',
            'risk_level':'R1','freshness_ttl_hours':24,
            'fact_ledger':[
                {'claim':'Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể.','source_urls':urls,'evidence_snippet':'Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể.','importance':'core'},
                {'claim':'Dữ kiện chính thứ hai được xác nhận trong tài liệu nguồn.','source_urls':urls,'evidence_snippet':'Dữ kiện chính thứ hai được xác nhận trong tài liệu nguồn.','importance':'core'},
                {'claim':'Bối cảnh thứ ba làm rõ giới hạn của thông tin.','source_urls':[urls[0]],'evidence_snippet':'Bối cảnh thứ ba làm rõ giới hạn của thông tin.','importance':'supporting'}
            ]
        }
        evidence_pages={
            urls[0]: "Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể. Dữ kiện chính thứ hai được xác nhận trong tài liệu nguồn. Bối cảnh thứ ba làm rõ giới hạn của thông tin.",
            urls[1]: "Dữ kiện chính thứ nhất có thời điểm và chủ thể cụ thể. Dữ kiện chính thứ hai được xác nhận trong tài liệu nguồn."
        }
        article=n.make_article(obj,group,evidence_pages)
        self.assertTrue(all(x.get('evidence_verifications') for x in article['fact_ledger']))
        self.assertEqual(article['quality_version'],'1.5')
        self.assertEqual(article['quality_status'],'PASS')
        self.assertNotIn('editorial_note',article)

    def test_make_article_rejects_fact_ledger_url_not_in_evidence(self):
        group=[{'source_name':'BBC News','source_url':'https://www.bbc.co.uk/news/story-a','source_published_at':'2026-10-31T01:00:00+00:00'},
               {'source_name':'Reuters','source_url':'https://www.reuters.com/world/story-a','source_published_at':'2026-10-31T01:00:00+00:00'}]
        body=[("Đoạn viết có dữ kiện cụ thể và phân tích bối cảnh được hỗ trợ bằng tài liệu. "*20)+str(i) for i in range(7)]
        obj={'publish':True,'title':'Một sự kiện có nguồn xác minh độc lập','summary':'Tóm tắt đủ rõ về sự kiện và bối cảnh.',
             'category':'world','body':body,'source_index':0,'seo_title':'Sự kiện','meta_description':'Tóm tắt',
             'keywords':['tin','sự kiện','quốc tế','dữ kiện'],'editorial_value':'Đối chiếu hai nguồn độc lập. Làm rõ phần dữ kiện chưa được xác nhận.',
             'content_type':'short_explainer','data_type':'general',
             'risk_level':'R1','freshness_ttl_hours':24,
             'fact_ledger':[{'claim':'Dữ kiện kiểm tra thứ nhất có thông tin cụ thể.','source_urls':['https://wrong.example/a']},
                            {'claim':'Dữ kiện kiểm tra thứ hai có thông tin cụ thể.','source_urls':['https://wrong.example/a']},
                            {'claim':'Dữ kiện kiểm tra thứ ba có thông tin cụ thể.','source_urls':['https://wrong.example/a']}]}
        with self.assertRaises(ValueError):
            n.make_article(obj,group)

if __name__=='__main__': unittest.main(verbosity=2)
