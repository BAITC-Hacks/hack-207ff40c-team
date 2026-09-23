"""Evaluator infrastructure tests. Toy adapters are not innovation results."""
from pathlib import Path
import contextlib
import io
import json
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE/'scripts'))
import evaluate
from harness import write_json

class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/'evals').mkdir()
        write_json(self.root/'state.json',{'mode':'build','rules_confirmed':True,'official_start_confirmed':True})
    def tearDown(self): self.tmp.cleanup()
    def cases(self,items):
        p=self.root/'evals/cases.jsonl'
        p.write_text(''.join(json.dumps(c)+'\n' for c in items),encoding='utf-8')
        return p
    def fixture(self,broken_baseline=False,bad_proposed=False):
        self.cases([{'id':str(i),'input':{'x':i},'expected':{'answer':i*2}} for i in [1,2]])
        baseline=['{python}','-S','-c',"import json,sys; v=json.load(sys.stdin); print(json.dumps({'answer':v['x']}))"]
        if broken_baseline: baseline=['{python}','-S','-c','raise SystemExit(3)']
        proposed=['{python}','-S','-c',"import json,sys; v=json.load(sys.stdin); print(json.dumps({'answer':v['x']*2}))"]
        if bad_proposed: proposed=['{python}','-S','-c',"print('{\"answer\":0}')"]
        write_json(self.root/'evals/config.json',{'baseline_argv':baseline,'proposed_argv':proposed,'timeout_seconds':2,'cases_file':'evals/cases.jsonl'})
    def test_path_lookup(self):
        self.assertEqual(evaluate.at_path({'a':[{'b':3}]},'a.0.b'),3)
    def test_booleans_not_numbers(self):
        self.assertFalse(evaluate.exact_equal({'x':True},{'x':1}))
    def test_type_sensitive_numbers(self):
        self.assertFalse(evaluate.exact_equal(1,1.0))
    def test_missing_path_fails(self):
        self.assertEqual(len(evaluate.compare({}, {'answer':2})),1)
    def test_empty_case_file_rejected(self):
        with self.assertRaises(ValueError): evaluate.read_cases(self.cases([]))
    def test_duplicate_case_ids_rejected(self):
        c={'id':'a','input':{},'expected':{'x':2}}
        with self.assertRaises(ValueError): evaluate.read_cases(self.cases([c,c]))
    def test_expectations_required(self):
        with self.assertRaises(ValueError): evaluate.read_cases(self.cases([{'id':'a','input':{}}]))
    def test_nan_rejected(self):
        with self.assertRaises(ValueError): evaluate.strict_loads('{"x":NaN}')
    def test_real_paired_execution(self):
        self.fixture()
        with contextlib.redirect_stdout(io.StringIO()): report,dest=evaluate.evaluate(self.root)
        self.assertEqual(report['summary']['baseline']['passed'],0)
        self.assertEqual(report['summary']['proposed']['passed'],2)
        self.assertTrue(report['evaluation_executed_without_errors'])
        self.assertTrue(dest.with_suffix('.md').exists())
        self.assertEqual(report['cases_sha256_before'],report['cases_sha256_after'])
    def test_baseline_crash_not_hidden(self):
        self.fixture(broken_baseline=True)
        with contextlib.redirect_stdout(io.StringIO()): report,_=evaluate.evaluate(self.root)
        self.assertEqual(report['summary']['baseline']['attempted'],2)
        self.assertEqual(report['summary']['baseline']['execution_errors'],2)
        self.assertFalse(report['evaluation_executed_without_errors'])
    def test_proposed_failure_recorded(self):
        self.fixture(bad_proposed=True)
        with contextlib.redirect_stdout(io.StringIO()): report,_=evaluate.evaluate(self.root)
        self.assertFalse(report['proposed_all_cases_passed'])
        self.assertEqual(report['summary']['proposed']['pass_rate'],0)
    def test_adapter_timeout(self):
        result=evaluate.invoke([sys.executable,'-S','-c','import time; time.sleep(1)'],{},self.root,0.05)
        self.assertEqual(result['status'],'timeout')
    def test_non_json_adapter_rejected(self):
        result=evaluate.invoke([sys.executable,'-S','-c','print("done")'],{},self.root,2)
        self.assertEqual(result['status'],'error')
    def test_missing_executable(self):
        result=evaluate.invoke(['definitely_no_such_hackathon_executable'],{},self.root,2)
        self.assertEqual(result['status'],'error')
    def test_no_path_escape(self):
        self.fixture()
        cfg=evaluate.load_json(self.root/'evals/config.json')
        cfg['cases_file']='../outside.jsonl'
        write_json(self.root/'evals/config.json',cfg)
        with self.assertRaises(ValueError): evaluate.evaluate(self.root)
    def test_prepare_mode_rejected(self):
        self.fixture(); write_json(self.root/'state.json',{'mode':'prepare'})
        with self.assertRaises(ValueError): evaluate.evaluate(self.root)

if __name__=='__main__': unittest.main()
