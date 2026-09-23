package cli

import (
	"context"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
	"path/filepath"
	"time"
)

const uploadTimeout = 10 * time.Minute

func UploadFile(filePath string) error {
	ctx, cancel := context.WithTimeout(context.Background(), uploadTimeout)
	defer cancel()
	return uploadFileContext(ctx, GetConfig(), filePath, &http.Client{Timeout: uploadTimeout})
}

func uploadFileContext(ctx context.Context, config *Config, filePath string, client *http.Client) (resultErr error) {
	origin, err := normalizeServerURL(config.ServerURL)
	if err != nil {
		return err
	}
	if config.Token == "" {
		return fmt.Errorf("not logged in; run 'scriberr login'")
	}
	file, err := os.Open(filePath)
	if err != nil {
		return fmt.Errorf("open upload: %w", err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() || info.Size() < 1 {
		return fmt.Errorf("upload must be a nonempty regular file")
	}
	reader, writer := io.Pipe()
	multipartWriter := multipart.NewWriter(writer)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, origin+"/api/v1/transcription/upload", reader)
	if err != nil {
		reader.Close()
		writer.Close()
		return err
	}
	request.Header.Set("Content-Type", multipartWriter.FormDataContentType())
	request.Header.Set("Authorization", "Bearer "+config.Token)
	completed := make(chan error, 1)
	go func() {
		part, copyErr := multipartWriter.CreateFormFile("audio", filepath.Base(filePath))
		if copyErr == nil {
			_, copyErr = io.Copy(part, file)
		}
		if copyErr == nil {
			copyErr = multipartWriter.WriteField("title", filepath.Base(filePath))
		}
		if copyErr == nil {
			copyErr = multipartWriter.Close()
		}
		_ = writer.CloseWithError(copyErr)
		completed <- copyErr
	}()
	defer func() {
		_ = reader.Close()
		if copyErr := <-completed; resultErr == nil && copyErr != nil {
			resultErr = fmt.Errorf("upload body was not completely sent: %w", copyErr)
		}
	}()
	safeClient := *client
	safeClient.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	response, err := safeClient.Do(request)
	if err != nil {
		return fmt.Errorf("send upload: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusCreated && response.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(io.LimitReader(response.Body, 4096))
		return fmt.Errorf("upload failed with status %d: %s", response.StatusCode, body)
	}
	// Drain a bounded response. The transport/context bounds both body and upload time.
	_, err = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
	return err
}
