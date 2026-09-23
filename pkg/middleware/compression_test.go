package middleware

import (
	"compress/gzip"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestCompressedStreamFlushesBeforeHandlerCompletes(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(CompressionMiddleware())
	release := make(chan struct{})
	defer close(release)
	router.POST("/stream", func(c *gin.Context) {
		c.Header("Content-Type", "text/plain")
		_, _ = c.Writer.WriteString("қазақша")
		c.Writer.Flush()
		<-release
	})
	server := httptest.NewServer(router)
	defer server.Close()
	req, err := http.NewRequest("POST", server.URL+"/stream", strings.NewReader("{}"))
	require.NoError(t, err)
	req.Header.Set("Accept-Encoding", "gzip")
	req.Header.Set("Content-Type", "application/json")
	client := &http.Client{Timeout: 2 * time.Second}
	response, err := client.Do(req)
	require.NoError(t, err)
	defer response.Body.Close()
	reader, err := gzip.NewReader(response.Body)
	require.NoError(t, err)
	defer reader.Close()
	buf := make([]byte, len("қазақша"))
	_, err = io.ReadFull(reader, buf)
	require.NoError(t, err)
	require.Equal(t, "қазақша", string(buf))
	// Release before httptest waits for the open connection during shutdown.
	release <- struct{}{}
}
