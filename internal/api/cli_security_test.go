package api

import (
	"bytes"
	"encoding/base64"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestCLICallbackRequiresExactLoopbackAndNonce(t *testing.T) {
	state := base64.RawURLEncoding.EncodeToString(make([]byte, 32))
	for _, callback := range []string{"http://127.0.0.1:12345/callback", "http://[::1]:12345/callback"} {
		if _, err := validateCLICallback(callback, state); err != nil {
			t.Fatal(err)
		}
	}
	for _, callback := range []string{"https://evil.example/callback", "http://localhost:123/callback", "http://127.0.0.1.evil.example:123/callback", "http://127.0.0.1/callback", "http://127.0.0.1:0/callback", "http://127.0.0.1:99999/callback", "http://127.0.0.1:123/", "http://127.0.0.1:123/callback?to=evil", "http://127.0.0.1:123/callback#secret", "http://user@127.0.0.1:123/callback", "http://[::ffff:127.0.0.1]:123/callback"} {
		if _, err := validateCLICallback(callback, state); err == nil {
			t.Errorf("accepted unsafe callback %s", callback)
		}
	}
	for _, state := range []string{"", "short", strings.Repeat("!", 43)} {
		if _, err := validateCLICallback("http://127.0.0.1:123/callback", state); err == nil {
			t.Fatal("accepted invalid state")
		}
	}
}

func TestUnsafeCLICallbackRejectedBeforeIssuingToken(t *testing.T) {
	handler := &Handler{}
	router := gin.New()
	router.POST("/authorize", handler.ConfirmCLIAuthorization)
	body := `{"callback_url":"https://attacker.invalid/callback","state":"` + base64.RawURLEncoding.EncodeToString(make([]byte, 32)) + `"}`
	response := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/authorize", strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(response, request)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("got %d: %s", response.Code, response.Body)
	}
}

func TestInstallScriptKeepsShellSubstitutionsInertAndUsesSupportedLogin(t *testing.T) {
	bash, err := exec.LookPath("bash")
	if err != nil {
		t.Skip("bash unavailable")
	}
	marker := filepath.Join(t.TempDir(), "executed")
	token := "a'$(touch " + marker + ")`touch " + marker + "`\"b"
	handler := &Handler{}
	router := gin.New()
	router.GET("/install.sh", handler.GetInstallScript)
	request := httptest.NewRequest("GET", "http://station.local/install.sh?token="+url.QueryEscape(token), nil)
	request.Header.Set("X-Forwarded-Host", "$(touch "+marker+")")
	request.Header.Set("X-Forwarded-Proto", "https; touch "+marker)
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	if response.Code != 200 {
		t.Fatalf("render failed %s", response.Body)
	}
	script := response.Body.String()
	if !strings.Contains(script, "--token-stdin") || strings.Contains(script, "--token-only") {
		t.Fatal("unsupported login contract")
	}
	prefix := strings.SplitN(script, "INSTALL_DIR=", 2)[0]
	out, err := exec.Command(bash, "-c", prefix+"printf '%s\\n%s' \"$SERVER_URL\" \"$TOKEN\"").CombinedOutput()
	if err != nil {
		t.Fatalf("shell failed: %v %s", err, out)
	}
	if !bytes.Equal(out, []byte("http://station.local\n"+token)) {
		t.Fatalf("values changed: %q", out)
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("shell substitution executed")
	}
	if response.Header().Get("Cache-Control") != "no-store" {
		t.Fatal("credential script must not be cached")
	}
}
