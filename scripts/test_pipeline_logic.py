"""Offline unit checks for model allowlists and article archive invariants."""
import os, json, unittest
from unittest.mock import patch
import news_pipeline as n
class ModelAllowlistTests(unittest.TestCase):
    def test_gemini_only_current_allowlisted_free_models(self):
        os.environ['GEMINI_API_KEY']='test'
        payload={'models':[{'name':'models/gemini-3.1-flash-lite','supportedGenerationMethods':['generateContent']},{'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']},{'name':'models/gemini-2.5-pro','supportedGenerationMethods':['generateContent']}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_gemini_models(),['gemini-3.1-flash-lite'])
    def test_groq_excludes_paid_or_unapproved_models(self):
        os.environ['GROQ_API_KEY']='test'
        payload={'data':[{'id':'openai/gpt-oss-20b'},{'id':'openai/gpt-oss-120b'},{'id':'qwen/qwen3.8-27b'},{'id':'meta-llama/llama-3.3-70b-versatile'}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_groq_models(),['openai/gpt-oss-20b','qwen/qwen3.8-27b','openai/gpt-oss-120b'])
    def test_openrouter_requires_zero_cost_free_variant(self):
        os.environ['OPENROUTER_API_KEY']='test'
        payload={'data':[{'id':'a/model:free','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'b/model','pricing':{'prompt':'0','completion':'0'},'context_length':32000},{'id':'c/model:free','pricing':{'prompt':'0.1','completion':'0'},'context_length':32000}]}
        with patch.object(n,'get_json',return_value=payload):
            self.assertEqual(n.discover_openrouter_models(),['a/model:free'])
if __name__=='__main__': unittest.main(verbosity=2)
