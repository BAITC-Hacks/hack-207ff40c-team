package transcription

import (
	"context"
	"encoding/json"
	"github.com/stretchr/testify/require"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"scriberr/internal/models"
	"scriberr/internal/transcription/interfaces"
	"scriberr/internal/transcription/registry"
	"scriberr/internal/webhook"
	"testing"
	"time"
)

func installSyntheticAdapter(t *testing.T, adapter interfaces.TranscriptionAdapter) {
	old, err := registry.GetRegistry().GetTranscriptionAdapter(ModelWhisperX)
	registry.RegisterTranscriptionAdapter(ModelWhisperX, adapter)
	t.Cleanup(func() {
		if err == nil {
			registry.RegisterTranscriptionAdapter(ModelWhisperX, old)
		}
	})
	// This fixture does not require or execute a real media/model tool.
	t.Setenv("PATH", t.TempDir())
}
func TestCompletedWebhookIncludesCommittedTranscript(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	installSyntheticAdapter(t, new(MockTranscriptionAdapter))
	callbacks := make(chan webhook.WebhookPayload, 1)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var payload webhook.WebhookPayload
		if err := json.NewDecoder(r.Body).Decode(&payload); err == nil {
			callbacks <- payload
		}
		w.WriteHeader(200)
	}))
	defer server.Close()
	audio := filepath.Join(t.TempDir(), "fake.wav")
	require.NoError(t, os.WriteFile(audio, []byte("synthetic input"), 0600))
	job := &models.TranscriptionJob{ID: "webhook-job", AudioPath: audio, Status: models.StatusProcessing, Parameters: models.WhisperXParams{ModelFamily: "whisper", CallbackURL: &server.URL}}
	require.NoError(t, repo.Create(context.Background(), job))
	service := NewUnifiedTranscriptionService(repo, cfg.TempDir, cfg.TranscriptsDir)
	require.NoError(t, service.ProcessJob(context.Background(), job.ID))
	select {
	case payload := <-callbacks:
		committed, err := repo.FindByID(context.Background(), job.ID)
		require.NoError(t, err)
		require.NotNil(t, payload.Transcript)
		require.Equal(t, committed.Transcript, payload.Transcript)
		require.Contains(t, *payload.Transcript, "mock transcript")
	case <-time.After(2 * time.Second):
		t.Fatal("completion webhook was not delivered")
	}
}

type blockingSyntheticAdapter struct {
	MockTranscriptionAdapter
	started chan string
	release chan struct{}
}

func (a *blockingSyntheticAdapter) Transcribe(ctx context.Context, input interfaces.AudioInput, params map[string]interface{}, proc interfaces.ProcessingContext) (*interfaces.TranscriptResult, error) {
	a.started <- proc.JobID
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-a.release:
		return &interfaces.TranscriptResult{Text: "synthetic"}, nil
	}
}
func TestSharedInferenceAdmissionHonorsWaitingCancellation(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "1")
	cfg, repo, _ := quickFixture(t)
	adapter := &blockingSyntheticAdapter{started: make(chan string, 2), release: make(chan struct{})}
	installSyntheticAdapter(t, adapter)
	audio := filepath.Join(t.TempDir(), "fake.wav")
	require.NoError(t, os.WriteFile(audio, []byte("synthetic"), 0600))
	for _, id := range []string{"normal", "quick"} {
		require.NoError(t, repo.Create(context.Background(), &models.TranscriptionJob{ID: id, AudioPath: audio, Status: models.StatusProcessing, Parameters: models.WhisperXParams{ModelFamily: "whisper"}}))
	}
	processor := NewUnifiedJobProcessor(repo, cfg.TempDir, cfg.TranscriptsDir)
	done := make(chan error, 1)
	go func() { done <- processor.ProcessJob(context.Background(), "normal") }()
	select {
	case <-adapter.started:
	case <-time.After(time.Second):
		t.Fatal("first inference did not start")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	require.ErrorIs(t, processor.ProcessJob(ctx, "quick"), context.DeadlineExceeded)
	require.Empty(t, adapter.started, "waiting inference must not bypass the shared capacity")
	close(adapter.release)
	require.NoError(t, <-done)
}
