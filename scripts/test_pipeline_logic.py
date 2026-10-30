"""Offline unit checks for model allowlists and article archive invariants."""
import os, json, unittest
from unittest.mock import patch
import news_pipeline as n
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
    def test_gemini_only_current_allowlisted_free_models(self):
        os.environ['GEMINI_API_KEY']='test'
        payload={'models':[{'name':'models/gemini-3.1-flash-lite','supportedGenerationMethods':['generateContent']},{'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']},{'name':'models/gemini-2.5-pro','supportedGenerationMethods':['generateContent']}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_gemini_models(),['gemini-3.1-flash-lite'])
    def test_xai_discovers_one_fast_text_model_for_the_key(self):
        os.environ['XAI_API_KEY']='test'
        payload={'data':[{'id':'grok-4.1-fast-reasoning'},{'id':'grok-4.1-fast-non-reasoning'},{'id':'grok-4.7'},{'id':'grok-vision-latest'}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_xai_models(),['grok-4.1-fast-non-reasoning'])

    def test_feed_date_reads_namespaced_dc_date(self):
        import xml.etree.ElementTree as ET
        node=ET.fromstring('<item xmlns:dc="http://purl.org/dc/elements/1.1/"><title>Test</title><dc:date>2026-10-30T08:00:00+07:00</dc:date></item>')
        self.assertEqual(n.feed_publication_date(node),'2026-10-30T01:00:00+00:00')
    def test_openrouter_requires_zero_cost_free_variant(self):
        os.environ['OPENROUTER_API_KEY']='test'
        payload={'data':[{'id':'a/model:free','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'b/model','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'c/model:free','pricing':{'prompt':'0.1','completion':'0'},'context_length':32000}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_openrouter_models(),['a/model:free'])
if __name__=='__main__': unittest.main(verbosity=2)
