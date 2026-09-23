package dropzone

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"gorm.io/gorm"
	"os"
	"path/filepath"
	"strconv"
	"testing"

	"github.com/glebarez/sqlite"
	"github.com/google/uuid"

	"scriberr/internal/config"
	"scriberr/internal/models"
	"scriberr/internal/repository"
)

type jobFixture struct {
	repository.JobRepository
	jobs []models.TranscriptionJob
}

func (r *jobFixture) FindByID(ctx context.Context, id interface{}) (*models.TranscriptionJob, error) {
	for i := range r.jobs {
		if r.jobs[i].ID == id {
			return &r.jobs[i], nil
		}
	}
	return nil, gorm.ErrRecordNotFound
}
func (r *jobFixture) Create(ctx context.Context, job *models.TranscriptionJob) error {
	r.jobs = append(r.jobs, *job)
	return nil
}
func (r *jobFixture) Schedule(ctx context.Context, job *models.TranscriptionJob) error {
	t := len(r.jobs) - 1
	r.jobs[t].Status = models.StatusPending
	return nil
}

type usersFixture struct{ repository.UserRepository }

func (*usersFixture) CountWithAutoTranscription(context.Context) (int64, error) { return 1, nil }

type fullQueue struct{}

func (fullQueue) EnqueuePreparedJob(string, func() error) error { return errors.New("full") }

func marker(data []byte) ReadyManifest {
	hash := sha256.Sum256(data)
	return ReadyManifest{Bytes: int64(len(data)), SHA256: hex.EncodeToString(hash[:])}
}

func TestGrowingRecordingNeedsCompletionAndIsNeverDeleted(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "meeting.wav")
	repo := &jobFixture{}
	service := NewService(&config.Config{UploadDir: filepath.Join(dir, "uploads")}, fullQueue{}, repo, &usersFixture{})
	original := []byte("first part; final spoken instruction")
	os.WriteFile(source, original[:10], 0600)
	service.processFile(source)
	if len(repo.jobs) != 0 {
		t.Fatal("creation imported an unfinished recording")
	}
	ready := marker(original)
	ready.HandoffID = "7c71e88b-9ce4-4f36-8e14-920f89a339dd"
	encoded, _ := json.Marshal(ready)
	os.WriteFile(source+".ready", encoded, 0600)
	service.processFile(source + ".ready")
	if len(repo.jobs) != 0 {
		t.Fatal("incomplete bytes imported despite marker")
	}
	if _, err := os.Stat(source + ".ready"); err != nil {
		t.Fatal("unfinished handoff marker was removed", err)
	}
	file, _ := os.OpenFile(source, os.O_APPEND|os.O_WRONLY, 0600)
	file.Write(original[10:])
	file.Close()
	service.processFile(source + ".ready")
	if len(repo.jobs) != 1 || repo.jobs[0].Status != models.StatusUploaded {
		t.Fatal("queue failure hid the imported recording", repo.jobs)
	}
	copied, _ := os.ReadFile(repo.jobs[0].AudioPath)
	retained, _ := os.ReadFile(source)
	if string(copied) != string(original) || string(retained) != string(original) {
		t.Fatal("audio lost or changed")
	}
	if _, err := os.Stat(source + ".ready"); !os.IsNotExist(err) {
		t.Fatal("completion marker not consumed")
	}
}

func TestHashMismatchPreservesSourceAndRemovesPartialCopy(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "meeting.wav")
	target := filepath.Join(dir, "copy.wav")
	os.WriteFile(source, []byte("other"), 0600)
	service := &Service{}
	if err := service.copyVerifiedFile(source, target, marker([]byte("truth"))); err == nil {
		t.Fatal("changed content accepted")
	}
	if _, err := os.Stat(target); !os.IsNotExist(err) {
		t.Fatal("invalid archive left behind")
	}
	if data, _ := os.ReadFile(source); string(data) != "other" {
		t.Fatal("producer recording lost")
	}
}

func TestReadyMarkerReplayAfterLostAcknowledgmentCreatesOneJob(t *testing.T) {
	dir := t.TempDir()
	source := filepath.Join(dir, "meeting.wav")
	data := []byte("complete recording")
	os.WriteFile(source, data, 0600)
	repo := &jobFixture{}
	service := NewService(&config.Config{UploadDir: filepath.Join(dir, "uploads")}, fullQueue{}, repo, &usersFixture{})
	encoded, _ := json.Marshal(marker(data))
	for attempt := 0; attempt < 2; attempt++ {
		os.WriteFile(source+".ready", encoded, 0600)
		service.processFile(source + ".ready")
	}
	if len(repo.jobs) != 1 {
		t.Fatalf("marker replay created %d imports", len(repo.jobs))
	}
	if original, _ := os.ReadFile(source); string(original) != string(data) {
		t.Fatal("source lost")
	}
}

func TestDeletedHandoffReplayDoesNotRestoreAudioAndNewHandoffCanImport(t *testing.T) {
	for _, handoff := range []string{"", "7c71e88b-9ce4-4f36-8e14-920f89a339dd"} {
		t.Run("handoff="+handoff, func(t *testing.T) {
			dir := t.TempDir()
			db, err := gorm.Open(sqlite.Open(filepath.Join(dir, "jobs.db")), &gorm.Config{})
			if err != nil {
				t.Fatal(err)
			}
			sqlDB, err := db.DB()
			if err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() { _ = sqlDB.Close() })
			if err := db.AutoMigrate(&models.TranscriptionJob{}); err != nil {
				t.Fatal(err)
			}
			source := filepath.Join(dir, "meeting.wav")
			data := []byte("same completed recording, intentionally imported again")
			if err := os.WriteFile(source, data, 0600); err != nil {
				t.Fatal(err)
			}
			repo := repository.NewJobRepository(db)
			service := NewService(&config.Config{UploadDir: filepath.Join(dir, "uploads")}, fullQueue{}, repo, &usersFixture{})
			ready := marker(data)
			ready.HandoffID = handoff
			publish := func() {
				t.Helper()
				encoded, err := json.Marshal(ready)
				if err != nil {
					t.Fatal(err)
				}
				if err := os.WriteFile(source+".ready", encoded, 0600); err != nil {
					t.Fatal(err)
				}
				service.processFile(source + ".ready")
				if _, err := os.Stat(source + ".ready"); !os.IsNotExist(err) {
					t.Fatalf("accepted/replayed handoff was not acknowledged: %v", err)
				}
			}
			publish()
			var first models.TranscriptionJob
			if err := db.First(&first).Error; err != nil {
				t.Fatal(err)
			}
			if handoff == "" {
				// Preserve the original ID formula for already-written legacy markers.
				canonical, _ := filepath.Abs(source)
				legacyID := uuid.NewSHA1(uuid.NameSpaceOID, []byte(canonical+"\x00"+ready.SHA256+"\x00"+strconv.FormatInt(ready.Bytes, 10))).String()
				if first.ID != legacyID {
					t.Fatal("legacy marker identity changed")
				}
			}
			if err := repo.Delete(context.Background(), first.ID); err != nil {
				t.Fatal(err)
			}
			if err := os.Remove(first.AudioPath); err != nil {
				t.Fatal(err)
			}
			// Current deletion scrubs content while retaining the deleted primary key.
			if err := db.Unscoped().Model(&models.TranscriptionJob{}).Where("id = ?", first.ID).Updates(map[string]any{"audio_path": "", "status": "deleted"}).Error; err != nil {
				t.Fatal(err)
			}
			publish()
			if _, err := os.Stat(first.AudioPath); !os.IsNotExist(err) {
				t.Fatalf("replayed deleted handoff recreated audio: %v", err)
			}
			var active, total int64
			if err := db.Model(&models.TranscriptionJob{}).Count(&active).Error; err != nil || active != 0 {
				t.Fatalf("deleted recording resurrected: active=%d err=%v", active, err)
			}
			if err := db.Unscoped().Model(&models.TranscriptionJob{}).Count(&total).Error; err != nil || total != 1 {
				t.Fatalf("deleted handoff duplicated: total=%d err=%v", total, err)
			}
			ready.HandoffID = "eb5bf13c-4b7b-4cb2-90f8-c68cb21c8475"
			publish()
			publish() // A retry of the new intentional handoff is still idempotent.
			if err := db.Model(&models.TranscriptionJob{}).Count(&active).Error; err != nil || active != 1 {
				t.Fatalf("new handoff did not import exactly once: active=%d err=%v", active, err)
			}
			if err := db.Unscoped().Model(&models.TranscriptionJob{}).Count(&total).Error; err != nil || total != 2 {
				t.Fatalf("new handoff changed the old tombstone: total=%d err=%v", total, err)
			}
			var second models.TranscriptionJob
			if err := db.First(&second).Error; err != nil || second.ID == first.ID {
				t.Fatalf("intentional import reused deleted identity: %v", err)
			}
			if archived, err := os.ReadFile(second.AudioPath); err != nil || string(archived) != string(data) {
				t.Fatalf("new import archive mismatch: %v", err)
			}
			if original, err := os.ReadFile(source); err != nil || string(original) != string(data) {
				t.Fatalf("producer source changed: %v", err)
			}
		})
	}
}

func TestInvalidHandoffIDRetainsMarkerAndSource(t *testing.T) {
	for _, id := range []string{"not-a-uuid", uuid.Nil.String(), "urn:uuid:7c71e88b-9ce4-4f36-8e14-920f89a339dd"} {
		t.Run(id, func(t *testing.T) {
			dir := t.TempDir()
			source := filepath.Join(dir, "meeting.wav")
			data := []byte("complete recording")
			if err := os.WriteFile(source, data, 0600); err != nil {
				t.Fatal(err)
			}
			ready := marker(data)
			ready.HandoffID = id
			encoded, _ := json.Marshal(ready)
			if err := os.WriteFile(source+".ready", encoded, 0600); err != nil {
				t.Fatal(err)
			}
			repo := &jobFixture{}
			service := NewService(&config.Config{UploadDir: filepath.Join(dir, "uploads")}, fullQueue{}, repo, &usersFixture{})
			service.processFile(source + ".ready")
			if len(repo.jobs) != 0 {
				t.Fatal("invalid handoff imported")
			}
			if retained, err := os.ReadFile(source + ".ready"); err != nil || string(retained) != string(encoded) {
				t.Fatalf("invalid marker changed or removed: %v", err)
			}
			if original, err := os.ReadFile(source); err != nil || string(original) != string(data) {
				t.Fatalf("source changed or removed: %v", err)
			}
		})
	}
}
