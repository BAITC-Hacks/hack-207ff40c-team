package queue

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"scriberr/internal/models"
	"scriberr/internal/repository"
	"scriberr/pkg/logger"
)

// RunningJob tracks both context cancellation and OS process
type RunningJob struct {
	Cancel  context.CancelFunc
	Process *exec.Cmd
}

// TaskQueue manages transcription job processing
type TaskQueue struct {
	minWorkers     int
	maxWorkers     int
	currentWorkers int64 // Use atomic for thread-safe access
	jobChannel     chan string
	ctx            context.Context
	cancel         context.CancelFunc
	wg             sync.WaitGroup
	processor      JobProcessor
	runningJobs    map[string]*RunningJob
	jobsMutex      sync.RWMutex
	autoScale      bool
	lastScaleTime  time.Time
	jobRepo        repository.JobRepository
	admissionMutex sync.Mutex
}

// JobProcessor defines the interface for processing jobs
type JobProcessor interface {
	ProcessJob(ctx context.Context, jobID string) error
	ProcessJobWithProcess(ctx context.Context, jobID string, registerProcess func(*exec.Cmd)) error
}

// MultiTrackJobProcessor extends JobProcessor with multi-track specific methods
type MultiTrackJobProcessor interface {
	JobProcessor
	TerminateMultiTrackJob(jobID string) error
	IsMultiTrackJob(jobID string) bool
}

// getOptimalWorkerCount calculates optimal worker count based on system resources
func getOptimalWorkerCount() (min, max int) {
	numCPU := runtime.NumCPU()

	// Check for environment variable override
	if workerStr := os.Getenv("QUEUE_WORKERS"); workerStr != "" {
		if workers, err := strconv.Atoi(workerStr); err == nil && workers > 0 {
			return workers, workers // Fixed worker count
		}
	}

	// For transcription workloads, we typically want fewer workers than CPUs
	// since each job is CPU and I/O intensive
	if numCPU <= 2 {
		return 1, 2
	}
	if numCPU <= 4 {
		return 1, 3
	}
	if numCPU <= 8 {
		return 2, 4
	}
	return 2, 6 // Cap at 6 for very high CPU systems
}

// NewTaskQueue creates a new task queue with auto-scaling capabilities
func NewTaskQueue(legacyWorkers int, processor JobProcessor, jobRepo repository.JobRepository) *TaskQueue {
	ctx, cancel := context.WithCancel(context.Background())

	// Calculate optimal worker counts, fallback to legacy parameter
	min, max := getOptimalWorkerCount()
	// Only use legacy parameter as fallback when QUEUE_WORKERS env var is not set
	// TODO: Deprecate `legacyWorkers` and rely on `getOptimalWorkerCount` instead.
	if os.Getenv("QUEUE_WORKERS") == "" && legacyWorkers > 0 {
		min = legacyWorkers
		max = legacyWorkers
	}

	// Check if auto-scaling should be enabled
	autoScale := os.Getenv("QUEUE_AUTO_SCALE") != "false"
	if min == max {
		autoScale = false // Disable auto-scaling if min == max
	}

	return &TaskQueue{
		minWorkers:     min,
		maxWorkers:     max,
		currentWorkers: int64(min),
		jobChannel:     make(chan string, 200), // Increased buffer for better throughput
		ctx:            ctx,
		cancel:         cancel,
		processor:      processor,
		runningJobs:    make(map[string]*RunningJob),
		autoScale:      autoScale,
		lastScaleTime:  time.Now(),
		jobRepo:        jobRepo,
	}
}

// Start starts the task queue workers
func (tq *TaskQueue) Start() {
	workers := int(atomic.LoadInt64(&tq.currentWorkers))
	logger.Debug("Starting task queue",
		"workers", workers,
		"min_workers", tq.minWorkers,
		"max_workers", tq.maxWorkers,
		"auto_scale", tq.autoScale)

	// Reset any zombie jobs from previous runs synchronously before starting workers
	tq.ResetZombieJobs()

	// Start initial workers
	for i := 0; i < workers; i++ {
		tq.wg.Add(1)
		go tq.worker(i)
	}

	// Recovery is a bounded producer alongside consumers, so backlogs larger
	// than the channel remain recoverable instead of being silently dropped.
	tq.wg.Add(1)
	go func() { defer tq.wg.Done(); tq.recoverPendingJobs() }()

	// Start auto-scaling monitor if enabled
	if tq.autoScale {
		tq.wg.Add(1)
		go tq.autoScaler()
	}
}

// Stop stops the task queue
func (tq *TaskQueue) Stop() {
	logger.Debug("Stopping task queue")
	logger.Debug("Stopping task queue")
	tq.cancel()
	// Do not close jobChannel here as it causes panics in EnqueueJob
	// The channel will be garbage collected when the queue is no longer referenced
	tq.wg.Wait()
	logger.Debug("Task queue stopped")
}

// EnqueueJob adds a job to the queue
func (tq *TaskQueue) EnqueueJob(jobID string) error {
	return tq.EnqueuePreparedJob(jobID, nil)
}

// EnqueuePreparedJob reserves local channel capacity before committing a durable
// database transition. All producers use admissionMutex, so a full queue never
// changes the previous result or leaves a newly stranded pending job.
func (tq *TaskQueue) EnqueuePreparedJob(jobID string, prepare func() error) error {
	tq.admissionMutex.Lock()
	defer tq.admissionMutex.Unlock()
	if tq.ctx.Err() != nil {
		return fmt.Errorf("queue is shutting down")
	}
	if len(tq.jobChannel) == cap(tq.jobChannel) {
		return fmt.Errorf("queue is full")
	}
	// Keep admission and ownership checks atomic with worker claim/finalization.
	// A canceled processor may still be closing files or waiting for its child.
	tq.jobsMutex.RLock()
	defer tq.jobsMutex.RUnlock()
	if _, running := tq.runningJobs[jobID]; running {
		return repository.ErrJobConflict
	}
	if prepare != nil {
		if err := prepare(); err != nil {
			return err
		}
	}
	// Capacity is reserved. Even when shutdown races this send, the durable
	// pending row is retained for startup recovery.
	tq.jobChannel <- jobID
	return nil
}

// BeginJobDeletion records durable deletion intent only when no processor owns
// the job. The same lock covers claim and admission, so neither can start between
// the ownership check and the database transition that makes future claims fail.
func (tq *TaskQueue) BeginJobDeletion(jobID string, begin func() error) error {
	tq.jobsMutex.Lock()
	defer tq.jobsMutex.Unlock()
	if _, running := tq.runningJobs[jobID]; running {
		return repository.ErrJobConflict
	}
	return begin()
}

// worker processes jobs from the channel
func (tq *TaskQueue) worker(id int) {
	defer tq.wg.Done()

	logger.Debug("Worker started", "worker_id", id)

	for {
		select {
		case jobID, ok := <-tq.jobChannel:
			if !ok {
				logger.Debug("Worker stopped", "worker_id", id)
				return
			}

			logger.WorkerOperation(id, jobID, "start")

			// A DB claim and its in-memory ownership are one transition to
			// KillJob, which must not mistake the claim window for a zombie.
			tq.jobsMutex.Lock()
			if _, running := tq.runningJobs[jobID]; running {
				tq.jobsMutex.Unlock()
				continue
			}
			if claimer, ok := tq.jobRepo.(interface {
				Claim(context.Context, string) (bool, error)
			}); ok {
				claimed, err := claimer.Claim(tq.ctx, jobID)
				if err != nil || !claimed {
					tq.jobsMutex.Unlock()
					continue
				}
			} else if err := tq.updateJobStatus(jobID, models.StatusProcessing); err != nil {
				tq.jobsMutex.Unlock()
				continue
			}

			jobCtx, jobCancel := context.WithCancel(tq.ctx)
			runningJob := &RunningJob{
				Cancel:  jobCancel,
				Process: nil, // Will be set by registerProcess callback
			}
			tq.runningJobs[jobID] = runningJob
			tq.jobsMutex.Unlock()

			// Register process callback
			registerProcess := func(cmd *exec.Cmd) {
				tq.jobsMutex.Lock()
				if job := tq.runningJobs[jobID]; job == runningJob {
					job.Process = cmd
				}
				tq.jobsMutex.Unlock()
			}

			// Process the job with process registration
			err := tq.processor.ProcessJobWithProcess(jobCtx, jobID, registerProcess)

			// Keep ownership until all final writes finish. Neither a retry nor
			// zombie cancellation may race these writes into a new execution.
			tq.jobsMutex.Lock()
			if err == nil && jobCtx.Err() != nil {
				err = jobCtx.Err()
			}
			if err != nil {
				if jobCtx.Err() == context.Canceled {
					logger.Info("Job cancelled", "worker_id", id, "job_id", jobID)
					if err := tq.updateJobStatus(jobID, models.StatusFailed); err != nil {
						logger.Error("Failed to update job status", "job_id", jobID, "error", err)
					}
					if err := tq.updateJobError(jobID, "Job was cancelled by user"); err != nil {
						logger.Error("Failed to update job error", "job_id", jobID, "error", err)
					}
				} else {
					logger.Error("Job processing failed", "worker_id", id, "job_id", jobID, "error", err)
					if err := tq.updateJobStatus(jobID, models.StatusFailed); err != nil {
						logger.Error("Failed to update job status", "job_id", jobID, "error", err)
					}
					if err := tq.updateJobError(jobID, err.Error()); err != nil {
						logger.Error("Failed to update job error", "job_id", jobID, "error", err)
					}
				}
			} else {
				logger.Debug("Job processed successfully", "worker_id", id, "job_id", jobID)
				if err := tq.updateJobStatus(jobID, models.StatusCompleted); err != nil {
					logger.Error("Failed to update job status", "job_id", jobID, "error", err)
				}
			}

			delete(tq.runningJobs, jobID)
			jobCancel() // release the parent context's completed child
			tq.jobsMutex.Unlock()

		case <-tq.ctx.Done():
			logger.Debug("Worker stopped", "worker_id", id, "reason", "context_cancelled")
			return
		}
	}
}

// KillJob aggressively terminates a running job
func (tq *TaskQueue) KillJob(jobID string) error {
	tq.jobsMutex.Lock()
	defer tq.jobsMutex.Unlock()

	runningJob, exists := tq.runningJobs[jobID]
	if !exists {
		// A processing row may belong to direct/quick inference or another
		// queue. Only startup recovery may classify an interrupted execution;
		// cancellation must not publish failed for a processor it cannot stop.
		return fmt.Errorf("job %s is not currently running in this queue", jobID)
	}

	logger.Info("Killing job", "job_id", jobID)

	// Cancellation propagates to individual tracks through the parent context.
	// Let their processor clean up after exit; eager multi-track termination
	// deletes live child records and exposes failed while inference still runs.

	// First, try to kill the OS process group (or process on non-Unix)
	if runningJob.Process != nil && runningJob.Process.Process != nil {
		logger.Debug("Terminating process tree", "pid", runningJob.Process.Process.Pid, "job_id", jobID)
		if err := killProcessTree(runningJob.Process.Process); err != nil {
			log.Printf("Failed to terminate process tree for job %s: %v, trying direct kill()", jobID, err)
			_ = runningJob.Process.Process.Kill()
		}
	}

	// Also cancel the context for cleanup
	runningJob.Cancel()

	// The worker records failed only after the processor exits. Exposing a
	// retryable state here would let a second execution race its cleanup.

	return nil
}

// IsJobRunning checks if a job is currently being processed
func (tq *TaskQueue) IsJobRunning(jobID string) bool {
	tq.jobsMutex.RLock()
	defer tq.jobsMutex.RUnlock()

	_, exists := tq.runningJobs[jobID]
	return exists
}

// updateJobStatus updates the status of a job
func (tq *TaskQueue) updateJobStatus(jobID string, status models.JobStatus) error {
	return tq.jobRepo.UpdateStatus(context.Background(), jobID, status)
}

// updateJobError updates the error message of a job
func (tq *TaskQueue) updateJobError(jobID string, errorMsg string) error {
	return tq.jobRepo.UpdateError(context.Background(), jobID, errorMsg)
}

// GetJobStatus gets the status of a job
func (tq *TaskQueue) GetJobStatus(jobID string) (*models.TranscriptionJob, error) {
	return tq.jobRepo.FindByID(context.Background(), jobID)
}

// autoScaler monitors queue load and adjusts worker count
func (tq *TaskQueue) autoScaler() {
	defer tq.wg.Done()

	ticker := time.NewTicker(30 * time.Second) // Check every 30 seconds
	defer ticker.Stop()

	log.Println("Auto-scaler started")

	for {
		select {
		case <-ticker.C:
			tq.checkAndScale()
		case <-tq.ctx.Done():
			log.Println("Auto-scaler stopped")
			return
		}
	}
}

// checkAndScale evaluates current load and adjusts worker count
func (tq *TaskQueue) checkAndScale() {
	// Prevent too frequent scaling
	if time.Since(tq.lastScaleTime) < 1*time.Minute {
		return
	}

	queueSize := len(tq.jobChannel)
	currentWorkers := int(atomic.LoadInt64(&tq.currentWorkers))

	tq.jobsMutex.RLock()
	runningJobsCount := len(tq.runningJobs)
	tq.jobsMutex.RUnlock()

	// Scale up if queue is building up and we have capacity
	if queueSize > 10 && currentWorkers < tq.maxWorkers {
		newWorkerCount := currentWorkers + 1
		log.Printf("Scaling up workers: %d -> %d (queue size: %d)", currentWorkers, newWorkerCount, queueSize)

		atomic.StoreInt64(&tq.currentWorkers, int64(newWorkerCount))
		tq.wg.Add(1)
		go tq.worker(newWorkerCount - 1)
		tq.lastScaleTime = time.Now()

		// Scale down if queue is empty and minimal jobs running
	} else if queueSize == 0 && runningJobsCount <= 1 && currentWorkers > tq.minWorkers {
		newWorkerCount := currentWorkers - 1
		log.Printf("Scaling down workers: %d -> %d (queue size: %d, running: %d)",
			currentWorkers, newWorkerCount, queueSize, runningJobsCount)

		atomic.StoreInt64(&tq.currentWorkers, int64(newWorkerCount))
		tq.lastScaleTime = time.Now()

		// Note: We don't actively stop workers here. They will naturally exit
		// when no more jobs are available and the queue empties.
	}
}

// GetQueueStats returns queue statistics
func (tq *TaskQueue) GetQueueStats() map[string]interface{} {
	ctx := context.Background()
	pendingCount, _ := tq.jobRepo.CountByStatus(ctx, models.StatusPending)
	processingCount, _ := tq.jobRepo.CountByStatus(ctx, models.StatusProcessing)
	completedCount, _ := tq.jobRepo.CountByStatus(ctx, models.StatusCompleted)
	failedCount, _ := tq.jobRepo.CountByStatus(ctx, models.StatusFailed)

	tq.jobsMutex.RLock()
	runningJobsCount := len(tq.runningJobs)
	tq.jobsMutex.RUnlock()

	return map[string]interface{}{
		"queue_size":      len(tq.jobChannel),
		"queue_capacity":  cap(tq.jobChannel),
		"current_workers": int(atomic.LoadInt64(&tq.currentWorkers)),
		"min_workers":     tq.minWorkers,
		"max_workers":     tq.maxWorkers,
		"auto_scale":      tq.autoScale,
		"running_jobs":    runningJobsCount,
		"pending_jobs":    pendingCount,
		"processing_jobs": processingCount,
		"completed_jobs":  completedCount,
		"failed_jobs":     failedCount,
	}
}

// ResetZombieJobs finds jobs stuck in processing state from previous runs and marks them as failed
func (tq *TaskQueue) ResetZombieJobs() {
	// Find all jobs with status "processing"
	zombieJobs, err := tq.jobRepo.FindByStatus(context.Background(), models.StatusProcessing)
	if err != nil {
		logger.Error("Failed to scan for zombie jobs", "error", err)
		return
	}

	if len(zombieJobs) == 0 {
		return
	}

	logger.Info("Found zombie jobs from previous run", "count", len(zombieJobs))

	for _, job := range zombieJobs {
		logger.Info("Resetting zombie job", "job_id", job.ID)

		// Mark as failed
		if err := tq.updateJobStatus(job.ID, models.StatusFailed); err != nil {
			logger.Error("Failed to update zombie job status", "job_id", job.ID, "error", err)
			continue
		}

		// Update error message
		if err := tq.updateJobError(job.ID, "Job interrupted by server restart"); err != nil {
			logger.Error("Failed to update zombie job error message", "job_id", job.ID, "error", err)
		}
	}
}

// recoverPendingJobs enqueues pending jobs from previous server runs
// This runs ONCE at startup, not repeatedly like the old scanner
func (tq *TaskQueue) recoverPendingJobs() {
	pendingJobs, err := tq.jobRepo.FindByStatus(context.Background(), models.StatusPending)
	if err != nil {
		logger.Error("Failed to scan for pending jobs during startup recovery", "error", err)
		return
	}

	if len(pendingJobs) == 0 {
		return
	}

	logger.Info("Recovering pending jobs from previous server run", "count", len(pendingJobs))

	for _, job := range pendingJobs {
		for {
			if err := tq.EnqueueJob(job.ID); err == nil || errors.Is(err, repository.ErrJobConflict) {
				// A job claimed after the recovery snapshot is already owned.
				break
			}
			select {
			case <-tq.ctx.Done():
				return
			case <-time.After(10 * time.Millisecond):
			}
		}
	}
}
