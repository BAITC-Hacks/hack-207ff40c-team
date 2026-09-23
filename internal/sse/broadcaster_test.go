package sse

import (
	"bufio"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestBroadcaster(t *testing.T) {
	b := NewBroadcaster()
	defer b.Shutdown()
	server := httptest.NewServer(b)
	defer server.Close()
	client := &http.Client{Timeout: 2 * time.Second}
	response, err := client.Get(server.URL + "/events?job_id=test-job-1")
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	if response.Header.Get("Content-Type") != "text/event-stream" {
		t.Fatal("missing SSE header")
	}
	reader := bufio.NewReader(response.Body)
	line, err := reader.ReadString('\n')
	if err != nil || !strings.Contains(line, `"type":"connected"`) {
		t.Fatalf("initial event: %q %v", line, err)
	}
	_, _ = reader.ReadString('\n')
	payload := map[string]string{"status": "completed"}
	b.Broadcast("test-job-1", "status_update", payload)
	line, err = reader.ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	expected, _ := json.Marshal(Event{Type: "status_update", Payload: payload})
	if !strings.Contains(line, string(expected)) {
		t.Fatalf("missing broadcast: %q", line)
	}
}

func TestBroadcastAfterShutdownReturns(t *testing.T) {
	b := NewBroadcaster()
	b.Shutdown()
	b.Shutdown()
	done := make(chan struct{})
	go func() { b.Broadcast("job", "complete", nil); close(done) }()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("broadcast blocked after shutdown")
	}
}
