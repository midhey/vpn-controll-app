package cli

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"

	"vpn-control-app/agent/internal/agent"
	"vpn-control-app/agent/internal/httpapi"
)

type commonFlags struct {
	opts agent.Options
	json bool
}

func Run(args []string, stdout io.Writer, stderr io.Writer) int {
	if len(args) == 0 {
		printUsage(stderr)
		return 2
	}

	command := args[0]
	switch command {
	case "inspect":
		return runInspect(args[1:], stdout, stderr)
	case "peers":
		return runPeers(args[1:], stdout, stderr)
	case "issue":
		return runIssue(args[1:], stdout, stderr)
	case "revoke":
		return runRevoke(args[1:], stdout, stderr)
	case "serve":
		return runServe(args[1:], stdout, stderr)
	case "-h", "--help", "help":
		printUsage(stdout)
		return 0
	default:
		fmt.Fprintf(stderr, "unknown command %q\n\n", command)
		printUsage(stderr)
		return 2
	}
}

func runInspect(args []string, stdout io.Writer, stderr io.Writer) int {
	fs, common := newFlagSet("inspect", stderr)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	result, err := agent.NewService(common.opts).Inspect(context.Background())
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return printResult(stdout, stderr, common.json, result, printInspect)
}

func runPeers(args []string, stdout io.Writer, stderr io.Writer) int {
	fs, common := newFlagSet("peers", stderr)
	if err := fs.Parse(args); err != nil {
		return 2
	}
	result, err := agent.NewService(common.opts).Peers(context.Background())
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return printResult(stdout, stderr, common.json, result, printPeers)
}

func runIssue(args []string, stdout io.Writer, stderr io.Writer) int {
	fs, common := newFlagSet("issue", stderr)
	name := fs.String("name", "", "client display name")
	dnsRaw := fs.String("dns", "1.1.1.1,8.8.8.8", "comma-separated DNS servers")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	result, err := agent.NewService(common.opts).Issue(context.Background(), agent.IssueRequest{
		Name: *name,
		DNS:  splitCSV(*dnsRaw),
	})
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return printResult(stdout, stderr, common.json, result, printIssue)
}

func runRevoke(args []string, stdout io.Writer, stderr io.Writer) int {
	fs, common := newFlagSet("revoke", stderr)
	publicKey := fs.String("public-key", "", "peer public key to revoke")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	result, err := agent.NewService(common.opts).Revoke(context.Background(), *publicKey)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return printResult(stdout, stderr, common.json, result, printRevoke)
}

func runServe(args []string, stdout io.Writer, stderr io.Writer) int {
	fs, common := newFlagSet("serve", stderr)
	listen := fs.String("listen", envOrDefault("VPN_AGENT_LISTEN", "127.0.0.1:8090"), "HTTP listen address")
	keyID := fs.String("hmac-key-id", os.Getenv("VPN_AGENT_KEY_ID"), "HMAC key id")
	secret := fs.String("hmac-secret", os.Getenv("VPN_AGENT_SECRET"), "HMAC secret")
	allowIPs := fs.String("allow-ip", envOrDefault("VPN_AGENT_ALLOW_IPS", "127.0.0.1,::1"), "comma-separated allowed client IPs/CIDRs")
	allowNoAuth := fs.Bool("allow-no-auth", false, "allow unsigned requests when no HMAC secret is configured")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	service := agent.NewService(common.opts)
	server, err := httpapi.NewServer(service, httpapi.Config{
		Auth: httpapi.AuthConfig{
			KeyID:       *keyID,
			Secret:      *secret,
			AllowedIPs:  splitCSV(*allowIPs),
			AllowNoAuth: *allowNoAuth,
		},
	})
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	fmt.Fprintf(stdout, "vpn-agent listening on %s\n", *listen)
	if *secret == "" && !*allowNoAuth {
		fmt.Fprintln(stdout, "HMAC secret is not configured; authenticated endpoints will reject requests")
	}
	if err := httpapi.ListenAndServe(context.Background(), *listen, server.Handler()); err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func newFlagSet(name string, output io.Writer) (*flag.FlagSet, *commonFlags) {
	common := &commonFlags{opts: agent.DefaultOptions()}
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(output)
	fs.StringVar(&common.opts.Container, "container", common.opts.Container, "AWG Docker container")
	fs.StringVar(&common.opts.Interface, "interface", common.opts.Interface, "AWG interface")
	fs.StringVar(&common.opts.ConfigPath, "config-path", common.opts.ConfigPath, "AWG config path inside container")
	fs.StringVar(&common.opts.ClientsTablePath, "clients-table-path", common.opts.ClientsTablePath, "clientsTable path inside container")
	fs.StringVar(&common.opts.LockPath, "lock-path", common.opts.LockPath, "host lock file")
	fs.StringVar(&common.opts.EndpointHost, "endpoint-host", "", "public endpoint host for generated client configs")
	fs.BoolVar(&common.json, "json", false, "print JSON")
	return fs, common
}

func printResult[T any](stdout io.Writer, stderr io.Writer, asJSON bool, result T, human func(io.Writer, T)) int {
	if asJSON {
		data, err := json.MarshalIndent(result, "", "  ")
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 1
		}
		fmt.Fprintln(stdout, string(data))
		return 0
	}
	human(stdout, result)
	return 0
}

func printInspect(w io.Writer, result agent.InspectResult) {
	fmt.Fprintf(w, "container: %s\n", result.Container)
	fmt.Fprintf(w, "container running: %t\n", result.ContainerRunning)
	fmt.Fprintf(w, "container image: %s\n", result.ContainerImage)
	fmt.Fprintf(w, "runtime interface: %s\n", result.RuntimeInterface)
	fmt.Fprintf(w, "listen port: %s\n", result.ListenPort)
	fmt.Fprintf(w, "config: %s mode=%s size=%d\n", result.ConfigPath, result.ConfigMode, result.ConfigSize)
	fmt.Fprintf(w, "clientsTable: %s mode=%s\n", result.ClientsTablePath, result.ClientsTableMode)
	fmt.Fprintf(w, "peers: config=%d runtime=%d\n", result.PeerCountConfig, result.PeerCountRuntime)
	for _, warning := range result.Warnings {
		fmt.Fprintf(w, "warning: %s\n", warning)
	}
}

func printPeers(w io.Writer, peers []agent.PeerView) {
	if len(peers) == 0 {
		fmt.Fprintln(w, "no peers")
		return
	}
	for _, peer := range peers {
		name := peer.Name
		if name == "" {
			name = "-"
		}
		allowed := firstNonEmpty(strings.Join(peer.AllowedIPsConfig, ","), strings.Join(peer.AllowedIPsRuntime, ","))
		fmt.Fprintf(w, "%s name=%q allowed=%s config=%t runtime=%t clientsTable=%t", peer.PublicKey, name, allowed, peer.InConfig, peer.InRuntime, peer.InClientsTable)
		if peer.Endpoint != "" {
			fmt.Fprintf(w, " endpoint=%s", peer.Endpoint)
		}
		if peer.LatestHandshake != "" {
			fmt.Fprintf(w, " handshake=%q", peer.LatestHandshake)
		}
		fmt.Fprintln(w)
	}
}

func printIssue(w io.Writer, result agent.IssueResult) {
	fmt.Fprintf(w, "public_key: %s\n", result.PublicKey)
	fmt.Fprintf(w, "client_ip: %s\n", result.ClientIP)
	if result.VPNURL != "" {
		fmt.Fprintf(w, "vpn_url: %s\n", result.VPNURL)
	}
	fmt.Fprintln(w, "config:")
	fmt.Fprintln(w, result.Config)
}

func printRevoke(w io.Writer, result agent.RevokeResult) {
	fmt.Fprintf(w, "revoked: %t\n", result.Revoked)
	fmt.Fprintf(w, "public_key: %s\n", result.PublicKey)
}

func splitCSV(value string) []string {
	parts := strings.Split(value, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func printUsage(w io.Writer) {
	fmt.Fprintln(w, "usage: vpn-agent <command> [flags]")
	fmt.Fprintln(w)
	fmt.Fprintln(w, "commands:")
	fmt.Fprintln(w, "  inspect")
	fmt.Fprintln(w, "  peers")
	fmt.Fprintln(w, "  issue --name NAME --endpoint-host HOST")
	fmt.Fprintln(w, "  revoke --public-key KEY")
	fmt.Fprintln(w, "  serve --hmac-key-id KEY_ID --hmac-secret SECRET")
}

func envOrDefault(name, fallback string) string {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return fallback
	}
	return value
}
