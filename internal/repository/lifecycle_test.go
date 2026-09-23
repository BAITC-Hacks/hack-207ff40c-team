package repository

import (
	"context"
	"fmt"
	"sync"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/models"
)

func lifecycleDB(t *testing.T) *gorm.DB {
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	sql, err := db.DB()
	require.NoError(t, err)
	sql.SetMaxOpenConns(1)
	t.Cleanup(func() { sql.Close() })
	require.NoError(t, db.AutoMigrate(&models.User{}, &models.TranscriptionJob{}))
	return db
}

func TestConcurrentInitialAdminHasOneWinner(t *testing.T) {
	repo := NewUserRepository(lifecycleDB(t)).(*userRepository)
	var wg sync.WaitGroup
	outcomes := make(chan error, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			outcomes <- repo.CreateInitialAdmin(context.Background(), &models.User{Username: fmt.Sprint("admin", i), Password: "already-hashed-test-password"})
		}(i)
	}
	wg.Wait()
	close(outcomes)
	winners := 0
	for err := range outcomes {
		if err == nil {
			winners++
		} else {
			require.ErrorIs(t, err, ErrAlreadyRegistered)
		}
	}
	require.Equal(t, 1, winners)
	count, err := repo.Count(context.Background())
	require.NoError(t, err)
	require.EqualValues(t, 1, count)
}

func TestSchedulingAndClaimAreAtomicAndPreserveResult(t *testing.T) {
	db := lifecycleDB(t)
	repo := NewJobRepository(db).(*jobRepository)
	old := "prior transcript"
	summary := "prior summary"
	job := models.TranscriptionJob{ID: "rerun", AudioPath: "audio.wav", Status: models.StatusCompleted, Transcript: &old, Summary: &summary, Parameters: models.WhisperXParams{Model: "old"}}
	require.NoError(t, repo.Create(context.Background(), &job))
	var wg sync.WaitGroup
	outcomes := make(chan error, 12)
	for i := 0; i < 12; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			copy := job
			copy.Parameters.Model = "new"
			outcomes <- repo.Schedule(context.Background(), &copy)
		}()
	}
	wg.Wait()
	close(outcomes)
	winners := 0
	for err := range outcomes {
		if err == nil {
			winners++
		} else {
			require.ErrorIs(t, err, ErrJobConflict)
		}
	}
	require.Equal(t, 1, winners)
	result, err := repo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, "new", result.Parameters.Model)
	require.Equal(t, old, *result.Transcript)
	require.Equal(t, summary, *result.Summary)
	claimed, err := repo.Claim(context.Background(), job.ID)
	require.NoError(t, err)
	require.True(t, claimed)
	claimed, err = repo.Claim(context.Background(), job.ID)
	require.NoError(t, err)
	require.False(t, claimed)
}

func TestRepositoryRejectsSortExpressions(t *testing.T) {
	repo := NewJobRepository(lifecycleDB(t))
	for _, value := range []string{"(SELECT password FROM users)", "title desc; DELETE FROM users", "random()"} {
		_, _, err := repo.ListWithParams(context.Background(), 0, 10, value, "asc", "", nil)
		require.Error(t, err)
	}
	_, _, err := repo.ListWithParams(context.Background(), 0, 10, "title", "asc", "", nil)
	require.NoError(t, err)
}
