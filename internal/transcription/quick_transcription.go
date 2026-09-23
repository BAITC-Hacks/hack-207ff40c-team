package transcription

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	"scriberr/internal/config"
	"scriberr/internal/models"
	"scriberr/internal/repository"
)

var ErrQuickQueueFull = errors.New("quick transcription queue is full")

// QuickTranscriptionJob is persisted privately until its six-hour expiry.
type QuickTranscriptionJob struct {
	ID           string                `json:"id"`
	Status       models.JobStatus      `json:"status"`
	AudioPath    string                `json:"audio_path"`
	Transcript   *string               `json:"transcript,omitempty"`
	Parameters   models.WhisperXParams `json:"parameters"`
	CreatedAt    time.Time             `json:"created_at"`
	ExpiresAt    time.Time             `json:"expires_at"`
	ErrorMessage *string               `json:"error_message,omitempty"`
}

type quickJobProcessor interface {
	ProcessJob(context.Context, string) error
}

type QuickTranscriptionService struct {
	config           *config.Config
	unifiedProcessor quickJobProcessor
	jobRepo          repository.JobRepository
	jobs             map[string]*QuickTranscriptionJob
	jobsMutex        sync.RWMutex
	tempDir          string
	ctx              context.Context
	cancel           context.CancelFunc
	work             chan string
	slots            chan struct{}
	wg               sync.WaitGroup
	closeOnce        sync.Once
}

func NewQuickTranscriptionService(cfg *config.Config, processor quickJobProcessor, repo repository.JobRepository) (*QuickTranscriptionService, error) {
	dir := filepath.Join(cfg.UploadDir, "quick_transcriptions")
	if err := os.MkdirAll(dir, 0700); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithCancel(context.Background())
	qs := &QuickTranscriptionService{config: cfg, unifiedProcessor: processor, jobRepo: repo, jobs: map[string]*QuickTranscriptionJob{}, tempDir: dir, ctx: ctx, cancel: cancel, work: make(chan string, 16), slots: make(chan struct{}, 16)}
	if err := qs.restore(); err != nil {
		cancel()
		return nil, err
	}
	qs.wg.Add(1)
	go qs.run()
	return qs, nil
}

// snapshot copies all nested pointer fields while the caller holds the lock.
func quickSnapshot(job *QuickTranscriptionJob) *QuickTranscriptionJob {
	raw, _ := json.Marshal(job)
	var copy QuickTranscriptionJob
	_ = json.Unmarshal(raw, &copy)
	return &copy
}

func (qs *QuickTranscriptionService) persist(job *QuickTranscriptionJob) error {
	data, err := json.Marshal(job)
	if err != nil {
		return err
	}
	file, err := os.CreateTemp(qs.tempDir, ".manifest-")
	if err != nil {
		return err
	}
	name := file.Name()
	defer os.Remove(name)
	if _, err = file.Write(data); err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	if err = os.Rename(name, filepath.Join(qs.tempDir, job.ID+".job.json")); err != nil {
		return err
	}
	dir, err := os.Open(qs.tempDir)
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}

func (qs *QuickTranscriptionService) SubmitQuickJob(audio io.Reader, filename string, params models.WhisperXParams) (*QuickTranscriptionJob, error) {
	if qs.ctx.Err() != nil {
		return nil, fmt.Errorf("quick transcription is stopping")
	}
	select {
	case qs.slots <- struct{}{}:
	default:
		return nil, ErrQuickQueueFull
	}
	admitted := false
	defer func() {
		if !admitted {
			<-qs.slots
		}
	}()
	id := uuid.NewString()
	path := filepath.Join(qs.tempDir, id+filepath.Ext(filepath.Base(filename)))
	file, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return nil, err
	}
	// Bound upload storage as well as goroutines and model concurrency.
	n, err := io.Copy(file, io.LimitReader(audio, (512<<20)+1))
	if err == nil && n > 512<<20 {
		err = fmt.Errorf("recording exceeds 512 MiB")
	}
	if err == nil {
		err = file.Sync()
	}
	closeErr := file.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil {
		_ = os.Remove(path)
		return nil, err
	}
	now := time.Now()
	job := &QuickTranscriptionJob{ID: id, Status: models.StatusPending, AudioPath: path, Parameters: params, CreatedAt: now, ExpiresAt: now.Add(6 * time.Hour)}
	job = quickSnapshot(job)
	if err := qs.persist(job); err != nil {
		_ = os.Remove(path)
		return nil, err
	}
	qs.jobsMutex.Lock()
	qs.jobs[id] = job
	response := quickSnapshot(job)
	qs.jobsMutex.Unlock()
	select {
	case qs.work <- id:
		admitted = true
		return response, nil
	case <-qs.ctx.Done():
		qs.jobsMutex.Lock()
		delete(qs.jobs, id)
		qs.jobsMutex.Unlock()
		_ = qs.cleanupJob(job)
		return nil, fmt.Errorf("quick transcription is stopping")
	}
}

func (qs *QuickTranscriptionService) GetQuickJob(id string) (*QuickTranscriptionJob, error) {
	qs.jobsMutex.RLock()
	defer qs.jobsMutex.RUnlock()
	job, ok := qs.jobs[id]
	if !ok {
		return nil, fmt.Errorf("job not found")
	}
	if time.Now().After(job.ExpiresAt) {
		return nil, fmt.Errorf("job expired")
	}
	return quickSnapshot(job), nil
}

func (qs *QuickTranscriptionService) run() {
	defer qs.wg.Done()
	ticker := time.NewTicker(time.Minute)
	defer ticker.Stop()
	for {
		select {
		case <-qs.ctx.Done():
			return
		case id := <-qs.work:
			qs.processQuickJob(id)
			<-qs.slots
		case <-ticker.C:
			qs.cleanupExpiredJobs()
			if err := qs.cleanupLegacyOrphans(); err != nil {
				log.Printf("quick retention cleanup failed: %v", err)
			}
		}
	}
}

func (qs *QuickTranscriptionService) processQuickJob(id string) {
	qs.jobsMutex.Lock()
	job := qs.jobs[id]
	if job == nil {
		qs.jobsMutex.Unlock()
		return
	}
	job.Status = models.StatusProcessing
	copy := quickSnapshot(job)
	qs.jobsMutex.Unlock()
	ctx, cancel := context.WithTimeout(qs.ctx, 30*time.Minute)
	defer cancel()
	err := qs.persist(copy)
	var transcript *string
	if err == nil {
		temp := &models.TranscriptionJob{ID: id, AudioPath: copy.AudioPath, Parameters: copy.Parameters, Status: models.StatusProcessing}
		err = qs.jobRepo.Create(ctx, temp)
		if err == nil {
			err = qs.unifiedProcessor.ProcessJob(ctx, id)
		}
		if err == nil {
			var processed *models.TranscriptionJob
			processed, err = qs.jobRepo.FindByID(ctx, id)
			if err == nil {
				if processed.Transcript == nil || *processed.Transcript == "" {
					err = fmt.Errorf("processing returned no transcript")
				} else {
					value := *processed.Transcript
					transcript = &value
				}
			}
		}
	}
	qs.jobsMutex.Lock()
	defer qs.jobsMutex.Unlock()
	job = qs.jobs[id]
	if job == nil {
		return
	}
	result := quickSnapshot(job)
	if err != nil {
		result.Status = models.StatusFailed
		msg := err.Error()
		result.ErrorMessage = &msg
	} else {
		result.Status = models.StatusCompleted
		result.Transcript = transcript
	}
	// Publish completion only after its result is durable. Keep the database
	// transcript for recovery when writing the result manifest fails.
	if saveErr := qs.persist(result); saveErr != nil {
		result.Status = models.StatusFailed
		result.Transcript = nil
		msg := fmt.Sprintf("cannot save quick result: %v", saveErr)
		result.ErrorMessage = &msg
	}
	qs.jobs[id] = result
	if result.Status == models.StatusCompleted {
		// Result is already in the durable private manifest. Remove its
		// temporary processing row instead of leaving a ghost archive job.
		if purger, ok := qs.jobRepo.(interface {
			Purge(context.Context, string) error
		}); ok {
			purgeCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			if err := purger.Purge(purgeCtx, id); err != nil {
				// Do not misrepresent a finished temporary job as processing
				// while durable retention cleanup retries its removal.
				_ = qs.jobRepo.UpdateStatus(purgeCtx, id, models.StatusCompleted)
				log.Printf("quick temporary record cleanup pending for %s: %v", id, err)
			}
			cancel()
		}
	}
}

func (qs *QuickTranscriptionService) restore() error {
	entries, err := os.ReadDir(qs.tempDir)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".job.json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(qs.tempDir, entry.Name()))
		if err != nil {
			return err
		}
		var job QuickTranscriptionJob
		if err := json.Unmarshal(data, &job); err != nil {
			return fmt.Errorf("invalid quick retention record %s: %w", entry.Name(), err)
		}
		if _, err := uuid.Parse(job.ID); err != nil || entry.Name() != job.ID+".job.json" {
			return fmt.Errorf("invalid quick retention identity")
		}
		// Derive ownership from the private directory, not arbitrary manifest paths.
		expected := filepath.Join(qs.tempDir, filepath.Base(job.AudioPath))
		if filepath.Clean(job.AudioPath) != filepath.Clean(expected) || (filepath.Base(expected) != job.ID && !strings.HasPrefix(filepath.Base(expected), job.ID+".")) {
			return fmt.Errorf("invalid quick source path")
		}
		if job.Status == models.StatusPending || job.Status == models.StatusProcessing {
			job.Status = models.StatusFailed
			message := "processing interrupted by server restart; resubmit the recording"
			job.ErrorMessage = &message
			if err := qs.persist(&job); err != nil {
				return err
			}
		}
		qs.jobs[job.ID] = &job
	}
	qs.cleanupExpiredJobs()
	return qs.cleanupLegacyOrphans()
}

func (qs *QuickTranscriptionService) cleanupLegacyOrphans() error {
	entries, err := os.ReadDir(qs.tempDir)
	if err != nil {
		return err
	}
	qs.jobsMutex.Lock()
	defer qs.jobsMutex.Unlock()
	// Scan periodically as well as at startup: files younger than six hours
	// at startup still expire without needing another process restart.
	// Pre-manifest releases left files and soft-deleted rows behind. Reconcile
	// only UUID-named artifacts owned by this quick-upload directory after 6h.
	for _, entry := range entries {
		name := entry.Name()
		if entry.IsDir() || strings.HasSuffix(name, ".job.json") {
			continue
		}
		if len(name) < 36 {
			continue
		}
		id := name[:36]
		if _, err := uuid.Parse(id); err != nil {
			continue
		}
		if _, ok := qs.jobs[id]; ok {
			continue
		}
		info, err := entry.Info()
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		if time.Since(info.ModTime()) < 6*time.Hour {
			continue
		}
		orphan := &QuickTranscriptionJob{ID: id, AudioPath: filepath.Join(qs.tempDir, name)}
		if err := qs.cleanupJob(orphan); err != nil {
			return err
		}
	}
	if scanner, ok := qs.jobRepo.(interface {
		ExpiredTemporaryJobs(context.Context, string, time.Time) ([]models.TranscriptionJob, error)
	}); ok {
		ctx, cancel := context.WithTimeout(qs.ctx, 10*time.Second)
		defer cancel()
		rows, err := scanner.ExpiredTemporaryJobs(ctx, qs.tempDir, time.Now().Add(-6*time.Hour))
		if err != nil {
			return err
		}
		for _, row := range rows {
			if _, err := uuid.Parse(row.ID); err != nil {
				continue
			}
			if _, active := qs.jobs[row.ID]; active {
				continue
			}
			if err := qs.cleanupJob(&QuickTranscriptionJob{ID: row.ID, AudioPath: row.AudioPath}); err != nil {
				return err
			}
		}
	}

	return nil
}

func (qs *QuickTranscriptionService) cleanupJob(job *QuickTranscriptionJob) error {
	for _, path := range []string{job.AudioPath, filepath.Join(qs.tempDir, job.ID+"_transcript.json")} {
		if err := os.Remove(path); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
	}
	for _, dir := range []string{qs.config.TranscriptsDir, qs.config.TempDir} {
		if dir != "" {
			if err := os.RemoveAll(filepath.Join(dir, job.ID)); err != nil {
				return err
			}
		}
	}
	if err := os.RemoveAll(filepath.Join(qs.tempDir, job.ID+"_output")); err != nil {
		return err
	}
	purger, ok := qs.jobRepo.(interface {
		Purge(context.Context, string) error
	})
	if !ok {
		return fmt.Errorf("temporary record purge unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := purger.Purge(ctx, job.ID); err != nil {
		return err
	}
	if err := os.Remove(filepath.Join(qs.tempDir, job.ID+".job.json")); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}

func (qs *QuickTranscriptionService) cleanupExpiredJobs() {
	qs.jobsMutex.Lock()
	defer qs.jobsMutex.Unlock()
	for id, job := range qs.jobs {
		if time.Now().After(job.ExpiresAt) && job.Status != models.StatusProcessing {
			if err := qs.cleanupJob(job); err == nil {
				delete(qs.jobs, id)
			}
		}
	}
}

func (qs *QuickTranscriptionService) Close() { qs.closeOnce.Do(qs.cancel); qs.wg.Wait() }
