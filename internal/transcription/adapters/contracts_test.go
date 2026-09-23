package adapters

import (
	"scriberr/internal/transcription/interfaces"
	"strings"
	"testing"
)

func TestTokenArgumentsRedactedWithoutChangingExecution(t *testing.T) {
	args := []string{"uv", "--hf_token", "sentinel-one", "--hf-token=sentinel-two", "--device", "cpu"}
	redacted := strings.Join(redactCommandArgs(args), " ")
	if strings.Contains(redacted, "sentinel") {
		t.Fatal("credential leaked", redacted)
	}
	if args[2] != "sentinel-one" || args[3] != "--hf-token=sentinel-two" {
		t.Fatal("execution arguments changed")
	}
	if !strings.Contains(redacted, "--device cpu") {
		t.Fatal("nonsecret option removed")
	}
}

func TestAdaptersForwardDeviceAndAutomaticLanguage(t *testing.T) {
	input := interfaces.AudioInput{FilePath: "fixture.wav"}
	pyannote := NewPyAnnoteAdapter(t.TempDir())
	args, err := pyannote.buildPyAnnoteArgs(input, map[string]interface{}{"device": "cpu", "hf_token": "fixture"}, t.TempDir())
	if err != nil || !strings.Contains(strings.Join(args, " "), "--device cpu") {
		t.Fatal(args, err)
	}
	voxtral := NewVoxtralAdapter(t.TempDir())
	for _, language := range []string{"auto", "ru", "kk"} {
		args, err = voxtral.buildVoxtralArgs(input, map[string]interface{}{"device": "cpu", "language": language}, t.TempDir())
		joined := strings.Join(args, " ")
		if err != nil || !strings.Contains(joined, "--device cpu") {
			t.Fatal(args, err)
		}
		if language == "auto" && strings.Contains(joined, "--language en") {
			t.Fatal("auto became English")
		}
		if language != "auto" && !strings.Contains(joined, "--language "+language) {
			t.Fatal("language lost", joined)
		}
	}
	sortformer := NewSortformerAdapter(t.TempDir())
	if _, err := sortformer.buildSortformerArgs(input, map[string]interface{}{"max_speakers": 1}, t.TempDir()); err == nil {
		t.Fatal("unsupported speaker limit accepted")
	}
	if _, err := sortformer.buildSortformerArgs(input, map[string]interface{}{"max_speakers": 4}, t.TempDir()); err != nil {
		t.Fatal(err)
	}
}
