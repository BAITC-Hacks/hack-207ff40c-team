package repository

import (
	"context"

	"scriberr/internal/models"
)

// FindByIDIncludingDeleted lets an idempotent producer recognize an accepted
// handoff even after deliberate deletion. Normal API lookups remain scoped.
func (r *jobRepository) FindByIDIncludingDeleted(ctx context.Context, id string) (*models.TranscriptionJob, error) {
	var job models.TranscriptionJob
	if err := r.db.WithContext(ctx).Unscoped().First(&job, "id = ?", id).Error; err != nil {
		return nil, err
	}
	return &job, nil
}
