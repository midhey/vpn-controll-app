package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"

	"vpn-control-app/agent/internal/agent"
)

type fakeService struct {
	peersCalled bool
	issueReq    agent.IssueRequest
	revokedKey  string
}

func (f *fakeService) Inspect(context.Context) (agent.InspectResult, error) {
	return agent.InspectResult{Container: "amnezia-awg2", PeerCountRuntime: 1}, nil
}

func (f *fakeService) Peers(context.Context) ([]agent.PeerView, error) {
	f.peersCalled = true
	return []agent.PeerView{{PublicKey: "peer", InConfig: true}}, nil
}

func (f *fakeService) Issue(_ context.Context, req agent.IssueRequest) (agent.IssueResult, error) {
	f.issueReq = req
	return agent.IssueResult{PublicKey: "new-peer", ClientIP: "10.8.1.2", Config: "[Interface]\n", VPNURL: "vpn://test"}, nil
}

func (f *fakeService) Revoke(_ context.Context, publicKey string) (agent.RevokeResult, error) {
	f.revokedKey = publicKey
	return agent.RevokeResult{Revoked: true, PublicKey: publicKey}, nil
}

func TestHealthDoesNotRequireAuth(t *testing.T) {
	server := newTestServer(t, &fakeService{})
	req := httptest.NewRequest(http.MethodGet, "/health", nil)
	res := httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
	var body map[string]any
	if err := json.Unmarshal(res.Body.Bytes(), &body); err != nil {
		t.Fatal(err)
	}
	if body["status"] != "ok" {
		t.Fatalf("status body = %#v", body)
	}
}

func TestSignedPeersRequest(t *testing.T) {
	service := &fakeService{}
	server := newTestServer(t, service)
	req := signedRequest(t, http.MethodGet, "/peers", nil)
	req.RemoteAddr = "127.0.0.1:12345"
	res := httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
	if !service.peersCalled {
		t.Fatal("Peers was not called")
	}
}

func TestUnsignedPeersRequestRejected(t *testing.T) {
	server := newTestServer(t, &fakeService{})
	req := httptest.NewRequest(http.MethodGet, "/peers", nil)
	req.RemoteAddr = "127.0.0.1:12345"
	res := httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
}

func TestAllowlistRejectsRemoteAddress(t *testing.T) {
	server := newTestServer(t, &fakeService{})
	req := signedRequest(t, http.MethodGet, "/peers", nil)
	req.RemoteAddr = "203.0.113.10:12345"
	res := httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusForbidden {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
}

func TestIssueAndRevokeHTTPShapes(t *testing.T) {
	service := &fakeService{}
	server := newTestServer(t, service)
	body := []byte(`{"name":"Phone","dns":["1.1.1.1"],"endpoint_host":"72.56.69.23","metadata":{"device":"1"}}`)
	req := signedRequest(t, http.MethodPost, "/peers", body)
	req.Header.Set("Content-Type", "application/json")
	req.RemoteAddr = "127.0.0.1:12345"
	res := httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
	if service.issueReq.Name != "Phone" || service.issueReq.EndpointHost != "72.56.69.23" {
		t.Fatalf("issue request = %#v", service.issueReq)
	}

	publicKey := "abc/def+="
	req = signedRequest(t, http.MethodDelete, "/peers/"+url.PathEscape(publicKey), nil)
	req.RemoteAddr = "127.0.0.1:12345"
	res = httptest.NewRecorder()

	server.Handler().ServeHTTP(res, req)

	if res.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", res.Code, res.Body.String())
	}
	if service.revokedKey != publicKey {
		t.Fatalf("revoked key = %q, want %q", service.revokedKey, publicKey)
	}
}

func newTestServer(t *testing.T, service AgentService) *Server {
	t.Helper()
	server, err := NewServer(service, Config{
		Auth: AuthConfig{
			KeyID:      "test-key",
			Secret:     "test-secret",
			AllowedIPs: []string{"127.0.0.1"},
			Now:        func() time.Time { return time.Date(2026, 7, 1, 12, 0, 0, 0, time.UTC) },
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return server
}

func signedRequest(t *testing.T, method, path string, body []byte) *http.Request {
	t.Helper()
	timestamp := time.Date(2026, 7, 1, 12, 0, 0, 0, time.UTC).Format(time.RFC3339)
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	req.Header.Set(headerKeyID, "test-key")
	req.Header.Set(headerTimestamp, timestamp)
	req.Header.Set(headerSignature, SignRequest([]byte("test-secret"), method, path, timestamp, body))
	return req
}
