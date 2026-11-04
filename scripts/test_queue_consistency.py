import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import content_quality as cq
import repair_queue
import write_candidates


class NumericSupportTests(unittest.TestCase):
    LEDGER=[{'claim':'FIFA mở tài liệu cho hội đồng.','source_claim':'Members were told material will be released.',
             'evidence_snippet':'Members were told material will be released.',
             'evidence_by_source':[{'source_url':'u','snippet':'Questions covered the past 12 months.'}]}]

    def test_number_in_verified_snippet_is_accepted_without_source_pages(self):
        body=['UEFA nêu nhiều vấn đề trong 12 tháng qua.']
        self.assertEqual(cq.validate_body_fact_coverage(body,self.LEDGER),[])

    def test_unsupported_number_is_still_rejected(self):
        errors=cq.validate_body_fact_coverage(['Có 77 người liên quan.'],self.LEDGER)
        self.assertTrue(errors and '77' in errors[0])

    def test_numbers_verified_at_writing_time_are_honoured_later(self):
        pages={'u':'The scheme cost 12 million.'}
        body=['Dự án trị giá 12 triệu.']
        verified=cq.compute_verified_numbers(body,[],pages)
        self.assertEqual(verified,['12'])
        self.assertTrue(cq.validate_body_fact_coverage(body,[]))
        self.assertEqual(cq.validate_body_fact_coverage(body,[],verified_numbers=verified),[])

    def test_verified_numbers_never_include_unsupported_numbers(self):
        self.assertEqual(cq.compute_verified_numbers(['Có 77 và 12.'],[],{'u':'only 12 here'}),['12'])


class RepairQueueTests(unittest.TestCase):
    def queue(self):
        return [
            {'queue_id':'a','status':'WRITTEN','written_article_id':'a','evidence_pages':{'u':'12'}},
            {'queue_id':'a','status':'READY','article':{'id':'a','body':['12'],'fact_ledger':[]}},
            {'queue_id':'ok','status':'READY','article':{'id':'ok','verified_numbers':[]}},
        ]

    def test_invalid_ready_is_withdrawn_and_returned_to_writing(self):
        q=self.queue()
        with patch.object(repair_queue,'ready_candidate_errors',side_effect=lambda a:['lỗi'] if a['id']=='a' else []):
            repaired,withdrawn=repair_queue.repair(q)
        self.assertEqual(withdrawn,['a']); self.assertEqual(repaired,[])
        self.assertEqual(q[1]['status'],'REJECT')
        self.assertEqual(q[0]['status'],'WRITING_PENDING')
        self.assertNotIn('written_article_id',q[0])
        self.assertEqual(q[2]['status'],'READY')

    def test_ready_is_repaired_from_sealed_pages_when_only_numbers_were_missing(self):
        q=self.queue()
        def errors(article):
            return [] if (article.get('verified_numbers') or article['id']=='ok') else ['số liệu']
        with patch.object(repair_queue,'ready_candidate_errors',side_effect=errors):
            repaired,withdrawn=repair_queue.repair(q)
        self.assertEqual(repaired,['a'])
        self.assertEqual(withdrawn,[])
        self.assertEqual(q[1]['status'],'READY')
        self.assertEqual(q[1]['article']['verified_numbers'],['12'])


class WriteAttemptCapTests(unittest.TestCase):
    error='fact_ledger cần ít nhất 3 dữ kiện có thể kiểm tra'

    def test_provider_outage_does_not_use_up_write_attempts(self):
        self.error='Gemini HTTP 503: high demand | OpenRouter HTTP 429'
        self.run_once(expected_status='WRITING_PENDING')

    def test_hopeless_candidate_is_closed_after_max_attempts(self):
        self.run_once(expected_status='REJECT')

    def run_once(self, expected_status):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            files={n:base/n for n in ('q.json','a.json','ar.json','s.json')}
            item={'queue_id':'x','status':'WRITING_PENDING','staged_at':'2026-11-01T10:00:00+00:00',
                  'expires_at':'2099-01-01T00:00:00+00:00','lead_title':'t','write_attempts':write_candidates.MAX_WRITE_ATTEMPTS-1,
                  'group':[{'source_url':'https://www.bbc.co.uk/a','source_name':'BBC','discovery_title':'t'},
                           {'source_url':'https://www.reuters.com/a','source_name':'R','discovery_title':'t'}],
                  'evidence_pages':{'https://www.bbc.co.uk/a':'text '*50,'https://www.reuters.com/a':'text '*50}}
            files['q.json'].write_text(json.dumps([item]),encoding='utf-8')
            for n in ('a.json','ar.json'): files[n].write_text('[]',encoding='utf-8')
            files['s.json'].write_text('{"items":{}}',encoding='utf-8')
            with patch.object(write_candidates,'QUEUE',files['q.json']), patch.object(write_candidates,'ARTICLES',files['a.json']), \
                 patch.object(write_candidates,'ARCHIVE',files['ar.json']), patch.object(write_candidates,'SEEN',files['s.json']), \
                 patch.object(write_candidates,'PENDING',base/'p.json'), \
                 patch.object(write_candidates.np,'make_prompt',return_value='p'), \
                 patch.object(write_candidates.np,'generate_with_fallback',side_effect=RuntimeError(self.error)), \
                 patch.dict(os.environ,{'GEMINI_API_KEY':'k'},clear=False):
                write_candidates.main()
            self.assertEqual(json.loads(files['q.json'].read_text(encoding='utf-8'))[0]['status'],expected_status)


if __name__=='__main__':
    unittest.main()


class AnchorReanchorTests(unittest.TestCase):
    URL='https://example.com/a'
    PAGE='The ministry announced the programme on 31 October 2026, officials said.'

    def fact(self, source_claim):
        return [{'claim':'x','source_claim':source_claim,'source_urls':[self.URL],
                 'evidence_snippet':self.PAGE,
                 'evidence_by_source':[{'source_url':self.URL,'snippet':self.PAGE,'locator':'p1'}]}]

    def test_trimmed_quote_is_reanchored_to_verified_excerpt(self):
        out=cq.repair_fact_ledger_anchors(self.fact('ministry ... announced the programme, officials said'),
                                          [self.URL],{self.URL:self.PAGE})
        self.assertEqual(out[0]['source_claim'],self.PAGE)

    def test_altered_quote_is_left_for_correction(self):
        bad='The ministry cancelled the programme on 31 October 2026.'
        out=cq.repair_fact_ledger_anchors(self.fact(bad),[self.URL],{self.URL:self.PAGE})
        self.assertEqual(out[0]['source_claim'],bad)

    def test_r2_needs_only_two_independent_sources(self):
        self.assertEqual(cq.R2_MIN_INDEPENDENT_SOURCES,2)
        self.assertEqual(cq.classify_risk('Chuyện thường ngày','Một chính sách mới của doanh nghiệp trên thị trường.'),'R1')
        self.assertEqual(cq.classify_risk('Lãi suất tăng','x'),'R2')


class JsonRecoveryTests(unittest.TestCase):
    def test_truncated_reply_is_recovered_without_inventing_values(self):
        import news_pipeline as np
        full=('{"publish":true,"title":"Tiêu đề thử nghiệm","summary":"Sapo thử nghiệm đủ dài.","category":"world",'
              '"body":["Đoạn một.","Đoạn hai."],"keywords":["a"],"fact_ledger":[{"claim":"Dữ kiện thứ nhất được nguồn nêu rõ","source_urls":["u"],"importance":"core"},'
              '{"claim":"Dữ kiện thứ hai bị cắt ngang giữa chừng')
        obj=np.parse_ai_json(full)
        self.assertEqual(obj['body'],["Đoạn một.","Đoạn hai."])
        self.assertEqual(len(obj['fact_ledger']),1)   # incomplete second fact dropped, not invented
        self.assertEqual(obj['risk_level'],'R1')      # optional metadata defaults

    def test_hopeless_text_still_fails(self):
        import news_pipeline as np
        with self.assertRaises(ValueError):
            np.parse_ai_json('xin lỗi tôi không thể giúp')


class LedgerCompletionTests(unittest.TestCase):
    URL1='https://one.example/a'; URL2='https://two.example/b'
    P1=('The ministry announced the programme on 31 October 2026 after months of talks. '
        'Officials said the scheme will cover 12 regions and cost 40 million dollars. '
        'Opposition lawmakers criticised the timetable in parliament on Monday.')
    P2='Reuters reported the ministry confirmed the programme and said the scheme covers 12 regions nationwide.'

    def test_paraphrased_claims_without_any_quotation_get_verified_evidence(self):
        pages={self.URL1:self.P1,self.URL2:self.P2}
        model=[{'claim':'Bộ công bố chương trình mới sau nhiều tháng đàm phán.','source_urls':[self.URL1]}]
        units=[{'text':'Officials said the scheme will cover 12 regions and cost 40 million dollars.','source_urls':[self.URL1]},
               {'text':'Opposition lawmakers criticised the timetable in parliament on Monday.','source_urls':[self.URL1]},
               {'text':'Reuters reported the ministry confirmed the programme and said the scheme covers 12 regions nationwide.','source_urls':[self.URL2]}]
        ledger=cq.complete_fact_ledger(model,units,pages,[self.URL1,self.URL2])
        self.assertGreaterEqual(len(ledger),3)
        errors,enriched=cq.verify_fact_ledger_against_pages(ledger,[self.URL1,self.URL2],pages)
        self.assertEqual(errors,[])
        self.assertEqual(cq.validate_fact_ledger_proof(enriched,[self.URL1,self.URL2]),[])

    def test_claim_with_number_absent_from_source_is_still_rejected(self):
        pages={self.URL1:self.P1}
        ledger=[{'claim':'Chương trình sẽ tốn 999 triệu đô la theo thông báo.','source_urls':[self.URL1],
                 'evidence_snippet':'Officials said the scheme will cover 12 regions and cost 40 million dollars.',
                 'evidence_by_source':[{'source_url':self.URL1,'snippet':'Officials said the scheme will cover 12 regions and cost 40 million dollars.','locator':'p2 of page'}]}]
        errors,_=cq.verify_fact_ledger_against_pages(ledger,[self.URL1],pages,min_claims=1)
        self.assertTrue(errors)

    def test_localized_dates_and_separators_are_not_flagged(self):
        self.assertEqual(cq.validate_body_fact_coverage(['Bộ công bố vào ngày 31 tháng 10 năm 2026.'],
                         [{'claim':'x','evidence_snippet':'announced on 31 October 2026'}]),[])
        self.assertEqual(cq.validate_body_fact_coverage(['Chi phí 1.200 triệu.'],
                         [{'claim':'x','evidence_snippet':'cost 1,200 million'}]),[])
