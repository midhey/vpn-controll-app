package httpapi

import (
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"net"
	"net/http"
	"strings"
	"time"
)

const (
	headerKeyID     = "X-Agent-Key-Id"
	headerTimestamp = "X-Agent-Timestamp"
	headerSignature = "X-Agent-Signature"
)

type AuthConfig struct {
	KeyID       string
	Secret      string
	AllowedIPs  []string
	AllowedSkew time.Duration
	AllowNoAuth bool
	Now         func() time.Time
}

type authenticator struct {
	keyID       string
	secret      []byte
	allowedNets []netipNet
	allowedSkew time.Duration
	allowNoAuth bool
	now         func() time.Time
}

type netipNet struct {
	ipnet net.IPNet
}

func newAuthenticator(config AuthConfig) (*authenticator, error) {
	auth := &authenticator{
		keyID:       strings.TrimSpace(config.KeyID),
		secret:      []byte(config.Secret),
		allowedSkew: config.AllowedSkew,
		allowNoAuth: config.AllowNoAuth,
		now:         config.Now,
	}
	if auth.allowedSkew == 0 {
		auth.allowedSkew = 60 * time.Second
	}
	if auth.now == nil {
		auth.now = time.Now
	}
	for _, value := range config.AllowedIPs {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		network, err := parseAllowedIP(value)
		if err != nil {
			return nil, err
		}
		auth.allowedNets = append(auth.allowedNets, netipNet{ipnet: network})
	}
	if len(auth.allowedNets) == 0 {
		return nil, fmt.Errorf("IP allowlist is empty; pass 0.0.0.0/0,::/0 explicitly to allow any client")
	}
	return auth, nil
}

func parseAllowedIP(value string) (net.IPNet, error) {
	if strings.Contains(value, "/") {
		_, network, err := net.ParseCIDR(value)
		if err != nil {
			return net.IPNet{}, fmt.Errorf("parse allow IP/CIDR %q: %w", value, err)
		}
		return *network, nil
	}
	ip := net.ParseIP(value)
	if ip == nil {
		return net.IPNet{}, fmt.Errorf("parse allow IP %q", value)
	}
	bits := 128
	if ip.To4() != nil {
		bits = 32
	}
	return net.IPNet{IP: ip, Mask: net.CIDRMask(bits, bits)}, nil
}

func (a *authenticator) authorize(r *http.Request, body []byte) error {
	if err := a.checkAllowlist(r); err != nil {
		return err
	}
	if len(a.secret) == 0 {
		if a.allowNoAuth {
			return nil
		}
		return httpError{status: http.StatusUnauthorized, message: "HMAC secret is not configured"}
	}
	keyID := r.Header.Get(headerKeyID)
	if !constantTimeStringEqual(keyID, a.keyID) {
		return httpError{status: http.StatusUnauthorized, message: "invalid key id"}
	}
	timestampRaw := r.Header.Get(headerTimestamp)
	timestamp, err := time.Parse(time.RFC3339, timestampRaw)
	if err != nil {
		return httpError{status: http.StatusUnauthorized, message: "invalid timestamp"}
	}
	delta := a.now().Sub(timestamp)
	if delta < 0 {
		delta = -delta
	}
	if delta > a.allowedSkew {
		return httpError{status: http.StatusUnauthorized, message: "timestamp outside allowed skew"}
	}

	expected := SignRequest(a.secret, r.Method, requestPath(r), timestampRaw, body)
	got := strings.TrimSpace(r.Header.Get(headerSignature))
	if !constantTimeStringEqual(got, expected) {
		return httpError{status: http.StatusUnauthorized, message: "invalid signature"}
	}
	return nil
}

func (a *authenticator) checkAllowlist(r *http.Request) error {
	if len(a.allowedNets) == 0 {
		return httpError{status: http.StatusForbidden, message: "IP allowlist is empty"}
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	ip := net.ParseIP(host)
	if ip == nil {
		return httpError{status: http.StatusForbidden, message: "invalid remote address"}
	}
	for _, allowed := range a.allowedNets {
		if allowed.ipnet.Contains(ip) {
			return nil
		}
	}
	return httpError{status: http.StatusForbidden, message: "remote address is not allowed"}
}

func SignRequest(secret []byte, method, path, timestamp string, body []byte) string {
	bodyHash := sha256.Sum256(body)
	payload := strings.Join([]string{
		method,
		path,
		timestamp,
		hex.EncodeToString(bodyHash[:]),
	}, "\n")
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(payload))
	return hex.EncodeToString(mac.Sum(nil))
}

func requestPath(r *http.Request) string {
	if r.URL.RawQuery == "" {
		return r.URL.EscapedPath()
	}
	return r.URL.EscapedPath() + "?" + r.URL.RawQuery
}

func constantTimeStringEqual(left, right string) bool {
	if len(left) != len(right) {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(left), []byte(right)) == 1
}
