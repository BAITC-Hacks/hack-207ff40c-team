package dropzone

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"

	"fmt"
	"gorm.io/gorm"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"

	"scriberr/internal/config"
	"scriberr/internal/models"
	"scriberr/internal/repository"

	"github.com/fsnotify/fsnotify"
	"github.com/google/uuid"
)

// TaskQueue interface for enqueueing transcription jobs
type TaskQueue interface {
	EnqueuePreparedJob(jobID string, prepare func() error) error
}

// Service manages the dropzone file monitoring
type Service struct {
	config       *config.Config
	watcher      *fsnotify.Watcher
	dropzonePath string
	taskQueue    TaskQueue
	jobRepo      repository.JobRepository
	userRepo     repository.UserRepository
}

// NewService creates a new dropzone service
func NewService(cfg *config.Config, taskQueue TaskQueue, jobRepo repository.JobRepository, userRepo repository.UserRepository) *Service {
	return &Service{
		config:       cfg,
		taskQueue:    taskQueue,
		dropzonePath: filepath.Join("data", "dropzone"),
		jobRepo:      jobRepo,
		userRepo:     userRepo,
	}
}

// Start initializes the dropzone directory and starts file monitoring
func (s *Service) Start() error {
	log.Printf("Starting dropzone service...")

	// Create dropzone directory if it doesn't exist
	if err := os.MkdirAll(s.dropzonePath, 0755); err != nil {
		return fmt.Errorf("failed to create dropzone directory: %v", err)
	}

	log.Printf("Dropzone directory created/verified at: %s", s.dropzonePath)

	// Initialize file watcher
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return fmt.Errorf("failed to create file watcher: %v", err)
	}
	s.watcher = watcher

	// Add dropzone directory and all subdirectories to watcher recursively
	if err := s.addDirectoryRecursively(s.dropzonePath); err != nil {
		s.watcher.Close()
		return fmt.Errorf("failed to add directories to watcher: %v", err)
	}

	// Process existing files recursively on startup
	if err := s.processExistingFiles(); err != nil {
		log.Printf("Warning: failed to process some existing files: %v", err)
	}

	// Start monitoring in a goroutine
	go s.watchFiles()

	log.Printf("Dropzone service started, monitoring recursively: %s", s.dropzonePath)
	return nil
}

// Stop stops the dropzone service
func (s *Service) Stop() error {
	if s.watcher != nil {
		log.Printf("Stopping dropzone service...")
		return s.watcher.Close()
	}
	return nil
}

// addDirectoryRecursively adds a directory and all its subdirectories to the watcher
func (s *Service) addDirectoryRecursively(root string) error {
	return filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			log.Printf("Warning: error accessing path %s: %v", path, err)
			return nil // Continue walking despite errors
		}

		// Only add directories to the watcher
		if info.IsDir() {
			if err := s.watcher.Add(path); err != nil {
				log.Printf("Warning: failed to watch directory %s: %v", path, err)
				return nil // Continue despite individual directory failures
			}
			log.Printf("Added directory to watcher: %s", path)
		}

		return nil
	})
}

// processExistingFiles processes all existing audio files in the dropzone on startup
func (s *Service) processExistingFiles() error {
	return filepath.Walk(s.dropzonePath, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			log.Printf("Warning: error accessing path %s: %v", path, err)
			return nil // Continue walking despite errors
		}

		// Only process files, not directories
		if !info.IsDir() {
			filename := filepath.Base(path)
			if strings.HasSuffix(filename, ".ready") {
				log.Printf("Processing existing audio file: %s", path)
				s.processFile(path)
			}
		}

		return nil
	})
}

// watchFiles monitors the dropzone directory for new files
func (s *Service) watchFiles() {
	for {
		select {
		case event, ok := <-s.watcher.Events:
			if !ok {
				return
			}

			// Handle creation events for both files and directories
			if event.Op&(fsnotify.Create|fsnotify.Write) != 0 {
				// Check if the created item is a directory
				if info, err := os.Stat(event.Name); err == nil && info.IsDir() {
					log.Printf("Detected new directory in dropzone: %s", event.Name)
					// Add the new directory to the watcher recursively
					if err := s.addDirectoryRecursively(event.Name); err != nil {
						log.Printf("Failed to watch new directory %s: %v", event.Name, err)
					}
				} else {
					log.Printf("Detected new file in dropzone: %s", event.Name)
					s.processFile(event.Name)
				}
			}

		case err, ok := <-s.watcher.Errors:
			if !ok {
				return
			}
			log.Printf("Dropzone watcher error: %v", err)
		}
	}
}

// isAudioFile checks if the file is a valid audio file based on extension
func (s *Service) isAudioFile(filename string) bool {
	ext := strings.ToLower(filepath.Ext(filename))
	audioExtensions := []string{
		".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg",
		".wma", ".mp4", ".avi", ".mov", ".mkv", ".webm",
	}

	for _, validExt := range audioExtensions {
		if ext == validExt {
			return true
		}
	}
	return false
}

// processFile handles a newly detected file in the dropzone
// ReadyManifest is written atomically by the producer after closing the audio.
// Keeping the producer-owned source prevents late writers from losing their data.
type ReadyManifest struct {
	Bytes     int64  `json:"bytes"`
	SHA256    string `json:"sha256"`
	HandoffID string `json:"handoff_id,omitempty"`
}

func readReady(path string) (ReadyManifest, error) {
	var ready ReadyManifest
	source, err := os.Open(path)
	if err != nil {
		return ready, err
	}
	defer source.Close()
	data, err := io.ReadAll(io.LimitReader(source, 4097))
	if err != nil || len(data) > 4096 {
		return ready, fmt.Errorf("invalid readiness marker")
	}
	if err := json.Unmarshal(data, &ready); err != nil {
		return ready, err
	}
	digest, err := hex.DecodeString(ready.SHA256)
	if err != nil || len(digest) != sha256.Size || ready.Bytes < 1 {
		return ready, fmt.Errorf("readiness marker needs positive bytes and SHA256")
	}
	ready.SHA256 = strings.ToLower(ready.SHA256)
	if ready.HandoffID != "" {
		id, err := uuid.Parse(ready.HandoffID)
		if err != nil || id == uuid.Nil || !strings.EqualFold(id.String(), ready.HandoffID) {
			return ready, fmt.Errorf("handoff_id must be a nonzero UUID in canonical form")
		}
		ready.HandoffID = id.String()
	}
	return ready, nil
}

func (s *Service) processFile(filePath string) {
	filePath = strings.TrimSuffix(filePath, ".ready")
	filename := filepath.Base(filePath)
	if !s.isAudioFile(filename) {
		return
	}
	ready, err := readReady(filePath + ".ready")
	if err != nil {
		return
	} // A Create/Write event is not a completion signal.
	if err := s.uploadFile(filePath, filename, ready); err != nil {
		log.Printf("Dropzone import failed; source and marker retained: %s: %v", filename, err)
		return
	}
	// Consume only the marker we processed, never a replacement handoff.
	if current, err := readReady(filePath + ".ready"); err == nil && current == ready {
		if err := os.Remove(filePath + ".ready"); err != nil {
			log.Printf("Imported recording but could not remove readiness marker: %v", err)
		}
	}
	log.Printf("Acknowledged %s handoff; producer-owned source retained for explicit cleanup", filename)
}

// uploadFile uploads the file using the existing pipeline logic
func (s *Service) uploadFile(sourcePath, originalFilename string, ready ReadyManifest) error {
	uploadDir := s.config.UploadDir
	// Keep legacy identity unchanged. An explicit new handoff permits a deliberate
	// reimport while retries of the same marker retain their original identity.
	canonical, err := filepath.Abs(sourcePath)
	if err != nil {
		return err
	}
	identity := canonical + "\x00" + ready.SHA256 + "\x00" + strconv.FormatInt(ready.Bytes, 10)
	if ready.HandoffID != "" {
		identity += "\x00" + ready.HandoffID
	}
	jobID := uuid.NewSHA1(uuid.NameSpaceOID, []byte(identity)).String()
	var existing *models.TranscriptionJob
	if lookup, ok := s.jobRepo.(interface {
		FindByIDIncludingDeleted(context.Context, string) (*models.TranscriptionJob, error)
	}); ok {
		existing, err = lookup.FindByIDIncludingDeleted(context.Background(), jobID)
	} else {
		existing, err = s.jobRepo.FindByID(context.Background(), jobID)
	}
	if err == nil {
		if existing.DeletedAt.Valid {
			// The accepted handoff was deliberately deleted. Acknowledge its replay
			// before touching audio; never restore content into that tombstone.
			return nil
		}
		if err := verifyReadyBytes(existing.AudioPath, ready); err != nil {
			return fmt.Errorf("previous import archive unavailable: %w", err)
		}
		return nil // Lost marker acknowledgment/restart: this handoff already committed.
	} else if !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}
	if err := os.MkdirAll(uploadDir, 0755); err != nil {
		return fmt.Errorf("failed to create upload directory: %v", err)
	}
	ext := filepath.Ext(originalFilename)
	filename := fmt.Sprintf("%s%s", jobID, ext)
	destPath := filepath.Join(uploadDir, filename)

	// Copy file from dropzone to upload directory
	if _, err := os.Lstat(destPath); err == nil {
		// A crash may have left the durable archive before its DB insertion.
		if err := verifyReadyBytes(destPath, ready); err != nil {
			if err := os.Remove(destPath); err != nil {
				return err
			}
		}
	}
	if _, err := os.Stat(destPath); os.IsNotExist(err) {
		if err := s.copyVerifiedFile(sourcePath, destPath, ready); err != nil {
			return fmt.Errorf("failed to copy file: %w", err)
		}
	}
	directory, err := os.Open(uploadDir)
	if err != nil {
		return err
	}
	syncErr := directory.Sync()
	_ = directory.Close()
	if syncErr != nil {
		return syncErr
	}

	// Create job record with "uploaded" status
	job := models.TranscriptionJob{
		ID:        jobID,
		AudioPath: destPath,
		Status:    models.StatusUploaded,
		Title:     &originalFilename, // Use original filename as title
	}

	// Save to database
	if err := s.jobRepo.Create(context.Background(), &job); err != nil {
		// Keep the verified archive for idempotent recovery after a database failure.
		return fmt.Errorf("failed to create job record: %v", err)
	}

	if s.isAutoTranscriptionEnabled() && !job.IsMultiTrack {
		scheduler, ok := s.jobRepo.(interface {
			Schedule(context.Context, *models.TranscriptionJob) error
		})
		if !ok {
			log.Printf("Automatic transcription unavailable; imported job %s remains uploaded", jobID)
		} else {
			if err := s.taskQueue.EnqueuePreparedJob(jobID, func() error { return scheduler.Schedule(context.Background(), &job) }); err != nil {
				log.Printf("Automatic transcription not admitted; imported job %s remains available for manual start: %v", jobID, err)
			}
		}
	}

	log.Printf("Successfully uploaded file %s as job %s", originalFilename, jobID)
	return nil
}

// isAutoTranscriptionEnabled checks if auto-transcription is enabled for any user
func (s *Service) isAutoTranscriptionEnabled() bool {
	count, err := s.userRepo.CountWithAutoTranscription(context.Background())
	if err != nil {
		log.Printf("Error checking auto-transcription settings: %v", err)
		return false
	}

	return count > 0
}

// copyVerifiedFile streams only a producer-declared complete immutable recording.
func (s *Service) copyVerifiedFile(src, dst string, ready ReadyManifest) (resultErr error) {
	before, err := os.Lstat(src)
	if err != nil {
		return err
	}
	if !before.Mode().IsRegular() || before.Size() != ready.Bytes {
		return fmt.Errorf("recording is not ready or size changed")
	}
	source, err := os.Open(src)
	if err != nil {
		return err
	}
	defer source.Close()
	opened, err := source.Stat()
	if err != nil || !os.SameFile(before, opened) {
		return fmt.Errorf("recording changed before copy")
	}
	destination, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	defer func() {
		closeErr := destination.Close()
		if resultErr == nil {
			resultErr = closeErr
		}
		if resultErr != nil {
			_ = os.Remove(dst)
		}
	}()
	digest := sha256.New()
	count, err := io.Copy(io.MultiWriter(destination, digest), io.LimitReader(source, ready.Bytes+1))
	if err != nil {
		return err
	}
	if count != ready.Bytes || hex.EncodeToString(digest.Sum(nil)) != ready.SHA256 {
		return fmt.Errorf("recording does not match its completion marker")
	}
	after, err := source.Stat()
	if err != nil || after.Size() != before.Size() || !after.ModTime().Equal(before.ModTime()) {
		return fmt.Errorf("recording changed while being copied")
	}
	return destination.Sync()
}

func verifyReadyBytes(path string, ready ReadyManifest) error {
	info, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Size() != ready.Bytes {
		return fmt.Errorf("archive size or type differs")
	}
	source, err := os.Open(path)
	if err != nil {
		return err
	}
	defer source.Close()
	digest := sha256.New()
	count, err := io.Copy(digest, io.LimitReader(source, ready.Bytes+1))
	if err != nil {
		return err
	}
	if count != ready.Bytes || hex.EncodeToString(digest.Sum(nil)) != ready.SHA256 {
		return fmt.Errorf("archive checksum differs")
	}
	return nil
}
