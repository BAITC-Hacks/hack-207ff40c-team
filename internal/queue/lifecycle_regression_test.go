package queue

import (
	"context"
	"errors"
	"os/exec"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/glebarez/sqlite"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/models"
	"scriberr/internal/repository"
)

func lifecycleRepository(t *testing.T) repository.JobRepository {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	sql, err := db.DB()
	require.NoError(t, err)
	sql.SetMaxOpenConns(1)
	t.Cleanup(func() { require.NoError(t, sql.Close()) })
	require.NoError(t, db.AutoMigrate(&models.TranscriptionJob{}))
	return repository.NewJobRepository(db)
}

type delayedCleanupProcessor struct {
	started           chan context.Context
	release           chan struct{}
	calls             atomic.Int32
	legacyTermination atomic.Bool
}

func (p *delayedCleanupProcessor) ProcessJob(ctx context.Context, id string) error {
	return p.ProcessJobWithProcess(ctx, id, nil)
}
func (p *delayedCleanupProcessor) ProcessJobWithProcess(ctx context.Context, _ string, _ func(*exec.Cmd)) error {
	p.calls.Add(1)
	p.started <- ctx
	<-p.release // Model an adapter waiting for its canceled child to finish cleanup.
	return ctx.Err()
}
func (p *delayedCleanupProcessor) IsMultiTrackJob(string) bool { return true }
func (p *delayedCleanupProcessor) TerminateMultiTrackJob(string) error {
	p.legacyTermination.Store(true)
	return nil
}

func TestCanceledJobStaysOwnedUntilProcessorCleanupEnds(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "2")
	repo := lifecycleRepository(t)
	job := models.TranscriptionJob{ID: "canceling", Status: models.StatusPending, AudioPath: "source.wav"}
	require.NoError(t, repo.Create(context.Background(), &job))
	p := &delayedCleanupProcessor{started: make(chan context.Context, 4), release: make(chan struct{})}
	q := NewTaskQueue(2, p, repo)
	var release sync.Once
	t.Cleanup(func() { release.Do(func() { close(p.release) }); q.Stop() })
	q.Start()
	select {
	case <-p.started:
	case <-time.After(2 * time.Second):
		t.Fatal("processor did not start")
	}
	require.NoError(t, q.KillJob(job.ID))
	require.False(t, p.legacyTermination.Load(), "multi-track cleanup must not delete records before its processor exits")
	require.True(t, q.IsJobRunning(job.ID))
	stored, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusProcessing, stored.Status)
	deleter := repo.(interface {
		BeginDeletion(context.Context, string) error
	})
	require.ErrorIs(t, deleter.BeginDeletion(context.Background(), job.ID), repository.ErrJobConflict)
	prepared := false
	require.ErrorIs(t, q.EnqueuePreparedJob(job.ID, func() error { prepared = true; return nil }), repository.ErrJobConflict)
	require.False(t, prepared)
	require.EqualValues(t, 1, p.calls.Load())

	release.Do(func() { close(p.release) })
	require.Eventually(t, func() bool { return !q.IsJobRunning(job.ID) }, 2*time.Second, time.Millisecond)
	stored, err = repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusFailed, stored.Status)
	require.Contains(t, *stored.ErrorMessage, "cancelled")
	scheduler := repo.(interface {
		Schedule(context.Context, *models.TranscriptionJob) error
	})
	require.NoError(t, q.EnqueuePreparedJob(job.ID, func() error { return scheduler.Schedule(context.Background(), stored) }))
	require.Eventually(t, func() bool { return p.calls.Load() == 2 && !q.IsJobRunning(job.ID) }, 2*time.Second, time.Millisecond)
	stored, err = repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusCompleted, stored.Status)
}

func TestKillDoesNotFailUnownedProcessingJob(t *testing.T) {
	repo := lifecycleRepository(t)
	job := models.TranscriptionJob{ID: "direct-inference", Status: models.StatusProcessing, AudioPath: "source.wav"}
	require.NoError(t, repo.Create(context.Background(), &job))
	q := NewTaskQueue(1, nil, repo)
	defer q.Stop()
	require.ErrorContains(t, q.KillJob(job.ID), "not currently running")
	stored, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusProcessing, stored.Status)
	require.Nil(t, stored.ErrorMessage)
}

type gatedClaimRepository struct {
	repository.JobRepository
	claimed chan struct{}
	release chan struct{}
}

func (r *gatedClaimRepository) Claim(ctx context.Context, id string) (bool, error) {
	claimed, err := r.JobRepository.(interface {
		Claim(context.Context, string) (bool, error)
	}).Claim(ctx, id)
	if claimed && err == nil {
		close(r.claimed)
		<-r.release
	}
	return claimed, err
}

func TestKillCannotTreatUnregisteredDatabaseClaimAsZombie(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "1")
	repo := &gatedClaimRepository{JobRepository: lifecycleRepository(t), claimed: make(chan struct{}), release: make(chan struct{})}
	job := models.TranscriptionJob{ID: "claiming", Status: models.StatusPending, AudioPath: "source.wav"}
	require.NoError(t, repo.Create(context.Background(), &job))
	p := &delayedCleanupProcessor{started: make(chan context.Context, 1), release: make(chan struct{})}
	q := NewTaskQueue(1, p, repo)
	var releaseClaim, releaseProcessor sync.Once
	t.Cleanup(func() {
		releaseClaim.Do(func() { close(repo.release) })
		releaseProcessor.Do(func() { close(p.release) })
		q.Stop()
	})
	q.Start()
	select {
	case <-repo.claimed:
	case <-time.After(2 * time.Second):
		t.Fatal("database claim did not commit")
	}
	// The database transition is paused before Claim returns to the worker.
	// KillJob's ownership lock must already protect this exact boundary.
	unlocked := q.jobsMutex.TryLock()
	if unlocked {
		q.jobsMutex.Unlock()
	}
	require.False(t, unlocked, "KillJob must not see a processing row without its in-flight claim ownership")
	killed := make(chan error, 1)
	go func() { killed <- q.KillJob(job.ID) }()
	releaseClaim.Do(func() { close(repo.release) })
	select {
	case err := <-killed:
		require.NoError(t, err)
	case <-time.After(2 * time.Second):
		t.Fatal("cancellation remained blocked after the claim completed")
	}
	stored, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusProcessing, stored.Status)
	require.True(t, q.IsJobRunning(job.ID))
	releaseProcessor.Do(func() { close(p.release) })
	require.Eventually(t, func() bool { return !q.IsJobRunning(job.ID) }, 2*time.Second, time.Millisecond)
	stored, err = repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusFailed, stored.Status)
}

type gatedFinalizationRepository struct {
	repository.JobRepository
	finishing chan struct{}
	release   chan struct{}
}

func (r *gatedFinalizationRepository) Claim(ctx context.Context, id string) (bool, error) {
	return r.JobRepository.(interface {
		Claim(context.Context, string) (bool, error)
	}).Claim(ctx, id)
}
func (r *gatedFinalizationRepository) UpdateError(ctx context.Context, id, message string) error {
	close(r.finishing)
	<-r.release
	return r.JobRepository.UpdateError(ctx, id, message)
}

type failedProcessor struct{}

func (failedProcessor) ProcessJob(context.Context, string) error {
	return errors.New("synthetic failure")
}
func (p failedProcessor) ProcessJobWithProcess(ctx context.Context, id string, _ func(*exec.Cmd)) error {
	return p.ProcessJob(ctx, id)
}

func TestFinalStatusAndErrorWriteKeepRunningOwnership(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "1")
	repo := &gatedFinalizationRepository{JobRepository: lifecycleRepository(t), finishing: make(chan struct{}), release: make(chan struct{})}
	job := models.TranscriptionJob{ID: "finishing", Status: models.StatusPending, AudioPath: "source.wav"}
	require.NoError(t, repo.Create(context.Background(), &job))
	q := NewTaskQueue(1, failedProcessor{}, repo)
	var release sync.Once
	t.Cleanup(func() { release.Do(func() { close(repo.release) }); q.Stop() })
	q.Start()
	select {
	case <-repo.finishing:
	case <-time.After(2 * time.Second):
		t.Fatal("worker did not reach its final error write")
	}
	// No worker can change this map until the gated repository is released;
	// the channel also synchronizes all writes before this inspection.
	require.Contains(t, q.runningJobs, job.ID, "final error writes must not outlive execution ownership")
	unlocked := q.jobsMutex.TryLock()
	if unlocked {
		q.jobsMutex.Unlock()
	}
	require.False(t, unlocked, "admission must wait for the final error write")
	release.Do(func() { close(repo.release) })
	require.Eventually(t, func() bool { return !q.IsJobRunning(job.ID) }, 2*time.Second, time.Millisecond)
	stored, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusFailed, stored.Status)
	require.Equal(t, "synthetic failure", *stored.ErrorMessage)
}
