//go:build windows

package agent

import "fmt"

// The agent targets Linux hosts; this stub only exists so the package
// builds and tests run on Windows development machines.

type FileLock struct{}

func AcquireLock(path string) (*FileLock, error) {
	return nil, fmt.Errorf("file locking is not supported on windows")
}

func (l *FileLock) Release() error {
	return nil
}
