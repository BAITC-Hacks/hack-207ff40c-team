package transcription

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/config"
	"scriberr/internal/models"
	"scriberr/internal/repository"
)

type quickFakeProcessor struct {
	repo          repository.JobRepository
	block         <-chan struct{}
	missingResult bool
}

func (p quickFakeProcessor) ProcessJob(ctx context.Context, id string) error {
	if p.block != nil {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-p.block:
		}
	}
	if p.missingResult {
		return nil
	}
	return p.repo.UpdateTranscript(ctx, id, `{"text":"synthetic result"}`)
}
func quickFixture(t *testing.T) (*config.Config, repository.JobRepository, *gorm.DB) {
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	sql, _ := db.DB()
	sql.SetMaxOpenConns(1)
	t.Cleanup(func() { sql.Close() })
	require.NoError(t, db.AutoMigrate(&models.TranscriptionJob{}, &models.TranscriptionJobExecution{}, &models.ChatSession{}, &models.ChatMessage{}, &models.Note{}, &models.Summary{}, &models.SpeakerMapping{}, &models.MultiTrackFile{}))
	root := t.TempDir()
	return &config.Config{UploadDir: filepath.Join(root, "uploads"), TempDir: filepath.Join(root, "temp"), TranscriptsDir: filepath.Join(root, "transcripts")}, repository.NewJobRepository(db), db
}
func TestQuickSnapshotsAdmissionAndCancellation(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	block := make(chan struct{})
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo, block: block}, repo)
	require.NoError(t, err)
	defer qs.Close()
	language := "kk"
	first, err := qs.SubmitQuickJob(strings.NewReader("fake"), "a.wav", models.WhisperXParams{Language: &language})
	require.NoError(t, err)
	*first.Parameters.Language = "changed response"
	copy, err := qs.GetQuickJob(first.ID)
	require.NoError(t, err)
	require.Equal(t, "kk", *copy.Parameters.Language)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 50; j++ {
				job, err := qs.GetQuickJob(first.ID)
				if err == nil {
					_, _ = json.Marshal(job)
				}
			}
		}()
	}
	for i := 0; i < 15; i++ {
		_, err = qs.SubmitQuickJob(strings.NewReader("fake"), "b.wav", models.WhisperXParams{})
		require.NoError(t, err)
	}
	_, err = qs.SubmitQuickJob(strings.NewReader("fake"), "overflow.wav", models.WhisperXParams{})
	require.ErrorIs(t, err, ErrQuickQueueFull)
	wg.Wait()
	done := make(chan struct{})
	go func() { qs.Close(); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("shutdown did not cancel inference")
	}
}
func TestQuickMissingResultFailsAndRetainsRecoverableRow(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo, missingResult: true}, repo)
	require.NoError(t, err)
	defer qs.Close()
	job, err := qs.SubmitQuickJob(strings.NewReader("fake"), "a.wav", models.WhisperXParams{})
	require.NoError(t, err)
	require.Eventually(t, func() bool { current, _ := qs.GetQuickJob(job.ID); return current.Status == models.StatusFailed }, time.Second, time.Millisecond)
	current, _ := qs.GetQuickJob(job.ID)
	require.Contains(t, *current.ErrorMessage, "no transcript")
	_, err = repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
}
func TestQuickExpirySurvivesRestartAndPurgesRealArtifacts(t *testing.T) {
	cfg, repo, db := quickFixture(t)
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo}, repo)
	require.NoError(t, err)
	job, err := qs.SubmitQuickJob(strings.NewReader("fake"), "a.wav", models.WhisperXParams{})
	require.NoError(t, err)
	require.Eventually(t, func() bool { current, _ := qs.GetQuickJob(job.ID); return current.Status == models.StatusCompleted }, time.Second, time.Millisecond)
	qs.Close()
	qs.jobsMutex.Lock()
	qs.jobs[job.ID].ExpiresAt = time.Now().Add(-time.Second)
	require.NoError(t, qs.persist(qs.jobs[job.ID]))
	qs.jobsMutex.Unlock()
	output := filepath.Join(cfg.TranscriptsDir, job.ID)
	require.NoError(t, os.MkdirAll(output, 0700))
	require.NoError(t, os.WriteFile(filepath.Join(output, "private.json"), []byte("secret"), 0600))
	reopened, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo}, repo)
	require.NoError(t, err)
	defer reopened.Close()
	_, err = reopened.GetQuickJob(job.ID)
	require.Error(t, err)
	require.NoFileExists(t, job.AudioPath)
	require.NoDirExists(t, output)
	var count int64
	require.NoError(t, db.Unscoped().Model(&models.TranscriptionJob{}).Where("id = ?", job.ID).Count(&count).Error)
	require.Zero(t, count)
}
func TestQuickLegacyOrphanExpiry(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	dir := filepath.Join(cfg.UploadDir, "quick_transcriptions")
	require.NoError(t, os.MkdirAll(dir, 0700))
	id := uuid.NewString()
	path := filepath.Join(dir, id+".wav")
	require.NoError(t, os.WriteFile(path, []byte("old private audio"), 0600))
	old := time.Now().Add(-7 * time.Hour)
	require.NoError(t, os.Chtimes(path, old, old))
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo}, repo)
	require.NoError(t, err)
	defer qs.Close()
	require.NoFileExists(t, path)
}
func TestQuickManifestFailureNeverPublishesCompleted(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	block := make(chan struct{})
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo, block: block}, repo)
	require.NoError(t, err)
	defer qs.Close()
	job, err := qs.SubmitQuickJob(strings.NewReader("fake"), "a.wav", models.WhisperXParams{})
	require.NoError(t, err)
	require.Eventually(t, func() bool { _, e := repo.FindByID(context.Background(), job.ID); return e == nil }, time.Second, time.Millisecond)
	// A directory at the target blocks atomic manifest replacement even as root.
	manifest := filepath.Join(qs.tempDir, job.ID+".job.json")
	require.NoError(t, os.Remove(manifest))
	require.NoError(t, os.Mkdir(manifest, 0700))
	close(block)
	require.Eventually(t, func() bool { current, _ := qs.GetQuickJob(job.ID); return current.Status == models.StatusFailed }, time.Second, time.Millisecond)
	current, _ := qs.GetQuickJob(job.ID)
	require.Contains(t, *current.ErrorMessage, "cannot save quick result")
	stored, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.NotNil(t, stored.Transcript, fmt.Sprint(current))
}

func TestYoungLegacyOrphanExpiresWithoutRestart(t *testing.T) {
	cfg, repo, _ := quickFixture(t)
	dir := filepath.Join(cfg.UploadDir, "quick_transcriptions")
	require.NoError(t, os.MkdirAll(dir, 0700))
	id := uuid.NewString()
	path := filepath.Join(dir, id+".wav")
	require.NoError(t, os.WriteFile(path, []byte("private"), 0600))
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo}, repo)
	require.NoError(t, err)
	defer qs.Close()
	require.FileExists(t, path)
	expired := time.Now().Add(-7 * time.Hour)
	require.NoError(t, os.Chtimes(path, expired, expired))
	require.NoError(t, qs.cleanupLegacyOrphans())
	require.NoFileExists(t, path)
}

func TestLegacyQuickOutputWithoutSourceStillExpires(t *testing.T) {
	cfg, repo, db := quickFixture(t)
	id := uuid.NewString()
	source := filepath.Join(cfg.UploadDir, "quick_transcriptions", id+".wav")
	job := models.TranscriptionJob{ID: id, AudioPath: source, Status: models.StatusCompleted, CreatedAt: time.Now().Add(-7 * time.Hour)}
	require.NoError(t, repo.Create(context.Background(), &job))
	require.NoError(t, repo.Delete(context.Background(), id))
	output := filepath.Join(cfg.TranscriptsDir, id)
	require.NoError(t, os.MkdirAll(output, 0700))
	require.NoError(t, os.WriteFile(filepath.Join(output, "sensitive.json"), []byte("private"), 0600))
	qs, err := NewQuickTranscriptionService(cfg, quickFakeProcessor{repo: repo}, repo)
	require.NoError(t, err)
	defer qs.Close()
	require.NoDirExists(t, output)
	var count int64
	require.NoError(t, db.Unscoped().Model(&models.TranscriptionJob{}).Where("id = ?", id).Count(&count).Error)
	require.Zero(t, count)
}
