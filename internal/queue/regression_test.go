package queue

import (
	"context"
	"fmt"
	"github.com/glebarez/sqlite"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"os/exec"
	"scriberr/internal/models"
	"scriberr/internal/repository"
	"sync"
	"testing"
	"time"
)

type countingProcessor struct {
	mu       sync.Mutex
	calls    map[string]int
	contexts []context.Context
}

func (p *countingProcessor) ProcessJob(ctx context.Context, id string) error {
	return p.ProcessJobWithProcess(ctx, id, nil)
}
func (p *countingProcessor) ProcessJobWithProcess(ctx context.Context, id string, _ func(*exec.Cmd)) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.calls[id]++
	p.contexts = append(p.contexts, ctx)
	return nil
}

func TestRecoveryExceedsBufferAndReleasesEachContext(t *testing.T) {
	t.Setenv("QUEUE_WORKERS", "2")
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	sql, _ := db.DB()
	sql.SetMaxOpenConns(1)
	defer sql.Close()
	require.NoError(t, db.AutoMigrate(&models.TranscriptionJob{}))
	repo := repository.NewJobRepository(db)
	for i := 0; i < 225; i++ {
		require.NoError(t, repo.Create(context.Background(), &models.TranscriptionJob{ID: fmt.Sprint(i), Status: models.StatusPending, AudioPath: "a"}))
	}
	processor := &countingProcessor{calls: map[string]int{}}
	queue := NewTaskQueue(2, processor, repo)
	queue.Start()
	defer queue.Stop()
	require.Eventually(t, func() bool { processor.mu.Lock(); defer processor.mu.Unlock(); return len(processor.calls) == 225 }, 10*time.Second, 10*time.Millisecond)
	require.Eventually(t, func() bool {
		processor.mu.Lock()
		defer processor.mu.Unlock()
		for _, ctx := range processor.contexts {
			if ctx.Err() != context.Canceled {
				return false
			}
		}
		return queue.ctx.Err() == nil
	}, time.Second, time.Millisecond)
	// Duplicate deliveries must not run an already-completed execution.
	require.NoError(t, queue.EnqueueJob("0"))
	queue.Stop()
	processor.mu.Lock()
	defer processor.mu.Unlock()
	require.Len(t, processor.calls, 225)
	for id, count := range processor.calls {
		require.Equal(t, 1, count, id)
	}
	for _, ctx := range processor.contexts {
		require.ErrorIs(t, ctx.Err(), context.Canceled)
	}
}

func TestFullQueueDoesNotMutateTheJob(t *testing.T) {
	queue := NewTaskQueue(1, nil, nil)
	defer queue.Stop()
	for i := 0; i < 200; i++ {
		require.NoError(t, queue.EnqueueJob(fmt.Sprint(i)))
	}
	prepared := false
	err := queue.EnqueuePreparedJob("rerun", func() error { prepared = true; return nil })
	require.Error(t, err)
	require.False(t, prepared)
}
