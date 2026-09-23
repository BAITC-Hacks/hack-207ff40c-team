package transcription

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"scriberr/internal/database"
	"scriberr/internal/models"
	"scriberr/internal/transcription/interfaces"
)

type admittedSyntheticAdapter struct {
	MockTranscriptionAdapter
	started chan string
	release chan struct{}
	active  atomic.Int32
	maximum atomic.Int32
}

func (a *admittedSyntheticAdapter) Transcribe(ctx context.Context, input interfaces.AudioInput, _ map[string]interface{}, _ interfaces.ProcessingContext) (*interfaces.TranscriptResult, error) {
	active := a.active.Add(1)
	defer a.active.Add(-1)
	for old := a.maximum.Load(); active > old && !a.maximum.CompareAndSwap(old, active); old = a.maximum.Load() {
	}
	a.started <- input.FilePath
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-a.release:
	}
	text := filepath.Base(input.FilePath)
	return &interfaces.TranscriptResult{
		Text: text, Language: "kk",
		WordSegments: []interfaces.Word{{Start: 0, End: 1, Word: text}},
		Segments:     []interfaces.Segment{{Start: 0, End: 1, Text: text}},
	}, nil
}

func TestMultiTrackUsesParentAdmissionForSequentialTracks(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "1")
	cfg, repo, db := quickFixture(t)
	oldDB := database.DB
	database.DB = db
	t.Cleanup(func() { database.DB = oldDB })
	adapter := &admittedSyntheticAdapter{started: make(chan string, 4), release: make(chan struct{}, 4)}
	installSyntheticAdapter(t, adapter)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	t.Cleanup(cancel)

	root := t.TempDir()
	paths := []string{filepath.Join(root, "first.wav"), filepath.Join(root, "second.wav"), filepath.Join(root, "other.wav")}
	for _, path := range paths {
		require.NoError(t, os.WriteFile(path, []byte("synthetic recording"), 0600))
	}
	parent := models.TranscriptionJob{
		ID: "multi-parent", Status: models.StatusProcessing, AudioPath: paths[0], IsMultiTrack: true,
		Parameters: models.WhisperXParams{ModelFamily: FamilyWhisper, IsMultiTrackEnabled: true},
	}
	require.NoError(t, repo.Create(ctx, &parent))
	for i, path := range paths[:2] {
		track := models.MultiTrackFile{TranscriptionJobID: parent.ID, FilePath: path, FileName: filepath.Base(path), Offset: float64(i)}
		require.NoError(t, db.Create(&track).Error)
	}
	other := models.TranscriptionJob{ID: "competing-job", Status: models.StatusProcessing, AudioPath: paths[2], Parameters: models.WhisperXParams{ModelFamily: FamilyWhisper}}
	require.NoError(t, repo.Create(ctx, &other))
	processor := NewUnifiedJobProcessor(repo, cfg.TempDir, cfg.TranscriptsDir)
	parentDone, otherDone := make(chan error, 1), make(chan error, 1)
	go func() { parentDone <- processor.ProcessJob(ctx, parent.ID) }()
	t.Cleanup(func() { cancel(); close(adapter.release) })
	nextStarted := func() string {
		t.Helper()
		select {
		case path := <-adapter.started:
			return path
		case <-ctx.Done():
			t.Fatal("inference did not start before the bounded deadline")
			return ""
		}
	}
	require.Equal(t, paths[0], nextStarted())
	go func() { otherDone <- processor.ProcessJob(ctx, other.ID) }()
	adapter.release <- struct{}{}
	require.Equal(t, paths[1], nextStarted(), "second track keeps the parent's slot ahead of the competing job")
	adapter.release <- struct{}{}
	require.Equal(t, paths[2], nextStarted(), "other inference runs only after the complete parent workflow releases admission")
	adapter.release <- struct{}{}
	for _, done := range []chan error{parentDone, otherDone} {
		select {
		case err := <-done:
			require.NoError(t, err)
		case <-ctx.Done():
			t.Fatal("processing exceeded its bounded deadline")
		}
	}
	require.EqualValues(t, 1, adapter.maximum.Load(), "nested tracks must not add inference concurrency")
	require.Zero(t, adapter.active.Load())
	stored, err := repo.FindByID(ctx, parent.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusCompleted, stored.Status)
	require.NotNil(t, stored.Transcript)
	var transcript interfaces.TranscriptResult
	require.NoError(t, json.Unmarshal([]byte(*stored.Transcript), &transcript))
	require.Len(t, transcript.WordSegments, 2)
	require.Contains(t, transcript.Text, "first.wav")
	require.Contains(t, transcript.Text, "second.wav")
}

func TestProcessorWithoutAdmissionFailsImmediately(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	processor := &UnifiedJobProcessor{unifiedService: &UnifiedTranscriptionService{}}
	require.ErrorContains(t, processor.ProcessJob(ctx, "unconfigured"), "inference admission is not configured")
	require.NoError(t, ctx.Err(), "invalid construction must fail before waiting for cancellation")
}
