package cli

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os/exec"
	"runtime"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

var loginCmd = &cobra.Command{Use: "login", Short: "Authenticate with the Scriberr server", RunE: runLogin}
var serverURL string
var tokenStdin bool

func init() {
	rootCmd.AddCommand(loginCmd)
	loginCmd.Flags().StringVarP(&serverURL, "server", "s", "http://localhost:8080", "Scriberr server URL")
	loginCmd.Flags().BoolVar(&tokenStdin, "token-stdin", false, "Read a token from stdin without exposing it in process arguments")
}

func normalizeServerURL(raw string) (string, error) {
	parsed, err := url.Parse(raw)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") || parsed.Hostname() == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" {
		return "", fmt.Errorf("server URL must be an HTTP(S) origin without credentials, query or fragment")
	}
	if parsed.Path != "" && parsed.Path != "/" {
		return "", fmt.Errorf("server URL must not contain a path")
	}
	return strings.TrimSuffix(parsed.String(), "/"), nil
}

func readLoginToken(source io.Reader) (string, error) {
	data, err := io.ReadAll(io.LimitReader(source, 16385))
	if err != nil {
		return "", err
	}
	token := strings.TrimSpace(string(data))
	if len(data) > 16384 || token == "" || strings.ContainsAny(token, "\r\n\x00\t ") {
		return "", fmt.Errorf("invalid or oversized token")
	}
	return token, nil
}

func callbackHandler(state string, tokenChan chan<- string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Referrer-Policy", "no-referrer")
		if r.Method != http.MethodGet || r.URL.Path != "/callback" {
			http.NotFound(w, r)
			return
		}
		if subtle.ConstantTimeCompare([]byte(r.URL.Query().Get("state")), []byte(state)) != 1 {
			http.Error(w, "Authorization state mismatch", http.StatusForbidden)
			return
		}
		token, err := readLoginToken(strings.NewReader(r.URL.Query().Get("token")))
		if err != nil {
			http.Error(w, "Invalid authorization token", http.StatusBadRequest)
			return
		}
		select {
		case tokenChan <- token:
			fmt.Fprint(w, "Authorization received. Return to the CLI to confirm it was saved.")
		default:
			http.Error(w, "Authorization already received", http.StatusConflict)
		}
	})
}

func runLogin(cmd *cobra.Command, args []string) error {
	origin, err := normalizeServerURL(serverURL)
	if err != nil {
		return err
	}
	if tokenStdin {
		token, err := readLoginToken(cmd.InOrStdin())
		if err != nil {
			return err
		}
		if _, err = SaveConfig(origin, token, ""); err != nil {
			return err
		}
		fmt.Fprintln(cmd.OutOrStdout(), "Configuration saved.")
		return nil
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return fmt.Errorf("start CLI listener: %w", err)
	}
	defer listener.Close()
	nonce := make([]byte, 32)
	if _, err := rand.Read(nonce); err != nil {
		return err
	}
	state := base64.RawURLEncoding.EncodeToString(nonce)
	tokenChan, errChan := make(chan string, 1), make(chan error, 1)
	server := &http.Server{Handler: callbackHandler(state, tokenChan), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 10 * time.Second, IdleTimeout: 5 * time.Second, MaxHeaderBytes: 32768}
	defer func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = server.Shutdown(ctx)
	}()
	go func() {
		if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
			errChan <- err
		}
	}()
	callbackURL := "http://" + listener.Addr().String() + "/callback"
	query := url.Values{"callback_url": {callbackURL}, "device_name": {"Scriberr CLI"}, "state": {state}}
	authURL := origin + "/auth/cli/authorize?" + query.Encode()
	fmt.Fprintln(cmd.OutOrStdout(), "Authorize this CLI in your browser:", authURL)
	if err := openBrowser(authURL); err != nil {
		fmt.Fprintln(cmd.OutOrStdout(), "Open the displayed address manually.")
	}
	ctx, cancel := context.WithTimeout(cmd.Context(), 5*time.Minute)
	defer cancel()
	select {
	case token := <-tokenChan:
		if _, err := SaveConfig(origin, token, ""); err != nil {
			return err
		}
		fmt.Fprintln(cmd.OutOrStdout(), "Configuration saved.")
		return nil
	case err := <-errChan:
		return err
	case <-ctx.Done():
		return fmt.Errorf("CLI authorization interrupted: %w", ctx.Err())
	}
}

func openBrowser(address string) error {
	command, args := "xdg-open", []string{address}
	switch runtime.GOOS {
	case "windows":
		command, args = "rundll32", []string{"url.dll,FileProtocolHandler", address}
	case "darwin":
		command = "open"
	}
	process := exec.Command(command, args...)
	if err := process.Start(); err != nil {
		return err
	}
	go func() { _ = process.Wait() }()
	return nil
}
