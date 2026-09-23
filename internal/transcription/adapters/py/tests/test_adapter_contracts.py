"""Retained adapter boundaries, using API-shaped models; no weights or inference."""
import contextlib
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import threading
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


def fake_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    if "." in name:
        parent_name, key = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name) or fake_module(monkeypatch, parent_name)
        setattr(parent, key, module)
    return module


@pytest.fixture
def models(monkeypatch):
    calls = types.SimpleNamespace(devices=[], languages=[], chunk_paths=[], barrier=None)
    fake_module(monkeypatch, "torch", cuda=types.SimpleNamespace(is_available=lambda: True),
                device=lambda value: value, bfloat16="bf16", float32="fp32", no_grad=contextlib.nullcontext)
    fake_module(monkeypatch, "librosa", load=lambda path, **kw: (list(Path(path).read_bytes()), 8))
    fake_module(monkeypatch, "soundfile", write=lambda path, data, sr: Path(path).write_bytes(bytes(data)))
    fake_module(monkeypatch, "omegaconf", OmegaConf=object, open_dict=lambda value: contextlib.nullcontext())

    class Parakeet:
        cfg = types.SimpleNamespace(decoding=types.SimpleNamespace(greedy={}))

        def change_decoding_strategy(self, cfg):
            pass

        def transcribe(self, paths, **kwargs):
            calls.chunk_paths.append(paths[0])
            if calls.barrier:
                calls.barrier.wait(timeout=5)
            return [types.SimpleNamespace(text=Path(paths[0]).read_bytes().decode(), timestamp=None)]

    fake_module(monkeypatch, "nemo.collections.asr.models",
                ASRModel=types.SimpleNamespace(restore_from=lambda path: Parakeet()),
                SortformerEncLabelModel=types.SimpleNamespace(restore_from=lambda **kw: pytest.fail("Unexpected model load")))

    class Inputs(dict):
        input_ids = types.SimpleNamespace(shape=(1, 0))

        def to(self, device, **kwargs):
            calls.devices.append(device)
            return self

    class Generated:
        def __getitem__(self, key):
            return self

    class Processor:
        def apply_transcription_request(self, *, language, audio, model_id):
            calls.languages.append(language)
            calls.chunk_paths.append(audio)
            if calls.barrier:
                calls.barrier.wait(timeout=5)
            self.text = Path(audio).read_bytes().decode()
            return Inputs()

        def batch_decode(self, output, **kwargs):
            return [self.text]

    def model(**kwargs):
        calls.devices.append(kwargs["device_map"])
        return types.SimpleNamespace(generate=lambda **kw: Generated())

    fake_module(monkeypatch, "transformers",
                AutoProcessor=types.SimpleNamespace(from_pretrained=lambda name: Processor()),
                VoxtralForConditionalGeneration=types.SimpleNamespace(from_pretrained=lambda name, **kw: model(**kw)))

    class Annotation:
        def itertracks(self, yield_label=False):
            assert yield_label
            yield types.SimpleNamespace(start=0.0, end=1.0, duration=1.0), None, "speaker_0"

        def write_rttm(self, stream):
            stream.write("SPEAKER fixture 1 0.000 1.000 <NA> <NA> speaker_0 <NA> <NA>\n")

    class Pipeline:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            return Pipeline()

        def to(self, device):
            calls.devices.append(device)
            return self

        def __call__(self, *args, **kwargs):
            return types.SimpleNamespace(speaker_diarization=Annotation())

    fake_module(monkeypatch, "pyannote.audio", Pipeline=Pipeline)
    return calls


def load(relative):
    spec = importlib.util.spec_from_file_location("boundary_" + Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("relative", ["nvidia/parakeet_transcribe_buffered.py", "voxtral/voxtral_transcribe_buffered.py"])
def test_overlapping_buffered_jobs_keep_private_chunks_and_remove_them(models, monkeypatch, tmp_path, relative):
    adapter = load(relative)
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / ".venv"))
    (tmp_path / "parakeet-tdt-0.6b-v3.nemo").write_bytes(b"test model placeholder")
    sources = [tmp_path / "a.wav", tmp_path / "b.wav"]
    for path, text in zip(sources, ["meeting-a", "meeting-b"]):
        path.write_text(text)
    models.barrier = threading.Barrier(2)

    def run(source):
        output = source.with_suffix(".json")
        adapter.transcribe_buffered(str(source), str(output), chunk_duration_secs=30)
        result = json.loads(output.read_text())
        return result.get("text", result.get("transcription"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, sources)) == ["meeting-a", "meeting-b"]
    assert len(set(models.chunk_paths)) == 2
    assert len({str(Path(path).parent) for path in models.chunk_paths}) == 2
    assert all(not Path(path).parent.exists() for path in models.chunk_paths)


@pytest.mark.parametrize("relative", ["nvidia/parakeet_transcribe_buffered.py", "voxtral/voxtral_transcribe_buffered.py"])
@pytest.mark.parametrize("duration", [0, -1, 1e-100, float("nan"), float("inf"), -float("inf")])
def test_invalid_chunk_duration_rejected_before_model_load(models, tmp_path, relative, duration):
    adapter = load(relative)
    source = tmp_path / "source.wav"
    source.write_bytes(b"nonempty input")
    with pytest.raises(ValueError, match="[Cc]hunk duration"):
        adapter.transcribe_buffered(str(source), str(tmp_path / "out.json"), chunk_duration_secs=duration)
    assert models.devices == []
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("relative", ["nvidia/parakeet_transcribe_buffered.py", "voxtral/voxtral_transcribe_buffered.py"])
def test_invalid_chunk_cli_option_is_not_success(models, monkeypatch, tmp_path, relative):
    adapter = load(relative)
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    positionals = [str(source), "--output", str(tmp_path / "out.json")] if relative.startswith("nvidia") else [str(source), str(tmp_path / "out.json")]
    monkeypatch.setattr(sys, "argv", [relative, *positionals, "--chunk-len", "nan"])
    with pytest.raises(SystemExit) as error:
        adapter.main()
    assert error.value.code == 2


@pytest.mark.parametrize("relative", ["voxtral/voxtral_transcribe.py", "voxtral/voxtral_transcribe_buffered.py"])
@pytest.mark.parametrize("language,condition", [("auto", [None]), ("ru", "ru"), ("kk", "kk")])
def test_voxtral_preserves_cpu_and_language_request(models, tmp_path, relative, language, condition):
    adapter = load(relative)
    source, output = tmp_path / "source.wav", tmp_path / "out.json"
    source.write_text("speech")
    method = getattr(adapter, "transcribe_audio", None) or adapter.transcribe_buffered
    method(str(source), str(output), device="cpu", language=language)
    assert set(models.devices) == {"cpu"}  # CUDA is available in this fixture.
    assert models.languages == [condition]
    assert json.loads(output.read_text())["language"] == language


@pytest.mark.parametrize("output_format", ["rttm", "json"])
def test_pyannote_four_output_wrapper_and_explicit_cpu(models, tmp_path, output_format):
    adapter = load("pyannote/pyannote_diarize.py")
    output = tmp_path / ("out." + output_format)
    adapter.diarize_audio("fixture.wav", str(output), "test-token", device="cpu", output_format=output_format)
    assert models.devices == ["cpu"]
    if output_format == "rttm":
        assert output.read_text().startswith("SPEAKER fixture")
    else:
        assert json.loads(output.read_text())["speakers"] == ["speaker_0"]


@pytest.mark.parametrize("limit", [0, 1, 2, 3, 5, True])
def test_sortformer_rejects_unsupported_speaker_constraints_before_loading(models, tmp_path, limit):
    adapter = load("nvidia/sortformer_diarize.py")
    with pytest.raises(ValueError, match="only max_speakers=4"):
        adapter.diarize_audio("fixture.wav", str(tmp_path / "result.json"), max_speakers=limit)
    assert not (tmp_path / "result.json").exists()


def test_sortformer_supported_four_speaker_output(models, monkeypatch, tmp_path):
    adapter = load("nvidia/sortformer_diarize.py")
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / ".venv"))
    (tmp_path / "diar_streaming_sortformer_4spk-v2.nemo").write_bytes(b"fixture model")
    model = types.SimpleNamespace(eval=lambda: None, diarize=lambda **kw: [[f"{i} {i+1} speaker_{i}" for i in range(4)]])
    monkeypatch.setattr(adapter.SortformerEncLabelModel, "restore_from", lambda **kw: model)
    output = tmp_path / "out.json"
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    adapter.diarize_audio(str(source), str(output), max_speakers=4, output_format="json")
    assert json.loads(output.read_text())["speaker_count"] == 4
