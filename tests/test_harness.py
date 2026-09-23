"""Tests of preparation tooling only. These are NOT product benchmark results."""
from pathlib import Path
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE/'scripts'))
import harness

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)/'repo'
        shutil.copytree(SOURCE,self.root,ignore=shutil.ignore_patterns('reports','__pycache__','.git','.venv','node_modules','third_party'))
    def tearDown(self):
        self.tmp.cleanup()
    def authorize(self):
        harness.write_json(self.root/'state.json',{'mode':'build','rules_confirmed':True,'official_start_confirmed':True})
    def config(self,exitcode=0):
        harness.write_json(self.root/'checks.json',{'commands':[
            {'name':kind,'kind':kind,'argv':['{python}','-S','-c',f'raise SystemExit({exitcode if kind=="test" else 0})'],'timeout_seconds':2}
            for kind in ('test','build','smoke')]})
    def test_structure(self):
        self.assertEqual(harness.check(self.root),[])
    def test_invalid_skill_detected(self):
        (self.root/'.agents/skills/hackathon-build/SKILL.md').write_text('bad')
        self.assertIn('Invalid skill frontmatter: hackathon-build', harness.check(self.root))
    def test_missing_skill_detected(self):
        (self.root/'.agents/skills/hackathon-build/SKILL.md').unlink()
        self.assertIn('Missing skill: hackathon-build', harness.check(self.root))
    def test_missing_file_detected(self):
        (self.root/'brief.json').unlink()
        self.assertTrue(harness.check(self.root))
    def test_prepare_not_authorized(self):
        self.assertFalse(harness.build_authorized(self.root))
    def test_confirmation_required(self):
        with self.assertRaises(ValueError): harness.activate(self.root,True,False)
    def test_real_brief_required(self):
        with self.assertRaises(ValueError): harness.activate(self.root,True,True)
    def test_activation_records_snapshot(self):
        harness.write_json(self.root/'brief.json',{'challenge_text':'This is a test-only challenge text, not an event briefing.','rules_source':'Test fixture, not real rules'})
        with contextlib.redirect_stdout(io.StringIO()): harness.activate(self.root,True,True)
        self.assertTrue(harness.build_authorized(self.root))
        self.assertEqual(len(list((self.root/'reports').glob('pre-build-manifest-*.json'))),1)
    def test_verification_refuses_prepare(self):
        with self.assertRaises(ValueError): harness.verify(self.root)
    def test_verification_refuses_empty(self):
        self.authorize()
        with self.assertRaises(ValueError): harness.verify(self.root)
    def test_verification_refuses_missing_kind(self):
        self.authorize()
        harness.write_json(self.root/'checks.json',{'commands':[{'name':'only-test','kind':'test','argv':['{python}','-V']}]})
        with self.assertRaises(ValueError): harness.verify(self.root)
    def test_real_commands_pass(self):
        self.authorize(); self.config()
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(harness.verify(self.root),0)
        self.assertEqual(len(list((self.root/'reports').glob('*.log'))),3)
    def test_failed_command_not_passing(self):
        self.authorize(); self.config(1)
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(harness.verify(self.root),1)
    def test_shell_string_rejected(self):
        with self.assertRaises(ValueError): harness.expand_argv('echo yes')
    def test_timeout_validation(self):
        for v in [0,-1,601,True,float('nan'),'30']:
            with self.subTest(value=v):
                with self.assertRaises(ValueError): harness.timeout_value(v)
    def test_snapshot_excludes_private_and_generated(self):
        (self.root/'.env').write_text('SECRET=not-real')
        (self.root/'node_modules').mkdir()
        (self.root/'node_modules/leak').write_text('skip')
        snap = harness.snapshot(self.root)['sha256']
        self.assertNotIn('.env',snap)
        self.assertNotIn('node_modules/leak',snap)
        self.assertIn('AGENTS.md',snap)
    def test_duplicate_command_names_rejected(self):
        self.authorize(); self.config()
        cfg=harness.load_json(self.root/'checks.json')
        cfg['commands'][1]['name']='test'
        harness.write_json(self.root/'checks.json',cfg)
        with self.assertRaises(ValueError): harness.verify(self.root)

if __name__=='__main__': unittest.main()
