"""Real join-page script executed by Node against bounded DOM fixtures."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).parents[1] / "join.js"
NODE = shutil.which("node")


def observe(*steps, host="meet.google.com"):
    if not NODE:
        pytest.skip("Node is required to execute the browser join script")
    program = r'''
const vm = require('vm');
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = fs.readFileSync(payload.path, 'utf8');
const context = vm.createContext({window:{}, location:{hostname:payload.host}, getComputedStyle:()=>({visibility:'visible'})});
const values = [];
for (const step of payload.steps) {
  const element = (text, excluded=false) => ({innerText:text,textContent:text,disabled:false,getClientRects:()=>[{}],getAttribute:()=>null,closest:()=>excluded?{}:null,click:()=>{}});
  context.Date = {now:()=>step.now ?? 1000};
  context.document = {body:{innerText:step.body ?? ''},querySelector:()=>null,querySelectorAll:(selector)=>
    selector === 'button, [role="button"], a' ? (step.live ? [element('Leave call')] : []) :
    selector === 'h1, h2, [role="heading"]' ? (step.heading ? [element(step.heading, step.inChat)] : []) : []};
  values.push(vm.runInContext(source, context).state);
}
process.stdout.write(JSON.stringify(values));
'''
    process = subprocess.run([NODE, "-e", program], input=json.dumps({"steps": steps, "path": str(SCRIPT), "host": host}), text=True, capture_output=True, timeout=5, check=True)
    return json.loads(process.stdout)


def test_live_controls_take_precedence_over_chat_and_captions():
    assert observe({"live": True, "body": "The meeting has ended. Waiting in the lobby. Sign in to join."}) == ["joined"]


def test_arbitrary_body_and_chat_heading_cannot_end_recording():
    assert observe({"body": "The meeting has ended"},
                   {"heading": "The meeting has ended", "inChat": True, "now": 10000}) == ["joining", "joining"]


@pytest.mark.parametrize("host,heading", [("meet.google.com", "You left the meeting"), ("zoom.us", "This meeting has been ended by host"), ("teams.microsoft.com", "The meeting has ended")])
def test_provider_terminal_heading_must_remain_stable(host, heading):
    assert observe({"heading": heading, "now": 1000}, {"heading": heading, "now": 2000}, {"heading": heading, "now": 3000}, host=host) == ["joining", "joining", "ended"]


def test_reappearing_call_control_resets_terminal_observation():
    assert observe({"heading": "Meeting has ended", "now": 1000}, {"live": True, "now": 4000},
                   {"heading": "Meeting has ended", "now": 5000}) == ["joining", "joined", "joining"]
