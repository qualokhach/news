import unittest, json, os, tempfile, sys
from pathlib import Path
from unittest.mock import patch
import news_pipeline as pipeline
import write_candidates

class TestResearchDossierGate(unittest.TestCase):
    def test_thin_dossier_is_not_ready(self):
        group=[
            {'source_url':'https://example-a.test/story','source_name':'A'},
            {'source_url':'https://example-b.test/story','source_name':'B'},
        ]
        pages={group[0]['source_url']:'Short text only.',
               group[1]['source_url']:'Another short text only.'}
        dossier=pipeline.build_research_dossier(group,pages)
        ok,reason=pipeline.research_dossier_ready(dossier)
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_dossier_records_distinct_factual_units(self):
        group=[
            {'source_url':'https://example-a.test/story','source_name':'A'},
            {'source_url':'https://example-b.test/story','source_name':'B'},
        ]
        pages={
          group[0]['source_url']:('The company reported revenue of 120 million dollars in 2026. '
            'The board approved a new production facility on 12 March 2026. '
            'The facility will employ 450 workers across three shifts. '
            'The regulator published the approval document on 14 March 2026. '
            'The production line is expected to begin operating in September 2026. '
            'The company stated the project budget was 85 million dollars. ')*5,
          group[1]['source_url']:('The company reported revenue of 120 million dollars in 2026. '
            'The board approved a new production facility on 12 March 2026. '
            'The facility will employ 450 workers across three shifts. '
            'The regulator published the approval document on 14 March 2026. '
            'The production line is expected to begin operating in September 2026. '
            'The company stated the project budget was 85 million dollars. ')*5,
        }
        dossier=pipeline.build_research_dossier(group,pages)
        self.assertGreaterEqual(dossier['distinct_fact_units'],5)
        self.assertEqual(dossier['source_count'],2)
        ok,reason=pipeline.research_dossier_ready(dossier)
        self.assertTrue(ok,reason)


    def test_thin_staged_candidate_returns_to_research_without_api_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            queue=base/'research_queue.json'; pending=base/'pending.json'
            articles=base/'articles.json'; archive=base/'archive_articles.json'; seen=base/'seen_items.json'
            lead='A verified test headline about public transport expansion'
            sources=[
                {'source_url':'https://publisher-a.example/story','source_name':'A','discovery_title':lead},
                {'source_url':'https://publisher-b.example/story','source_name':'B','discovery_title':lead},
            ]
            weak=(lead+'. This page repeats the same short discovery statement without additional facts. ')*12
            queue.write_text(json.dumps([{'queue_id':'q1','status':'WRITING_PENDING','lead_title':lead,
                'group':sources,'discovery_group':sources,
                'evidence_pages':{x['source_url']:weak for x in sources}}]),encoding='utf-8')
            pending.write_text('[]',encoding='utf-8'); articles.write_text('[]',encoding='utf-8')
            archive.write_text('[]',encoding='utf-8'); seen.write_text('{"items":{}}',encoding='utf-8')
            def source_info(url):
                host=url.split('/')[2]
                return {'source_family':host,'is_primary':False}
            with patch.object(write_candidates,'QUEUE',queue), \
                 patch.object(write_candidates,'PENDING',pending), \
                 patch.object(write_candidates,'ARTICLES',articles), \
                 patch.object(write_candidates,'ARCHIVE',archive), \
                 patch.object(write_candidates,'SEEN',seen), \
                 patch.object(write_candidates.np,'source_info',side_effect=source_info), \
                 patch.object(write_candidates.np,'generate_with_fallback',side_effect=AssertionError('AI must not be called')):
                with patch.dict(os.environ,{'GEMINI_API_KEY':'test-key'},clear=False):
                    write_candidates.main()
            q=json.loads(queue.read_text(encoding='utf-8'))
            p=json.loads(pending.read_text(encoding='utf-8'))
            self.assertEqual(q[0]['status'],'RESEARCH_PENDING')
            self.assertEqual(len(p),2)
            self.assertTrue(all(x['status']=='retry' for x in p))

    def test_short_relevant_sources_survive_writing_filter(self):
        lead='Council approves 18 kilometre road project'
        page_a=('Council approves 18 kilometre road project on 12 March 2026. '
                'Construction begins in June 2026. The project covers three districts.')
        page_b=('Council confirmed approval of the 18 kilometre road project on 12 March 2026. '
                'Work is scheduled to begin in June 2026. Three districts are included.')
        group=[
            {'source_url':'https://publisher-a.example/story','source_name':'A','discovery_title':lead},
            {'source_url':'https://publisher-b.example/story','source_name':'B','discovery_title':lead},
        ]
        with patch.object(write_candidates.np,'source_info',side_effect=lambda url:{
            'source_family':url.split('/')[2],'is_primary':False
        }):
            relevant,pages,independent,has_primary=write_candidates._filter_candidate_evidence({
                'lead_title':lead,'group':group,
                'evidence_pages':{group[0]['source_url']:page_a,group[1]['source_url']:page_b}
            })
        self.assertEqual(len(relevant),2)
        self.assertEqual(independent,2)
        self.assertFalse(has_primary)
        self.assertTrue(all(len(x)<500 for x in pages.values()))

    def test_dossier_fixes_content_type_before_prompt(self):
        group=[{'source_url':'https://example-a.test/story','source_name':'A'},
               {'source_url':'https://example-b.test/story','source_name':'B'}]
        pages={x['source_url']:('A confirmed event included 120 participants on 12 March 2026. ')*12 for x in group}
        dossier=pipeline.build_research_dossier(group,pages)
        self.assertIn(dossier['content_type'],{'quick_update','short_explainer','news_analysis'})


    def test_short_primary_source_can_pass_without_character_floor(self):
        group=[{'source_url':'https://agency.example/notice','source_name':'Official agency'}]
        page=('Agency approved the project on 12 March 2026. '
              'The permit covers 450 workers at the facility. '
              'Operations are scheduled to begin in September 2026.')
        with patch.object(pipeline,'source_info',return_value={
            'source_family':'agency.example','is_primary':True,'source_type':'official'
        }):
            dossier=pipeline.build_research_dossier(group,{group[0]['source_url']:page})
            ok,reason=pipeline.research_dossier_ready(dossier)
        self.assertLess(dossier['evidence_characters'],2500)
        self.assertGreaterEqual(dossier['distinct_fact_units'],3)
        self.assertTrue(ok,reason)

    def test_short_secondary_article_is_not_rejected_by_length_alone(self):
        group=[{'source_url':'https://publisher-a.example/report','source_name':'A'},
               {'source_url':'https://publisher-b.example/report','source_name':'B'}]
        pages={
          group[0]['source_url']:('The council approved the plan on 12 March 2026. '
                                  'The project covers 18 kilometres of road. '
                                  'Construction begins in June 2026.'),
          group[1]['source_url']:('Officials confirmed the plan was approved on 12 March 2026. '
                                  'The road project spans 18 kilometres. '
                                  'Work is scheduled to start in June 2026.')
        }
        with patch.object(pipeline,'source_info',side_effect=lambda url:{
            'source_family':url.split('/')[2],'is_primary':False,'source_type':'publisher'
        }):
            dossier=pipeline.build_research_dossier(group,pages)
            ok,reason=pipeline.research_dossier_ready(dossier)
        self.assertLess(dossier['evidence_characters'],2500)
        self.assertTrue(ok,reason)

if __name__=='__main__':
    unittest.main()
