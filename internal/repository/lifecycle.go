package repository

import (
	"context"
	"errors"
	"path/filepath"
	"time"

	"gorm.io/gorm"
	"scriberr/internal/models"
)

var ErrAlreadyRegistered = errors.New("an administrator already exists")
var ErrJobConflict = errors.New("job state changed; reload and retry")

// CreateInitialAdmin is one database statement. SQLite serializes writers, so
// concurrent processes cannot both satisfy NOT EXISTS before inserting.
func (r *userRepository) CreateInitialAdmin(ctx context.Context, user *models.User) error {
	now := time.Now()
	result := r.db.WithContext(ctx).Exec(`INSERT INTO users (username, password, auto_transcription_enabled, created_at, updated_at)
 SELECT ?, ?, false, ?, ? WHERE NOT EXISTS (SELECT 1 FROM users)`, user.Username, user.Password, now, now)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return ErrAlreadyRegistered
	}
	return r.db.WithContext(ctx).Where("username = ?", user.Username).First(user).Error
}

// Schedule preserves the prior transcript and summary until replacement succeeds.
func (r *jobRepository) Schedule(ctx context.Context, job *models.TranscriptionJob) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		result := tx.Model(&models.TranscriptionJob{}).Where("id = ? AND status IN ?", job.ID,
			[]models.JobStatus{models.StatusUploaded, models.StatusCompleted, models.StatusFailed}).Update("status", models.StatusPending)
		if result.Error != nil {
			return result.Error
		}
		if result.RowsAffected != 1 {
			return ErrJobConflict
		}
		job.Status = models.StatusPending
		statement := &gorm.Statement{DB: tx}
		if err := statement.Parse(job); err != nil {
			return err
		}
		columns := []string{"diarization", "error_message"}
		for _, field := range statement.Schema.Fields {
			if len(field.BindNames) > 0 && field.BindNames[0] == "Parameters" {
				columns = append(columns, field.DBName)
			}
		}
		return tx.Model(job).Select(columns).Updates(job).Error
	})
}

// Claim prevents duplicate channel deliveries from running the same job twice.
func (r *jobRepository) Claim(ctx context.Context, id string) (bool, error) {
	result := r.db.WithContext(ctx).Model(&models.TranscriptionJob{}).Where("id = ? AND status = ?", id, models.StatusPending).Update("status", models.StatusProcessing)
	return result.RowsAffected == 1, result.Error
}

// BeginDeletion records an idempotent intent before touching the filesystem.
func (r *jobRepository) BeginDeletion(ctx context.Context, id string) error {
	result := r.db.WithContext(ctx).Model(&models.TranscriptionJob{}).
		Where("id = ? AND status != ?", id, models.StatusProcessing).Update("status", "deleting")
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected != 1 {
		return ErrJobConflict
	}
	return nil
}

// Purge removes sensitive child data and the job in a single transaction. It is
// used only after a deletion intent or expiry of an explicitly temporary job.
func (r *jobRepository) Purge(ctx context.Context, id string) error { return r.purge(ctx, id, false) }

// CompleteDeletion preserves an empty tombstone for clients' delta sync.
func (r *jobRepository) CompleteDeletion(ctx context.Context, id string) error {
	return r.purge(ctx, id, true)
}

func (r *jobRepository) purge(ctx context.Context, id string, tombstone bool) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		sessions := tx.Unscoped().Model(&models.ChatSession{}).Select("id").Where("transcription_id = ?", id)
		if err := tx.Unscoped().Where("chat_session_id IN (?)", sessions).Delete(&models.ChatMessage{}).Error; err != nil {
			return err
		}
		for _, item := range []struct {
			model  any
			column string
		}{
			{&models.ChatSession{}, "transcription_id"}, {&models.Note{}, "transcription_id"},
			{&models.Summary{}, "transcription_id"}, {&models.SpeakerMapping{}, "transcription_job_id"},
			{&models.TranscriptionJobExecution{}, "transcription_job_id"}, {&models.MultiTrackFile{}, "transcription_job_id"},
		} {
			if err := tx.Unscoped().Where(item.column+" = ?", id).Delete(item.model).Error; err != nil {
				return err
			}
		}
		if tombstone {
			empty := models.TranscriptionJob{ID: id, Status: "deleted", DeletedAt: gorm.DeletedAt{Time: time.Now(), Valid: true}}
			return tx.Unscoped().Model(&models.TranscriptionJob{}).Where("id = ?", id).Select("*").Omit("id", "created_at").Updates(&empty).Error
		}
		return tx.Unscoped().Delete(&models.TranscriptionJob{}, "id = ?", id).Error
	})
}

// ExpiredTemporaryJobs also includes legacy soft-deleted quick rows whose source
// file disappeared before their actual output directory was cleaned.
func (r *jobRepository) ExpiredTemporaryJobs(ctx context.Context, directory string, before time.Time) ([]models.TranscriptionJob, error) {
	prefix := filepath.Clean(directory) + string(filepath.Separator)
	var jobs []models.TranscriptionJob
	err := r.db.WithContext(ctx).Unscoped().Where("substr(audio_path,1,?) = ? AND created_at < ?", len(prefix), prefix, before).Find(&jobs).Error
	return jobs, err
}
