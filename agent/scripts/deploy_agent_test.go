package scripts

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

const testSecret = "agent-hmac-secret-for-test"

func TestDeployScriptProtectsServiceSecretAndSSHArguments(t *testing.T) {
	env := newDeployTestEnv(t)
	output, err := env.command().CombinedOutput()
	if err != nil {
		t.Fatalf("deploy failed: %v\n%s", err, output)
	}
	if strings.Contains(string(output), testSecret) {
		t.Fatal("HMAC secret leaked to deploy output")
	}

	envPath := filepath.Join(env.captureDir, "vpn-agent.env")
	info, err := os.Stat(envPath)
	if err != nil {
		t.Fatal(err)
	}
	if got := info.Mode().Perm(); got != 0o600 {
		t.Fatalf("local env mode = %o, want 600", got)
	}
	envContent := readFile(t, envPath)
	if !strings.Contains(envContent, "VPN_AGENT_SECRET=\""+testSecret+"\"") {
		t.Fatal("captured env does not contain the expected secret")
	}

	unit := readFile(t, filepath.Join(env.captureDir, "vpn-agent.service"))
	if strings.Contains(unit, testSecret) || strings.Contains(unit, "--hmac-secret") {
		t.Fatal("systemd unit exposes the HMAC secret")
	}
	if !strings.Contains(unit, "EnvironmentFile=/etc/vpn-agent/vpn-agent.env") {
		t.Fatal("systemd unit does not use the protected EnvironmentFile")
	}

	log := readFile(t, env.callLog)
	if !strings.Contains(log, "\t-l\troot\t--\t203.0.113.10\t") {
		t.Fatalf("ssh user/host are not safely separated:\n%s", log)
	}
	if !strings.Contains(log, "\t-o\tUser=root\t--\t") {
		t.Fatalf("scp user/source options are not safely separated:\n%s", log)
	}
	precreate := strings.Index(log, "chmod 0600 '/tmp/vpn-agent-deploy-")
	envCopy := strings.Index(log, "scp\t600\tvpn-agent.env")
	if precreate < 0 || envCopy < 0 || precreate > envCopy {
		t.Fatalf("remote env was not created with 0600 before SCP:\n%s", log)
	}
	if !strings.Contains(log, "install -m 0600") || !strings.Contains(log, "install -m 0644") {
		t.Fatalf("final systemd env/unit modes are not explicit:\n%s", log)
	}
	if !strings.Contains(log, "rm -rf --") || !strings.Contains(log, "vpn-agent-deploy-") {
		t.Fatalf("remote cleanup was not attempted:\n%s", log)
	}
	assertLocalTempsCleaned(t, env)
}

func TestDeployScriptPreflightConnectsWithoutUploading(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := exec.Command("/bin/bash", env.script,
		"--user", "root",
		"--host", "203.0.113.10",
		"--preflight-only",
	)
	cmd.Env = env.environmentWithoutSecret()
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("preflight failed: %v\n%s", err, output)
	}
	log := readFile(t, env.callLog)
	if strings.Contains(log, "scp\t") {
		t.Fatalf("preflight uploaded a file:\n%s", log)
	}
	if !strings.Contains(log, "command -v sh >/dev/null") {
		t.Fatalf("preflight did not perform a real SSH command:\n%s", log)
	}
}

func TestDeployScriptConsumesPasswordEnvironmentBeforeChildren(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := exec.Command("/bin/bash", env.script,
		"--user", "root",
		"--host", "203.0.113.10",
		"--password-env", "VPN_AGENT_DEPLOY_SSH_PASSWORD",
		"--preflight-only",
	)
	cmd.Env = append(env.environmentWithoutSecret(),
		"VPN_AGENT_DEPLOY_SSH_PASSWORD=temporary-password",
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("password preflight failed: %v\n%s", err, output)
	}
}

func TestDeployScriptDetectsAgentAllowlistFromSSHSource(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := env.command()
	cmd.Args = append(cmd.Args, "--allow-ip", "ssh-source")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("deploy failed: %v\n%s", err, output)
	}

	envContent := readFile(t, filepath.Join(env.captureDir, "vpn-agent.env"))
	if !strings.Contains(envContent, `VPN_AGENT_ALLOW_IPS="198.51.100.25"`) {
		t.Fatalf("automatic allowlist was not written:\n%s", envContent)
	}
}

func TestDeployScriptRejectsUnsafeUsernameBeforeSSH(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := exec.Command("/bin/bash", env.script,
		"--user", "-oProxyCommand=touch /tmp/pwned",
		"--host", "203.0.113.10",
		"--preflight-only",
	)
	cmd.Env = env.environment()
	if output, err := cmd.CombinedOutput(); err == nil {
		t.Fatalf("unsafe username was accepted:\n%s", output)
	}
	if _, err := os.Stat(env.callLog); !os.IsNotExist(err) {
		t.Fatalf("SSH was invoked for an unsafe username; stat error = %v", err)
	}
}

func TestDeployScriptCleansRemoteTempsAfterCopyError(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := env.command()
	cmd.Env = append(cmd.Env, "FAIL_SERVICE_COPY=1")
	if output, err := cmd.CombinedOutput(); err == nil {
		t.Fatalf("deploy unexpectedly succeeded:\n%s", output)
	}

	log := readFile(t, env.callLog)
	failurePoint := strings.Index(log, "scp\t600\tvpn-agent.service")
	cleanupPoint := strings.LastIndex(log, "rm -rf --")
	if failurePoint < 0 || cleanupPoint < failurePoint {
		t.Fatalf("remote temps were not cleaned after SCP error:\n%s", log)
	}
	assertLocalTempsCleaned(t, env)
}

func TestKeepArtifactNeverKeepsHMACEnvironment(t *testing.T) {
	env := newDeployTestEnv(t)
	cmd := env.command()
	cmd.Args = append(cmd.Args, "--keep-artifact")
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("deploy failed: %v\n%s", err, output)
	}

	for _, source := range strings.Fields(readFile(t, env.sourceLog)) {
		if filepath.Base(source) != "vpn-agent.env" {
			continue
		}
		if _, err := os.Stat(source); !os.IsNotExist(err) {
			t.Fatalf("--keep-artifact retained HMAC env: %s (stat error %v)", source, err)
		}
		_ = os.RemoveAll(filepath.Dir(source))
		return
	}
	t.Fatal("test did not observe a local HMAC env file")
}

func TestDeployScriptCleansRemoteTempsAfterSignal(t *testing.T) {
	env := newDeployTestEnv(t)
	marker := filepath.Join(env.root, "copy-started")
	cmd := env.command()
	cmd.Env = append(cmd.Env, "BLOCK_SERVICE_COPY=1", "BLOCK_MARKER="+marker)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(5 * time.Second)
	for {
		if _, err := os.Stat(marker); err == nil {
			break
		}
		if time.Now().After(deadline) {
			_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL)
			t.Fatal("deploy did not reach the interruptible SCP phase")
		}
		time.Sleep(10 * time.Millisecond)
	}
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGTERM); err != nil {
		t.Fatal(err)
	}
	_ = cmd.Wait()

	log := readFile(t, env.callLog)
	signalPoint := strings.Index(log, "scp\t600\tvpn-agent.service")
	cleanupPoint := strings.LastIndex(log, "rm -rf --")
	if signalPoint < 0 || cleanupPoint < signalPoint {
		t.Fatalf("remote temps were not cleaned after signal:\n%s", log)
	}
	assertLocalTempsCleaned(t, env)
}

type deployTestEnv struct {
	root       string
	fakeBin    string
	captureDir string
	callLog    string
	sourceLog  string
	binary     string
	script     string
}

func newDeployTestEnv(t *testing.T) deployTestEnv {
	t.Helper()
	root := t.TempDir()
	env := deployTestEnv{
		root:       root,
		fakeBin:    filepath.Join(root, "bin"),
		captureDir: filepath.Join(root, "capture"),
		callLog:    filepath.Join(root, "calls.log"),
		sourceLog:  filepath.Join(root, "sources.log"),
		binary:     filepath.Join(root, "vpn-agent"),
		script:     filepath.Join("deploy-agent.sh"),
	}
	for _, dir := range []string{env.fakeBin, env.captureDir} {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			t.Fatal(err)
		}
	}
	writeExecutable(t, env.binary, "#!/bin/sh\nexit 0\n")
	writeExecutable(t, filepath.Join(env.fakeBin, "ssh"), fakeSSH)
	writeExecutable(t, filepath.Join(env.fakeBin, "scp"), fakeSCP)
	return env
}

func (e deployTestEnv) command() *exec.Cmd {
	cmd := exec.Command("/bin/bash", e.script,
		"--user", "root",
		"--host", "203.0.113.10",
		"--binary", e.binary,
		"--install-service",
		"--hmac-key-id", "backend-test",
		"--hmac-secret-env", "VPN_AGENT_DEPLOY_HMAC_SECRET",
		"--allow-ip", "10.0.0.5/32",
		"--skip-inspect",
	)
	cmd.Env = e.environment()
	return cmd
}

func (e deployTestEnv) environment() []string {
	return append(e.environmentWithoutSecret(),
		"VPN_AGENT_DEPLOY_HMAC_SECRET="+testSecret,
	)
}

func (e deployTestEnv) environmentWithoutSecret() []string {
	return append(os.Environ(),
		"PATH="+e.fakeBin+":"+os.Getenv("PATH"),
		"CALL_LOG="+e.callLog,
		"SOURCE_LOG="+e.sourceLog,
		"CAPTURE_DIR="+e.captureDir,
	)
}

func writeExecutable(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o700); err != nil {
		t.Fatal(err)
	}
}

func readFile(t *testing.T, path string) string {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}

func assertLocalTempsCleaned(t *testing.T, env deployTestEnv) {
	t.Helper()
	for _, source := range strings.Fields(readFile(t, env.sourceLog)) {
		if source == env.binary {
			continue
		}
		if _, err := os.Stat(source); !os.IsNotExist(err) {
			t.Fatalf("local temporary file was not cleaned: %s (stat error %v)", source, err)
		}
	}
}

const fakeSSH = `#!/bin/bash
if [[ -n "${VPN_AGENT_DEPLOY_HMAC_SECRET+x}" ]]; then
  exit 43
fi
if [[ -n "${VPN_AGENT_DEPLOY_SSH_PASSWORD+x}" ]]; then
  exit 47
fi
if [[ -n "${VPN_AGENT_DEPLOY_ASKPASS_SECRET+x}" ]]; then
  [[ "${SSH_ASKPASS_REQUIRE:-}" == "force" ]] || exit 44
  [[ -x "${SSH_ASKPASS:-}" ]] || exit 45
  [[ "$("$SSH_ASKPASS")" == "$VPN_AGENT_DEPLOY_ASKPASS_SECRET" ]] || exit 46
fi
{
  printf 'ssh'
  for arg in "$@"; do printf '\t%s' "$arg"; done
  printf '\n'
} >> "$CALL_LOG"
if [[ "${*: -1}" == *SSH_CONNECTION* ]]; then
  printf '198.51.100.25 53000 203.0.113.10 22'
fi
exit 0
`

const fakeSCP = `#!/bin/bash
if [[ -n "${VPN_AGENT_DEPLOY_HMAC_SECRET+x}" ]]; then
  exit 43
fi
if [[ -n "${VPN_AGENT_DEPLOY_SSH_PASSWORD+x}" ]]; then
  exit 47
fi
if [[ -n "${VPN_AGENT_DEPLOY_ASKPASS_SECRET+x}" ]]; then
  [[ "${SSH_ASKPASS_REQUIRE:-}" == "force" ]] || exit 44
  [[ -x "${SSH_ASKPASS:-}" ]] || exit 45
  [[ "$("$SSH_ASKPASS")" == "$VPN_AGENT_DEPLOY_ASKPASS_SECRET" ]] || exit 46
fi
source_path=""
destination=""
after_options=0
for arg in "$@"; do
  if [[ "$after_options" == "1" && -z "$source_path" ]]; then
    source_path="$arg"
  elif [[ "$after_options" == "1" ]]; then
    destination="$arg"
  elif [[ "$arg" == "--" ]]; then
    after_options=1
  fi
done
printf '%s\n' "$source_path" >> "$SOURCE_LOG"
mode="$(stat -c '%a' "$source_path" 2>/dev/null || stat -f '%Lp' "$source_path")"
base="$(basename "$source_path")"
{
  printf 'scp\t%s\t%s' "$mode" "$base"
  for arg in "$@"; do printf '\t%s' "$arg"; done
  printf '\n'
} >> "$CALL_LOG"
cp -p "$source_path" "$CAPTURE_DIR/$base"
if [[ "$base" == "vpn-agent.env" && "$mode" != "600" ]]; then
  exit 41
fi
if [[ "$base" == "vpn-agent.service" && "${FAIL_SERVICE_COPY:-0}" == "1" ]]; then
  exit 42
fi
if [[ "$base" == "vpn-agent.service" && "${BLOCK_SERVICE_COPY:-0}" == "1" ]]; then
  printf started > "$BLOCK_MARKER"
  trap 'exit 143' TERM INT
  while :; do sleep 1; done
fi
exit 0
`
