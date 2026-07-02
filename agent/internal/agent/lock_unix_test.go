//go:build unix

package agent

import (
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestAcquireLockTimesOutWhenHeld(t *testing.T) {
	origTimeout, origInterval := lockAcquireTimeout, lockRetryInterval
	lockAcquireTimeout = 200 * time.Millisecond
	lockRetryInterval = 20 * time.Millisecond
	t.Cleanup(func() {
		lockAcquireTimeout, lockRetryInterval = origTimeout, origInterval
	})

	path := filepath.Join(t.TempDir(), "vpn-agent.lock")
	first, err := AcquireLock(path)
	if err != nil {
		t.Fatal(err)
	}
	defer first.Release()

	_, err = AcquireLock(path)
	if err == nil {
		t.Fatal("second AcquireLock succeeded, want timeout error")
	}
	if !strings.Contains(err.Error(), "held by another process") {
		t.Fatalf("error = %q, want lock-held message", err)
	}
}

func TestAcquireLockAfterRelease(t *testing.T) {
	path := filepath.Join(t.TempDir(), "vpn-agent.lock")
	first, err := AcquireLock(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := first.Release(); err != nil {
		t.Fatal(err)
	}
	second, err := AcquireLock(path)
	if err != nil {
		t.Fatalf("acquire after release: %v", err)
	}
	if err := second.Release(); err != nil {
		t.Fatal(err)
	}
}
