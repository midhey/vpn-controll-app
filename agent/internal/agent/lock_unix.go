//go:build unix

package agent

import (
	"fmt"
	"os"
	"syscall"
	"time"
)

// lockAcquireTimeout bounds how long AcquireLock waits for a busy lock so a
// stuck holder cannot block mutating operations forever. Overridable in tests.
var (
	lockAcquireTimeout = 10 * time.Second
	lockRetryInterval  = 100 * time.Millisecond
)

type FileLock struct {
	file *os.File
}

func AcquireLock(path string) (*FileLock, error) {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	deadline := time.Now().Add(lockAcquireTimeout)
	for {
		err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			return &FileLock{file: file}, nil
		}
		if err != syscall.EWOULDBLOCK && err != syscall.EAGAIN {
			_ = file.Close()
			return nil, err
		}
		if time.Now().After(deadline) {
			_ = file.Close()
			return nil, fmt.Errorf("lock %s is held by another process", path)
		}
		time.Sleep(lockRetryInterval)
	}
}

func (l *FileLock) Release() error {
	if l == nil || l.file == nil {
		return nil
	}
	errUnlock := syscall.Flock(int(l.file.Fd()), syscall.LOCK_UN)
	errClose := l.file.Close()
	l.file = nil
	if errUnlock != nil {
		return errUnlock
	}
	return errClose
}
