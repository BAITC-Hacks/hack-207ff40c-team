package api

import (
	"context"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/models"
	"scriberr/internal/queue"
	"scriberr/internal/repository"
)

type earlyCompletionProcessor struct {
	repo      repository.JobRepository
	published chan error
	release   chan struct{}
}

func (p *earlyCompletionProcessor) ProcessJob(ctx context.Context, id string) error {
	// The retained multi-track pipeline publishes the result before its final
	// execution record and cleanup finish. A completed row is still owned.
	err := p.repo.UpdateStatus(ctx, id, models.StatusCompleted)
	p.published <- err
	<-p.release
	return err
}
func (p *earlyCompletionProcessor) ProcessJobWithProcess(ctx context.Context, id string, _ func(*exec.Cmd)) error {
	return p.ProcessJob(ctx, id)
}

func TestDeletionRejectsCompletedJobStillOwnedByProcessor(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "1")
	h, db := regressionHandler(t)
	path := filepath.Join(t.TempDir(), "synthetic-track.wav")
	require.NoError(t, os.WriteFile(path, []byte("synthetic recording"), 0600))
	job := models.TranscriptionJob{ID: "finishing-multitrack", Status: models.StatusPending, AudioPath: path}
	require.NoError(t, db.Create(&job).Error)
	p := &earlyCompletionProcessor{repo: h.jobRepo, published: make(chan error, 1), release: make(chan struct{})}
	h.taskQueue = queue.NewTaskQueue(1, p, h.jobRepo)
	var release sync.Once
	t.Cleanup(func() { release.Do(func() { close(p.release) }); h.taskQueue.Stop() })
	h.taskQueue.Start()
	select {
	case err := <-p.published:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("processor did not publish its result")
	}
	w := requestHandler(http.MethodDelete, "/jobs/"+job.ID, nil, h.DeleteTranscriptionJob)
	require.Equal(t, http.StatusConflict, w.Code, w.Body.String())
	require.FileExists(t, path)
	stored, err := h.jobRepo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusCompleted, stored.Status, "rejection must not write deletion intent")
	require.True(t, h.taskQueue.IsJobRunning(job.ID))

	release.Do(func() { close(p.release) })
	require.Eventually(t, func() bool { return !h.taskQueue.IsJobRunning(job.ID) }, 2*time.Second, time.Millisecond)
	w = requestHandler(http.MethodDelete, "/jobs/"+job.ID, nil, h.DeleteTranscriptionJob)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	require.NoFileExists(t, path)
	_, err = h.jobRepo.FindByID(context.Background(), job.ID)
	require.ErrorIs(t, err, gorm.ErrRecordNotFound)
}
