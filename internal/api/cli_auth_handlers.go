package api

import (
	"encoding/base64"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"strconv"

	"github.com/gin-gonic/gin"
)

// AuthorizeCLIRequest represents the request body for confirming CLI authorization
type AuthorizeCLIRequest struct {
	CallbackURL string `json:"callback_url" binding:"required"`
	DeviceName  string `json:"device_name"`
	State       string `json:"state" binding:"required"`
}

// The CLI listener is literal loopback on its own ephemeral port. Never send a
// durable credential to a supplied web origin, hostname alias or arbitrary path.
func validateCLICallback(raw, state string) (*url.URL, error) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return nil, fmt.Errorf("invalid CLI callback")
	}
	port, err := strconv.Atoi(parsed.Port())
	ip := net.ParseIP(parsed.Hostname())
	nonce, nonceErr := base64.RawURLEncoding.DecodeString(state)
	if parsed.Scheme != "http" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || parsed.Path != "/callback" || parsed.RawPath != "" || parsed.Opaque != "" || ip == nil || !ip.IsLoopback() || (parsed.Hostname() != "127.0.0.1" && parsed.Hostname() != "::1") || err != nil || port < 1 || port > 65535 || nonceErr != nil || len(nonce) != 32 || len(state) != 43 {
		return nil, fmt.Errorf("CLI callback must be an exact loopback listener with a valid request state")
	}
	return parsed, nil
}

// AuthorizeCLI validates the user session and returns user info for the confirmation page
// GET /api/auth/cli/authorize
func (h *Handler) AuthorizeCLI(c *gin.Context) {
	// User ID is set by middleware
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}

	// Fetch full user object
	u, err := h.userRepo.FindByID(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch user"})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"status": "authorized",
		"user": gin.H{
			"id":       u.ID,
			"username": u.Username,
		},
	})
}

// ConfirmCLIAuthorization generates a token and returns the redirect URL for the CLI
// POST /api/auth/cli/authorize
func (h *Handler) ConfirmCLIAuthorization(c *gin.Context) {
	var req AuthorizeCLIRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	callbackURL, err := validateCLICallback(req.CallbackURL, req.State)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// User ID is set by middleware
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}

	// Fetch full user object
	u, err := h.userRepo.FindByID(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to fetch user"})
		return
	}

	// Generate long-lived token
	token, err := h.authService.GenerateLongLivedToken(u)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	q := callbackURL.Query()
	q.Set("token", token)
	q.Set("state", req.State)
	q.Set("username", u.Username)
	callbackURL.RawQuery = q.Encode()

	c.JSON(http.StatusOK, gin.H{
		"redirect_url": callbackURL.String(),
	})
}
