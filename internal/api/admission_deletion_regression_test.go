package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/models"
	"scriberr/internal/repository"
	"scriberr/internal/service"
)

// The first Schedule update has committed to the transaction when its parameter
// write fails. This exercises rollback after the caller's status was mutated.
func failSchedulingParameters(t *testing.T, db *gorm.DB) *bool {
	t.Helper()
	failed := false
	const name = "test:fail-scheduling-parameters"
	require.NoError(t, db.Callback().Update().Before("gorm:update").Register(name, func(tx *gorm.DB) {
		if tx.Statement.Table == "transcription_jobs" && len(tx.Statement.Selects) > 0 {
			failed = true
			tx.AddError(errors.New("synthetic parameter write failure"))
		}
	}))
	t.Cleanup(func() { require.NoError(t, db.Callback().Update().Remove(name)) })
	return &failed
}

func TestAutoUploadAdmissionFailureReturnsPersistedJob(t *testing.T) {
	for _, media := range []string{"audio", "video"} {
		for _, failure := range []string{"queue-full", "transaction-rollback"} {
			t.Run(media+"/"+failure, func(t *testing.T) {
				h, db := regressionHandler(t)
				require.NoError(t, db.AutoMigrate(&models.TranscriptionProfile{}))
				profile := models.TranscriptionProfile{Name: "auto profile", Parameters: models.WhisperXParams{Model: "profile-not-committed", Diarize: true, BatchSize: 32}}
				require.NoError(t, db.Create(&profile).Error)
				user := models.User{Username: "test-secretary", Password: "unused", AutoTranscriptionEnabled: true, DefaultProfileID: &profile.ID}
				require.NoError(t, db.Create(&user).Error)
				h.profileRepo = repository.NewProfileRepository(db)
				h.userService = service.NewUserService(h.userRepo, h.authService)
				var failed *bool
				if failure == "queue-full" {
					for i := 0; i < 200; i++ {
						require.NoError(t, h.taskQueue.EnqueueJob(fmt.Sprintf("occupied-%d", i)))
					}
				} else {
					failed = failSchedulingParameters(t, db)
				}

				filename := "synthetic.wav"
				handler := h.UploadAudio
				if media == "video" {
					filename, handler = "synthetic.mp4", h.UploadVideo
					// Only the ffmpeg process is substituted; upload, filesystem,
					// admission and SQLite transactions are the real implementations.
					bin := t.TempDir()
					require.NoError(t, os.WriteFile(filepath.Join(bin, "ffmpeg"), []byte("#!/bin/sh\nfor output do :; done\nprintf 'synthetic audio' > \"$output\"\n"), 0700))
					t.Setenv("PATH", bin+string(os.PathListSeparator)+os.Getenv("PATH"))
				}
				var body bytes.Buffer
				form := multipart.NewWriter(&body)
				part, err := form.CreateFormFile(media, filename)
				require.NoError(t, err)
				_, err = part.Write([]byte("synthetic media"))
				require.NoError(t, err)
				require.NoError(t, form.Close())
				router := gin.New()
				router.POST("/upload", func(c *gin.Context) { c.Set("user_id", user.ID); handler(c) })
				req := httptest.NewRequest(http.MethodPost, "/upload", &body)
				req.Header.Set("Content-Type", form.FormDataContentType())
				w := httptest.NewRecorder()
				router.ServeHTTP(w, req)
				require.Equal(t, http.StatusOK, w.Code, w.Body.String())
				var response models.TranscriptionJob
				require.NoError(t, json.Unmarshal(w.Body.Bytes(), &response))
				stored, err := h.jobRepo.FindByID(context.Background(), response.ID)
				require.NoError(t, err)
				require.Equal(t, models.StatusUploaded, stored.Status)
				require.NotEqual(t, profile.Parameters.Model, stored.Parameters.Model)
				persisted, err := json.Marshal(stored)
				require.NoError(t, err)
				require.JSONEq(t, string(persisted), w.Body.String(), "upload receipt must describe the persisted job")
				require.FileExists(t, stored.AudioPath)
				if failed != nil {
					require.True(t, *failed, "must reach the second Schedule write")
					require.Equal(t, 0, h.taskQueue.GetQueueStats()["queue_size"])
				} else {
					require.Equal(t, 200, h.taskQueue.GetQueueStats()["queue_size"])
				}
			})
		}
	}
}

func TestEnqueueRollbackRestoresCallerSnapshot(t *testing.T) {
	h, db := regressionHandler(t)
	old := "previous transcript"
	job := models.TranscriptionJob{ID: "previous-job", Status: models.StatusCompleted, AudioPath: "recording.wav", Transcript: &old, Summary: &old}
	require.NoError(t, db.Create(&job).Error)
	failed := failSchedulingParameters(t, db)
	job.Parameters.Model = "not-committed"
	job.Diarization = true
	require.ErrorContains(t, h.enqueueTranscription(context.Background(), &job), "synthetic parameter write failure")
	require.True(t, *failed)
	stored, err := h.jobRepo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.StatusCompleted, job.Status)
	require.Equal(t, stored.Parameters, job.Parameters)
	require.Equal(t, stored.Diarization, job.Diarization)
	require.Equal(t, old, *job.Transcript)
	require.Equal(t, old, *job.Summary)
	require.Equal(t, 0, h.taskQueue.GetQueueStats()["queue_size"])
}

func TestDeletionDatabaseFailureRollsBackChildrenAndRetries(t *testing.T) {
	h, db := regressionHandler(t)
	path := filepath.Join(t.TempDir(), "synthetic-recording.wav")
	require.NoError(t, os.WriteFile(path, []byte("synthetic private audio"), 0600))
	text := "synthetic private transcript"
	job := models.TranscriptionJob{ID: "delete-job", Status: models.StatusCompleted, AudioPath: path, Transcript: &text, Summary: &text}
	require.NoError(t, db.Create(&job).Error)
	session := models.ChatSession{ID: "delete-session", JobID: job.ID, TranscriptionID: job.ID, Model: "local-test"}
	require.NoError(t, db.Create(&session).Error)
	message := models.ChatMessage{ChatSessionID: session.ID, Role: "user", Content: "synthetic private message"}
	require.NoError(t, db.Create(&message).Error)
	note := models.Note{ID: "delete-note", TranscriptionID: job.ID, Quote: "synthetic quote", Content: "synthetic annotation"}
	require.NoError(t, db.Create(&note).Error)

	const callback = "test:fail-notes-deletion"
	childrenDeletedBeforeFailure := false
	require.NoError(t, db.Callback().Delete().Before("gorm:delete").Register(callback, func(tx *gorm.DB) {
		if tx.Statement.Table != "notes" {
			return
		}
		// Observe real earlier deletes inside the same transaction, so rollback
		// assertions cannot pass by injecting an error before any work happened.
		var messages, sessions int64
		q := tx.Session(&gorm.Session{NewDB: true})
		require.NoError(t, q.Model(&models.ChatMessage{}).Where("chat_session_id = ?", session.ID).Count(&messages).Error)
		require.NoError(t, q.Model(&models.ChatSession{}).Where("id = ?", session.ID).Count(&sessions).Error)
		childrenDeletedBeforeFailure = messages == 0 && sessions == 0
		tx.AddError(errors.New("synthetic database finalization failure"))
	}))
	w := requestHandler(http.MethodDelete, "/jobs/"+job.ID, nil, h.DeleteTranscriptionJob)
	require.Equal(t, http.StatusInternalServerError, w.Code, w.Body.String())
	require.True(t, childrenDeletedBeforeFailure)
	require.NoFileExists(t, path)
	stored, err := h.jobRepo.FindByID(context.Background(), job.ID)
	require.NoError(t, err)
	require.Equal(t, models.JobStatus("deleting"), stored.Status)
	require.Equal(t, text, *stored.Transcript)
	for _, model := range []any{&models.ChatSession{}, &models.ChatMessage{}, &models.Note{}} {
		var count int64
		require.NoError(t, db.Model(model).Count(&count).Error)
		require.EqualValues(t, 1, count, "earlier child deletes must be rolled back")
	}

	require.NoError(t, db.Callback().Delete().Remove(callback))
	w = requestHandler(http.MethodDelete, "/jobs/"+job.ID, nil, h.DeleteTranscriptionJob)
	require.Equal(t, http.StatusOK, w.Code, w.Body.String())
	_, err = h.jobRepo.FindByID(context.Background(), job.ID)
	require.ErrorIs(t, err, gorm.ErrRecordNotFound)
	var tombstone models.TranscriptionJob
	require.NoError(t, db.Unscoped().First(&tombstone, "id = ?", job.ID).Error)
	require.True(t, tombstone.DeletedAt.Valid)
	require.Equal(t, models.JobStatus("deleted"), tombstone.Status)
	require.Empty(t, tombstone.AudioPath)
	require.Nil(t, tombstone.Transcript)
	require.Nil(t, tombstone.Summary)
	for _, model := range []any{&models.ChatSession{}, &models.ChatMessage{}, &models.Note{}} {
		var count int64
		require.NoError(t, db.Unscoped().Model(model).Count(&count).Error)
		require.Zero(t, count)
	}
}
