package cli

import (
	"context"
	"errors"
	"fmt"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) { return f(request) }

func TestCallbackNonceRequiredBeforeTokenAccepted(t *testing.T) {
	received := make(chan string, 1)
	handler := callbackHandler("expected-state", received)
	for _, query := range []string{"token=secret", "state=wrong&token=secret"} {
		response := httptest.NewRecorder()
		handler.ServeHTTP(response, httptest.NewRequest("GET", "/callback?"+query, nil))
		if response.Code != 403 {
			t.Fatal(response.Code)
		}
	}
	if len(received) != 0 {
		t.Fatal("unsolicited token was accepted")
	}
	query := url.Values{"state": {"expected-state"}, "token": {"secret"}}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, httptest.NewRequest("GET", "/callback?"+query.Encode(), nil))
	if response.Code != 200 || <-received != "secret" {
		t.Fatal("valid callback rejected")
	}
}

func TestTokenStdinUsesRegisteredFlagAndPrivateConfiguration(t *testing.T) {
	if loginCmd.Flags().Lookup("token-stdin") == nil {
		t.Fatal("installer flag missing")
	}
	oldPath, oldServer, oldStdin := cfgFile, serverURL, tokenStdin
	t.Cleanup(func() { cfgFile, serverURL, tokenStdin = oldPath, oldServer, oldStdin; viper.Reset() })
	cfgFile = filepath.Join(t.TempDir(), "settings.yaml")
	serverURL = "http://127.0.0.1:8080"
	tokenStdin = true
	command := &cobra.Command{}
	command.SetIn(strings.NewReader("test-token-from-stdin\n"))
	command.SetOut(io.Discard)
	if err := runLogin(command, nil); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(cfgFile)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "test-token-from-stdin") {
		t.Fatal("token missing")
	}
	info, _ := os.Stat(cfgFile)
	if info.Mode().Perm() != 0600 {
		t.Fatal("credential file permissions", info.Mode())
	}
	if _, err := readLoginToken(strings.NewReader(strings.Repeat("x", 16385))); err == nil {
		t.Fatal("oversized stdin token accepted")
	}
}

func TestUploadStreamsMultipartAndStopsOnDeadline(t *testing.T) {
	source := filepath.Join(t.TempDir(), "meeting.wav")
	if err := os.WriteFile(source, []byte(strings.Repeat("audio", 30000)), 0600); err != nil {
		t.Fatal(err)
	}
	client := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		if request.ContentLength > 0 {
			t.Fatal("upload unexpectedly buffered into a known-length body")
		}
		_, params, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
		if err != nil {
			t.Fatal(err)
		}
		reader := multipart.NewReader(request.Body, params["boundary"])
		part, err := reader.NextPart()
		if err != nil {
			t.Fatal(err)
		}
		if part.FormName() != "audio" {
			t.Fatal(part.FormName())
		}
		bytes, err := io.Copy(io.Discard, part)
		if err != nil || bytes != 150000 {
			t.Fatal(bytes, err)
		}
		part, err = reader.NextPart()
		if err != nil || part.FormName() != "title" {
			t.Fatal(err)
		}
		if _, err := io.Copy(io.Discard, part); err != nil {
			t.Fatal(err)
		}
		if _, err := reader.NextPart(); err != io.EOF {
			t.Fatal(err)
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"id":"fixture"}`)), Header: make(http.Header)}, nil
	})}
	cfg := &Config{ServerURL: "http://127.0.0.1:9999", Token: "test-token"}
	if err := uploadFileContext(context.Background(), cfg, source, client); err != nil {
		t.Fatal(err)
	}
	client.Transport = roundTripFunc(func(request *http.Request) (*http.Response, error) {
		<-request.Context().Done()
		return nil, request.Context().Err()
	})
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	start := time.Now()
	err := uploadFileContext(ctx, cfg, source, client)
	if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > time.Second {
		t.Fatalf("unbounded upload: %v", err)
	}
}

func TestUploadRejectsPrematureSuccessWithoutSendingFile(t *testing.T) {
	source := filepath.Join(t.TempDir(), "meeting.wav")
	os.WriteFile(source, []byte("audio"), 0600)
	client := &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("{}")), Header: make(http.Header)}, nil
	})}
	if err := uploadFileContext(context.Background(), &Config{ServerURL: "http://127.0.0.1:9999", Token: "t"}, source, client); err == nil {
		t.Fatal("accepted an upload whose body never reached the server")
	}
}

func TestWatcherBoundsConcurrentUploadsAndCancelsWorkers(t *testing.T) {
	directory := t.TempDir()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var active, peak atomic.Int32
	started := make(chan struct{}, 32)
	done := make(chan error, 1)
	go func() {
		done <- watchFolderWithUpload(ctx, directory, func(ctx context.Context, path string) error {
			count := active.Add(1)
			defer active.Add(-1)
			for old := peak.Load(); count > old; old = peak.Load() {
				if peak.CompareAndSwap(old, count) {
					break
				}
			}
			started <- struct{}{}
			<-ctx.Done()
			return ctx.Err()
		})
	}()
	// Allow the local fsnotify subscription to open; no external services involved.
	time.Sleep(100 * time.Millisecond)
	for index := 0; index < 30; index++ {
		if err := os.WriteFile(filepath.Join(directory, fmt.Sprintf("%02d.wav", index)), []byte("fixture"), 0600); err != nil {
			t.Fatal(err)
		}
	}
	for index := 0; index < 2; index++ {
		select {
		case <-started:
		case <-time.After(5 * time.Second):
			t.Fatal("watcher did not upload")
		}
	}
	time.Sleep(100 * time.Millisecond)
	if peak.Load() != 2 {
		t.Fatalf("unbounded uploads: %d", peak.Load())
	}
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("workers did not cancel")
	}
	if files, _ := os.ReadDir(directory); len(files) != 30 {
		t.Fatal("backlogged originals were lost")
	}
}
