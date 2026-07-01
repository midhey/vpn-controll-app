package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"vpn-control-app/agent/internal/agent"
)

const Version = "0.2.0"

type AgentService interface {
	Inspect(context.Context) (agent.InspectResult, error)
	Peers(context.Context) ([]agent.PeerView, error)
	Issue(context.Context, agent.IssueRequest) (agent.IssueResult, error)
	Revoke(context.Context, string) (agent.RevokeResult, error)
}

type Server struct {
	service AgentService
	auth    *authenticator
}

type Config struct {
	Auth AuthConfig
}

type httpError struct {
	status  int
	message string
}

func (e httpError) Error() string {
	return e.message
}

func NewServer(service AgentService, config Config) (*Server, error) {
	auth, err := newAuthenticator(config.Auth)
	if err != nil {
		return nil, err
	}
	return &Server{service: service, auth: auth}, nil
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/status", s.withAuth(s.handleStatus))
	mux.HandleFunc("/peers", s.withAuth(s.handlePeers))
	mux.HandleFunc("/peers/", s.withAuth(s.handlePeer))
	return mux
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, httpError{status: http.StatusMethodNotAllowed, message: "method not allowed"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"status":  "ok",
		"version": Version,
	})
}

func (s *Server) handleStatus(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, httpError{status: http.StatusMethodNotAllowed, message: "method not allowed"})
		return
	}
	result, err := s.service.Inspect(r.Context())
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handlePeers(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		result, err := s.service.Peers(r.Context())
		if err != nil {
			writeError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
	case http.MethodPost:
		var req issueHTTPReq
		if err := decodeJSON(r, &req); err != nil {
			writeError(w, err)
			return
		}
		result, err := s.service.Issue(r.Context(), agent.IssueRequest{
			Name:         req.Name,
			DNS:          req.DNS,
			EndpointHost: req.EndpointHost,
		})
		if err != nil {
			writeError(w, err)
			return
		}
		writeJSON(w, http.StatusCreated, result)
	default:
		writeError(w, httpError{status: http.StatusMethodNotAllowed, message: "method not allowed"})
	}
}

func (s *Server) handlePeer(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		writeError(w, httpError{status: http.StatusMethodNotAllowed, message: "method not allowed"})
		return
	}
	raw := strings.TrimPrefix(r.URL.EscapedPath(), "/peers/")
	publicKey, err := url.PathUnescape(raw)
	if err != nil || publicKey == "" {
		writeError(w, httpError{status: http.StatusBadRequest, message: "invalid public key"})
		return
	}
	result, err := s.service.Revoke(r.Context(), publicKey)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) withAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 1<<20))
		if err != nil {
			writeError(w, httpError{status: http.StatusBadRequest, message: "request body is too large"})
			return
		}
		r.Body = io.NopCloser(bytes.NewReader(body))
		if err := s.auth.authorize(r, body); err != nil {
			writeError(w, err)
			return
		}
		next(w, r)
	}
}

type issueHTTPReq struct {
	Name         string         `json:"name"`
	DNS          []string       `json:"dns"`
	EndpointHost string         `json:"endpoint_host"`
	Metadata     map[string]any `json:"metadata,omitempty"`
}

func decodeJSON(r *http.Request, out any) error {
	defer r.Body.Close()
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(out); err != nil {
		return httpError{status: http.StatusBadRequest, message: "invalid JSON: " + err.Error()}
	}
	if decoder.Decode(&struct{}{}) != io.EOF {
		return httpError{status: http.StatusBadRequest, message: "invalid JSON: multiple values"}
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	encoder := json.NewEncoder(w)
	encoder.SetIndent("", "  ")
	_ = encoder.Encode(value)
}

func writeError(w http.ResponseWriter, err error) {
	status := http.StatusInternalServerError
	message := "internal error"
	var apiErr httpError
	if errors.As(err, &apiErr) {
		status = apiErr.status
		message = apiErr.message
	} else if err != nil {
		message = err.Error()
	}
	writeJSON(w, status, map[string]any{
		"error":       message,
		"status":      status,
		"status_text": http.StatusText(status),
	})
}

func ListenAndServe(ctx context.Context, addr string, handler http.Handler) error {
	server := &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
	}
	errCh := make(chan error, 1)
	go func() {
		errCh <- server.ListenAndServe()
	}()
	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			return err
		}
		return ctx.Err()
	case err := <-errCh:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return fmt.Errorf("serve %s: %w", addr, err)
	}
}
