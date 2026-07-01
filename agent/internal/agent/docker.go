package agent

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"path"
	"strconv"
	"strings"
	"time"
)

type DockerClient struct {
	Timeout time.Duration
}

type ContainerInfo struct {
	Running bool
	Image   string
	Created string
}

type FileInfo struct {
	Exists bool
	Size   int64
	Mode   string
}

func NewDockerClient() DockerClient {
	return DockerClient{Timeout: 30 * time.Second}
}

func (d DockerClient) ContainerInfo(ctx context.Context, container string) (ContainerInfo, error) {
	out, err := d.Docker(ctx, "inspect", container, "--format", "{{.State.Running}}\n{{.Config.Image}}\n{{.Created}}")
	if err != nil {
		return ContainerInfo{}, err
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	if len(lines) < 3 {
		return ContainerInfo{}, fmt.Errorf("unexpected docker inspect output for %s", container)
	}
	return ContainerInfo{
		Running: strings.TrimSpace(lines[0]) == "true",
		Image:   strings.TrimSpace(lines[1]),
		Created: strings.TrimSpace(lines[2]),
	}, nil
}

func (d DockerClient) ReadFile(ctx context.Context, container, filePath string) (string, error) {
	return d.Exec(ctx, container, "cat", filePath)
}

func (d DockerClient) ReadFileOrEmptyArray(ctx context.Context, container, filePath string) (string, error) {
	return d.Shell(ctx, container, "if test -f "+shellQuote(filePath)+"; then cat "+shellQuote(filePath)+"; else printf '[]\\n'; fi")
}

func (d DockerClient) FileInfo(ctx context.Context, container, filePath string) (FileInfo, error) {
	out, err := d.Shell(ctx, container, "if test -e "+shellQuote(filePath)+"; then stat -c '%s %a' "+shellQuote(filePath)+"; else echo missing; fi")
	if err != nil {
		return FileInfo{}, err
	}
	out = strings.TrimSpace(out)
	if out == "missing" {
		return FileInfo{}, nil
	}
	parts := strings.Fields(out)
	if len(parts) != 2 {
		return FileInfo{}, fmt.Errorf("unexpected stat output for %s: %q", filePath, out)
	}
	size, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		return FileInfo{}, fmt.Errorf("parse stat size for %s: %w", filePath, err)
	}
	return FileInfo{Exists: true, Size: size, Mode: parts[1]}, nil
}

func (d DockerClient) WriteFileAtomic(ctx context.Context, container, filePath string, data []byte, mode string) error {
	dir := path.Dir(filePath)
	base := path.Base(filePath)
	tmp := path.Join(dir, fmt.Sprintf(".%s.tmp.%d", base, time.Now().UnixNano()))
	if _, err := d.ExecInput(ctx, container, string(data), "sh", "-lc", "cat > "+shellQuote(tmp)); err != nil {
		return err
	}
	script := strings.Join([]string{
		"chmod " + shellQuote(mode) + " " + shellQuote(tmp),
		"mv -f " + shellQuote(tmp) + " " + shellQuote(filePath),
		"chmod " + shellQuote(mode) + " " + shellQuote(filePath),
		"sync",
	}, " && ")
	if _, err := d.Shell(ctx, container, script); err != nil {
		return err
	}
	return nil
}

func (d DockerClient) BackupFile(ctx context.Context, container, filePath, backupPath string, required bool) error {
	script := "if test -f " + shellQuote(filePath) + "; then cp -p " + shellQuote(filePath) + " " + shellQuote(backupPath) + "; "
	if required {
		script += "else echo missing required file " + shellQuote(filePath) + " >&2; exit 1; fi"
	} else {
		script += "else printf '[]\\n' > " + shellQuote(backupPath) + "; fi"
	}
	_, err := d.Shell(ctx, container, script)
	return err
}

func (d DockerClient) RestoreFile(ctx context.Context, container, backupPath, filePath, mode string) error {
	script := strings.Join([]string{
		"cp -p " + shellQuote(backupPath) + " " + shellQuote(filePath),
		"chmod " + shellQuote(mode) + " " + shellQuote(filePath),
		"sync",
	}, " && ")
	_, err := d.Shell(ctx, container, script)
	return err
}

func (d DockerClient) SyncConf(ctx context.Context, container, iface, configPath string) error {
	script := "awg syncconf " + shellQuote(iface) + " <(awg-quick strip " + shellQuote(configPath) + ")"
	_, err := d.Exec(ctx, container, "bash", "-lc", script)
	return err
}

func (d DockerClient) AWGShow(ctx context.Context, container, iface string) (string, error) {
	return d.Exec(ctx, container, "awg", "show", iface)
}

func (d DockerClient) GeneratePrivateKey(ctx context.Context, container string) (string, error) {
	out, err := d.Exec(ctx, container, "awg", "genkey")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(out), nil
}

func (d DockerClient) PublicKey(ctx context.Context, container, privateKey string) (string, error) {
	out, err := d.ExecInput(ctx, container, privateKey+"\n", "awg", "pubkey")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(out), nil
}

func (d DockerClient) Docker(ctx context.Context, args ...string) (string, error) {
	return d.run(ctx, "", append([]string{}, args...)...)
}

func (d DockerClient) Exec(ctx context.Context, container string, args ...string) (string, error) {
	all := append([]string{"exec", container}, args...)
	return d.run(ctx, "", all...)
}

func (d DockerClient) ExecInput(ctx context.Context, container, input string, args ...string) (string, error) {
	all := append([]string{"exec", "-i", container}, args...)
	return d.run(ctx, input, all...)
}

func (d DockerClient) Shell(ctx context.Context, container, script string) (string, error) {
	return d.Exec(ctx, container, "sh", "-lc", script)
}

func (d DockerClient) run(ctx context.Context, input string, args ...string) (string, error) {
	timeout := d.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	var cancel context.CancelFunc
	ctx, cancel = context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "docker", args...)
	if input != "" {
		cmd.Stdin = strings.NewReader(input)
	}
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = strings.TrimSpace(stdout.String())
		}
		if msg == "" {
			msg = err.Error()
		}
		if ctx.Err() != nil {
			return "", fmt.Errorf("docker %s timed out: %w", strings.Join(args, " "), ctx.Err())
		}
		return "", fmt.Errorf("docker %s failed: %s", strings.Join(args, " "), msg)
	}
	return stdout.String(), nil
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", "'\\''") + "'"
}
