package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/glebarez/sqlite"
	"github.com/stretchr/testify/require"
	"gorm.io/gorm"
	"scriberr/internal/auth"
	"scriberr/internal/config"
	"scriberr/internal/llm"
	"scriberr/internal/models"
	"scriberr/internal/queue"
	"scriberr/internal/repository"
	"scriberr/internal/service"
)

func regressionHandler(t *testing.T) (*Handler, *gorm.DB) {
	gin.SetMode(gin.TestMode)
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	require.NoError(t, err)
	sql, _ := db.DB()
	sql.SetMaxOpenConns(1)
	t.Cleanup(func() { sql.Close() })
	require.NoError(t, db.AutoMigrate(&models.TranscriptionJob{}, &models.User{}, &models.RefreshToken{}, &models.TranscriptionJobExecution{}, &models.ChatSession{}, &models.ChatMessage{}, &models.Note{}, &models.Summary{}, &models.SpeakerMapping{}, &models.MultiTrackFile{}))
	root := t.TempDir()
	cfg := &config.Config{UploadDir: filepath.Join(root, "uploads"), TranscriptsDir: filepath.Join(root, "transcripts"), TempDir: filepath.Join(root, "temp")}
	repo := repository.NewJobRepository(db)
	h := &Handler{config: cfg, jobRepo: repo, userRepo: repository.NewUserRepository(db), fileService: service.NewFileService(), authService: auth.NewAuthService("test-only-local-secret"), refreshTokenRepo: repository.NewRefreshTokenRepository(db), summaryRepo: repository.NewSummaryRepository(db)}
	h.taskQueue = queue.NewTaskQueue(1, nil, repo)
	t.Cleanup(h.taskQueue.Stop)
	return h, db
}
func requestHandler(method, path string, body io.Reader, fn gin.HandlerFunc) *httptest.ResponseRecorder {
	r := gin.New()
	r.Handle(method, "/jobs/:id", fn)
	w := httptest.NewRecorder()
	r.ServeHTTP(w, httptest.NewRequest(method, path, body))
	return w
}

func TestListRejectsPaginationAndSQLSyntax(t *testing.T) {
	h := &Handler{}
	for _, query := range []string{"limit=0", "limit=-1", "limit=NaN", "limit=1001", "page=0", "page=abc", "sort_by=random%28%29", "sort_order=asc%3BDELETE"} {
		w := requestHandler("GET", "/jobs/list?"+query, nil, h.ListTranscriptionJobs)
		require.Equal(t, 400, w.Code, query)
	}
}

func TestStartMalformedAndFullQueuePreserveCompletedResult(t *testing.T) {
	h, db := regressionHandler(t)
	old := "previous result"
	job := models.TranscriptionJob{ID: "job", AudioPath: "a.wav", Status: models.StatusCompleted, Transcript: &old, Summary: &old}
	require.NoError(t, db.Create(&job).Error)
	for _, body := range []string{"{", `{"batch_size":"wrong"}`} {
		w := requestHandler("POST", "/jobs/job", strings.NewReader(body), h.StartTranscription)
		require.Equal(t, 400, w.Code)
	}
	for i := 0; i < 200; i++ {
		require.NoError(t, h.taskQueue.EnqueueJob(string(rune(i))))
	}
	w := requestHandler("POST", "/jobs/job", strings.NewReader(`{"model":"new"}`), h.StartTranscription)
	require.Equal(t, 503, w.Code)
	stored, err := h.jobRepo.FindByID(context.Background(), "job")
	require.NoError(t, err)
	require.Equal(t, models.StatusCompleted, stored.Status)
	require.Equal(t, old, *stored.Transcript)
	require.Equal(t, old, *stored.Summary)
}

func TestMultipartUploadReturnsJSONAndDeletesOwnedFiles(t *testing.T) {
	h, _ := regressionHandler(t)
	var body bytes.Buffer
	form := multipart.NewWriter(&body)
	for _, name := range []string{"a.wav", "b.wav"} {
		part, err := form.CreateFormFile("files", name)
		require.NoError(t, err)
		_, err = part.Write([]byte("synthetic audio"))
		require.NoError(t, err)
	}
	require.NoError(t, form.Close())
	router := gin.New()
	router.POST("/upload", h.UploadMultiTrack)
	req := httptest.NewRequest("POST", "/upload", &body)
	req.Header.Set("Content-Type", form.FormDataContentType())
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)
	require.Equal(t, 200, w.Code, w.Body.String())
	var job models.TranscriptionJob
	require.NoError(t, json.Unmarshal(w.Body.Bytes(), &job))
	require.NotNil(t, job.MultiTrackFolder)
	require.Len(t, job.MultiTrackFiles, 2)
	require.DirExists(t, *job.MultiTrackFolder)
	w = requestHandler("DELETE", "/jobs/"+job.ID, nil, h.DeleteTranscriptionJob)
	require.Equal(t, 200, w.Code, w.Body.String())
	require.NoDirExists(t, *job.MultiTrackFolder)
	_, err := h.jobRepo.FindByID(context.Background(), job.ID)
	require.ErrorIs(t, err, gorm.ErrRecordNotFound)
}

type failingFileService struct {
	service.FileService
	fail bool
}

func (f *failingFileService) RemoveFile(path string) error {
	if f.fail {
		return errors.New("disk unavailable")
	}
	return f.FileService.RemoveFile(path)
}
func TestDeletionFailureKeepsRetryableIntent(t *testing.T) {
	h, db := regressionHandler(t)
	path := filepath.Join(t.TempDir(), "recording.wav")
	require.NoError(t, os.WriteFile(path, []byte("private"), 0600))
	require.NoError(t, db.Create(&models.TranscriptionJob{ID: "job", Status: models.StatusUploaded, AudioPath: path}).Error)
	fs := &failingFileService{FileService: h.fileService, fail: true}
	h.fileService = fs
	w := requestHandler("DELETE", "/jobs/job", nil, h.DeleteTranscriptionJob)
	require.Equal(t, 500, w.Code)
	job, err := h.jobRepo.FindByID(context.Background(), "job")
	require.NoError(t, err)
	require.Equal(t, models.JobStatus("deleting"), job.Status)
	require.FileExists(t, path)
	fs.fail = false
	w = requestHandler("DELETE", "/jobs/job", nil, h.DeleteTranscriptionJob)
	require.Equal(t, 200, w.Code, w.Body.String())
	require.NoFileExists(t, path)
}
func TestRegisterImmediatelyIssuesMediaCookie(t *testing.T) {
	h, _ := regressionHandler(t)
	w := requestHandler("POST", "/jobs/register", strings.NewReader(`{"username":"secretary","password":"StrongLocalPassword123!","confirmPassword":"StrongLocalPassword123!"}`), h.Register)
	require.Equal(t, 201, w.Code, w.Body.String())
	cookies := w.Result().Cookies()
	names := map[string]*http.Cookie{}
	for _, cookie := range cookies {
		names[cookie.Name] = cookie
	}
	require.Contains(t, names, "scriberr_access_token")
	require.True(t, names["scriberr_access_token"].HttpOnly)
	require.Contains(t, names, "scriberr_refresh_token")
}

type closedStreamService struct {
	llm.Service
	chunks    []string
	streamErr error
	fallback  *llm.ChatResponse
}

func (s closedStreamService) ChatCompletionStream(context.Context, string, []llm.ChatMessage, float64) (<-chan string, <-chan error) {
	content := make(chan string, len(s.chunks))
	errs := make(chan error, 1)
	for _, chunk := range s.chunks {
		content <- chunk
	}
	close(content)
	if s.streamErr != nil {
		errs <- s.streamErr
	}
	close(errs)
	return content, errs
}
func (s closedStreamService) ChatCompletion(context.Context, string, []llm.ChatMessage, float64) (*llm.ChatResponse, error) {
	return s.fallback, nil
}
func TestSummaryDrainsBufferedContentAndDoesNotPersistErrors(t *testing.T) {
	h, db := regressionHandler(t)
	require.NoError(t, db.Create(&models.TranscriptionJob{ID: "job", AudioPath: "a", Status: models.StatusCompleted}).Error)
	for iteration := 0; iteration < 20; iteration++ {
		w := httptest.NewRecorder()
		ctx, _ := gin.CreateTestContext(w)
		ctx.Request = httptest.NewRequest("POST", "/", nil)
		h.processSummarization(ctx, SummarizeRequest{Model: "fake", TranscriptionID: "job"}, closedStreamService{chunks: []string{"Русский ", "қазақша"}}, nil, time.Now())
		require.Equal(t, "Русский қазақша", w.Body.String())
	}
	var count int64
	require.NoError(t, db.Model(&models.Summary{}).Count(&count).Error)
	require.EqualValues(t, 20, count)
	w := httptest.NewRecorder()
	ctx, _ := gin.CreateTestContext(w)
	ctx.Request = httptest.NewRequest("POST", "/", nil)
	h.processSummarization(ctx, SummarizeRequest{Model: "fake", TranscriptionID: "job"}, closedStreamService{chunks: []string{"partial"}, streamErr: errors.New("failed inference")}, nil, time.Now())
	require.NoError(t, db.Model(&models.Summary{}).Count(&count).Error)
	require.EqualValues(t, 20, count)
}

func TestChatCountsTranscriptOnceAndHandlesEmptyFallback(t *testing.T) {
	for _, emptyFallback := range []bool{false, true} {
		t.Run(fmt.Sprint("empty-fallback-", emptyFallback), func(t *testing.T) {
			h, db := regressionHandler(t)
			require.NoError(t, db.AutoMigrate(&models.LLMConfig{}))
			h.chatRepo = repository.NewChatRepository(db)
			h.llmConfigRepo = repository.NewLLMConfigRepository(db)
			h.speakerMappingRepo = repository.NewSpeakerMappingRepository(db)
			requests := make(chan llm.ChatRequest, 2)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.URL.Path == "/api/show" {
					_, _ = w.Write([]byte(`{"model_info":{"llama.context_length":4096}}`))
					return
				}
				var req llm.ChatRequest
				_ = json.NewDecoder(r.Body).Decode(&req)
				requests <- req
				if emptyFallback {
					if req.Stream {
						w.WriteHeader(400)
						_, _ = w.Write([]byte(`{"error":{"code":"unsupported_value"}}`))
					} else {
						_, _ = w.Write([]byte(`{"choices":[]}`))
					}
					return
				}
				_, _ = w.Write([]byte("{\"message\":{\"role\":\"assistant\",\"content\":\"synthetic answer\"},\"done\":true}\n"))
			}))
			defer server.Close()
			cfg := models.LLMConfig{Provider: "ollama", BaseURL: &server.URL, IsActive: true}
			if emptyFallback {
				key := "synthetic"
				cfg.Provider = "openai"
				cfg.OpenAIBaseURL = &server.URL
				cfg.APIKey = &key
			}
			require.NoError(t, db.Create(&cfg).Error)
			text := `{"segments":[{"start":0,"end":1,"text":"` + strings.Repeat("a", 9000) + `"}]}`
			require.NoError(t, db.Create(&models.TranscriptionJob{ID: "job", AudioPath: "a", Status: models.StatusCompleted, Transcript: &text}).Error)
			require.NoError(t, db.Create(&models.ChatSession{ID: "chat", JobID: "job", TranscriptionID: "job", Model: "fixture", Title: "fixture"}).Error)
			router := gin.New()
			router.POST("/chat/:session_id", h.SendChatMessage)
			w := httptest.NewRecorder()
			router.ServeHTTP(w, httptest.NewRequest("POST", "/chat/chat", strings.NewReader(`{"content":"summarize"}`)))
			require.Equal(t, 200, w.Code, w.Body.String())
			if emptyFallback {
				require.Contains(t, w.Body.String(), "model returned no completion")
			} else {
				require.Equal(t, "synthetic answer", w.Body.String())
				sent := <-requests
				estimate := 0
				for _, message := range sent.Messages {
					estimate += (len(message.Content) + 3) / 4
				}
				require.Equal(t, strconv.Itoa(estimate), w.Header().Get("X-Context-Used"))
				require.Less(t, estimate, 3596)
			}
		})
	}
}
