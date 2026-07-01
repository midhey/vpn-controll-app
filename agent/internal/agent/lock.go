package agent

import (
	"os"
	"syscall"
)

type FileLock struct {
	file *os.File
}

func AcquireLock(path string) (*FileLock, error) {
	file, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(file.Fd()), syscall.LOCK_EX); err != nil {
		_ = file.Close()
		return nil, err
	}
	return &FileLock{file: file}, nil
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
