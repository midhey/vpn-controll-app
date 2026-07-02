package agent

import (
	"context"
	"fmt"
	"strings"
	"testing"
	"time"

	"vpn-control-app/agent/internal/awg"
)

const testConfig = `[Interface]
PrivateKey = server-priv
Address = 10.8.1.0/24
ListenPort = 49351

[Peer]
PublicKey = admin-pub
PresharedKey = psk
AllowedIPs = 10.8.1.1/32
`

const testClientsTable = `[
    {
        "clientId": "admin-pub",
        "userData": {
            "clientName": "Admin"
        }
    }
]
`

// fakeDocker is an in-memory dockerAPI: files live in a map, SyncConf
// regenerates the runtime view from the current config unless told to fail
// or to leave the runtime stale.
type fakeDocker struct {
	files        map[string]string
	runtime      string
	syncFailures int
	restoreErr   error
	staleRuntime bool
	syncCalls    int
	removedFiles []string
}

func newFakeDocker() *fakeDocker {
	d := &fakeDocker{
		files: map[string]string{
			DefaultConfigPath:       testConfig,
			DefaultClientsTablePath: testClientsTable,
			DefaultServerPublicKey:  "server-pub\n",
			DefaultPresharedKey:     "psk\n",
		},
	}
	d.runtime = runtimeFromConfig(testConfig)
	return d
}

func runtimeFromConfig(configText string) string {
	cfg, err := awg.ParseConfig(configText)
	if err != nil {
		panic(err)
	}
	var b strings.Builder
	b.WriteString("interface: awg0\n  public key: server-pub\n  listening port: 49351\n")
	for _, peer := range cfg.Peers {
		fmt.Fprintf(&b, "\npeer: %s\n  allowed ips: %s\n", peer.PublicKey, strings.Join(peer.AllowedIPs, ", "))
	}
	return b.String()
}

func (d *fakeDocker) ContainerInfo(context.Context, string) (ContainerInfo, error) {
	return ContainerInfo{Running: true, Image: "test-image", Created: "2026-07-01"}, nil
}

func (d *fakeDocker) ReadFile(_ context.Context, _ string, filePath string) (string, error) {
	content, ok := d.files[filePath]
	if !ok {
		return "", fmt.Errorf("cat %s: no such file", filePath)
	}
	return content, nil
}

func (d *fakeDocker) ReadFileOrEmptyArray(_ context.Context, _ string, filePath string) (string, error) {
	content, ok := d.files[filePath]
	if !ok {
		return "[]\n", nil
	}
	return content, nil
}

func (d *fakeDocker) FileInfo(_ context.Context, _ string, filePath string) (FileInfo, error) {
	content, ok := d.files[filePath]
	if !ok {
		return FileInfo{}, nil
	}
	return FileInfo{Exists: true, Size: int64(len(content)), Mode: "600"}, nil
}

func (d *fakeDocker) WriteFileAtomic(_ context.Context, _ string, filePath string, data []byte, _ string) error {
	d.files[filePath] = string(data)
	return nil
}

func (d *fakeDocker) BackupFile(_ context.Context, _ string, filePath, backupPath string, required bool) error {
	content, ok := d.files[filePath]
	if !ok {
		if required {
			return fmt.Errorf("missing required file %s", filePath)
		}
		content = "[]\n"
	}
	d.files[backupPath] = content
	return nil
}

func (d *fakeDocker) RestoreFile(_ context.Context, _ string, backupPath, filePath, _ string) error {
	if d.restoreErr != nil {
		return d.restoreErr
	}
	content, ok := d.files[backupPath]
	if !ok {
		return fmt.Errorf("backup %s not found", backupPath)
	}
	d.files[filePath] = content
	return nil
}

func (d *fakeDocker) RemoveFile(_ context.Context, _ string, filePath string) error {
	delete(d.files, filePath)
	d.removedFiles = append(d.removedFiles, filePath)
	return nil
}

func (d *fakeDocker) SyncConf(_ context.Context, _ string, _, configPath string) error {
	d.syncCalls++
	if d.syncFailures > 0 {
		d.syncFailures--
		return fmt.Errorf("syncconf failed")
	}
	if !d.staleRuntime {
		d.runtime = runtimeFromConfig(d.files[configPath])
	}
	return nil
}

func (d *fakeDocker) AWGShow(context.Context, string, string) (string, error) {
	return d.runtime, nil
}

func (d *fakeDocker) GeneratePrivateKey(context.Context, string) (string, error) {
	return "generated-priv", nil
}

func (d *fakeDocker) PublicKey(context.Context, string, string) (string, error) {
	return "generated-pub", nil
}

func newTestService(docker *fakeDocker) *Service {
	service := newServiceWithDocker(Options{EndpointHost: "203.0.113.10"}, docker)
	service.now = func() time.Time { return time.Date(2026, 7, 1, 12, 0, 0, 0, time.UTC) }
	service.acquireLock = func(string) (*FileLock, error) { return &FileLock{}, nil }
	return service
}

func TestIssueHappyPath(t *testing.T) {
	docker := newFakeDocker()
	service := newTestService(docker)

	result, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err != nil {
		t.Fatal(err)
	}
	if result.PublicKey != "generated-pub" {
		t.Fatalf("public key = %q", result.PublicKey)
	}
	if result.ClientIP != "10.8.1.2" {
		t.Fatalf("client IP = %q", result.ClientIP)
	}
	if !strings.HasPrefix(result.VPNURL, "vpn://") {
		t.Fatalf("vpn url = %q", result.VPNURL)
	}
	if !strings.Contains(result.Config, "PrivateKey = generated-priv") {
		t.Fatalf("client config missing private key:\n%s", result.Config)
	}
	if !strings.Contains(docker.files[DefaultConfigPath], "generated-pub") {
		t.Fatal("server config does not contain new peer")
	}
	if !strings.Contains(docker.files[DefaultClientsTablePath], "Phone") {
		t.Fatal("clientsTable does not contain new client")
	}
	if docker.syncCalls != 1 {
		t.Fatalf("sync calls = %d, want 1", docker.syncCalls)
	}
}

func TestIssueSkipsRuntimeOnlyIPs(t *testing.T) {
	docker := newFakeDocker()
	// A peer known to runtime but absent from the config file occupies 10.8.1.2.
	docker.runtime += "\npeer: ghost-pub\n  allowed ips: 10.8.1.2/32\n"
	service := newTestService(docker)

	result, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err != nil {
		t.Fatal(err)
	}
	if result.ClientIP != "10.8.1.3" {
		t.Fatalf("client IP = %q, want 10.8.1.3", result.ClientIP)
	}
}

func TestIssueRollbackOnSyncError(t *testing.T) {
	docker := newFakeDocker()
	docker.syncFailures = 1
	service := newTestService(docker)

	_, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err == nil {
		t.Fatal("Issue succeeded, want sync error")
	}
	if !strings.Contains(err.Error(), "rollback completed") {
		t.Fatalf("error = %q, want rollback completed", err)
	}
	if strings.Contains(docker.files[DefaultConfigPath], "generated-pub") {
		t.Fatal("config still contains new peer after rollback")
	}
	if strings.Contains(docker.files[DefaultClientsTablePath], "Phone") {
		t.Fatal("clientsTable still contains new client after rollback")
	}
}

func TestIssueRollbackOnVerifyFailure(t *testing.T) {
	docker := newFakeDocker()
	docker.staleRuntime = true
	service := newTestService(docker)

	_, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err == nil {
		t.Fatal("Issue succeeded, want verify error")
	}
	if !strings.Contains(err.Error(), "not found in runtime after sync") {
		t.Fatalf("error = %q", err)
	}
	if !strings.Contains(err.Error(), "rollback completed") {
		t.Fatalf("error = %q, want rollback completed", err)
	}
	if strings.Contains(docker.files[DefaultConfigPath], "generated-pub") {
		t.Fatal("config still contains new peer after rollback")
	}
}

func TestIssueRollbackFailureIsReported(t *testing.T) {
	docker := newFakeDocker()
	docker.syncFailures = 1
	docker.restoreErr = fmt.Errorf("restore broken")
	service := newTestService(docker)

	_, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err == nil {
		t.Fatal("Issue succeeded, want error")
	}
	if !strings.Contains(err.Error(), "rollback failed") {
		t.Fatalf("error = %q, want rollback failed", err)
	}
}

func TestIssueRollbackRemovesCreatedClientsTable(t *testing.T) {
	docker := newFakeDocker()
	delete(docker.files, DefaultClientsTablePath)
	docker.syncFailures = 1
	service := newTestService(docker)

	_, err := service.Issue(context.Background(), IssueRequest{Name: "Phone"})
	if err == nil {
		t.Fatal("Issue succeeded, want sync error")
	}
	if _, exists := docker.files[DefaultClientsTablePath]; exists {
		t.Fatal("clientsTable exists after rollback, want it removed")
	}
}

func TestRevokeHappyPath(t *testing.T) {
	docker := newFakeDocker()
	service := newTestService(docker)

	result, err := service.Revoke(context.Background(), "admin-pub")
	if err != nil {
		t.Fatal(err)
	}
	if !result.Revoked {
		t.Fatal("revoked = false")
	}
	if strings.Contains(docker.files[DefaultConfigPath], "admin-pub") {
		t.Fatal("config still contains revoked peer")
	}
	if strings.Contains(docker.files[DefaultClientsTablePath], "admin-pub") {
		t.Fatal("clientsTable still contains revoked client")
	}
}

func TestRevokeRollbackWhenPeerStillPresent(t *testing.T) {
	docker := newFakeDocker()
	docker.staleRuntime = true
	service := newTestService(docker)

	_, err := service.Revoke(context.Background(), "admin-pub")
	if err == nil {
		t.Fatal("Revoke succeeded, want verify error")
	}
	if !strings.Contains(err.Error(), "still present in runtime after sync") {
		t.Fatalf("error = %q", err)
	}
	if !strings.Contains(docker.files[DefaultConfigPath], "admin-pub") {
		t.Fatal("config lost peer after rollback")
	}
}

func TestInspectReportsMissingConfig(t *testing.T) {
	docker := newFakeDocker()
	delete(docker.files, DefaultConfigPath)
	service := newTestService(docker)

	result, err := service.Inspect(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if result.ConfigExists {
		t.Fatal("config_exists = true, want false")
	}
	if result.PeerCountConfig != 0 {
		t.Fatalf("peer_count_config = %d, want 0", result.PeerCountConfig)
	}
	found := false
	for _, warning := range result.Warnings {
		if strings.Contains(warning, "missing") {
			found = true
		}
	}
	if !found {
		t.Fatalf("warnings = %#v, want missing-config warning", result.Warnings)
	}
}
