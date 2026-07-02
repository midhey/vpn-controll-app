package agent

import (
	"context"
	"fmt"
	"net/netip"
	"os"
	"path"
	"sort"
	"strings"
	"time"

	"vpn-control-app/agent/internal/awg"
)

const (
	DefaultContainer        = "amnezia-awg2"
	DefaultInterface        = "awg0"
	DefaultConfigPath       = "/opt/amnezia/awg/awg0.conf"
	DefaultClientsTablePath = "/opt/amnezia/awg/clientsTable"
	DefaultLockPath         = "/var/lock/vpn-agent.lock"
	DefaultServerPublicKey  = "/opt/amnezia/awg/wireguard_server_public_key.key"
	DefaultPresharedKey     = "/opt/amnezia/awg/wireguard_psk.key"
)

type Options struct {
	Container        string
	Interface        string
	ConfigPath       string
	ClientsTablePath string
	LockPath         string
	EndpointHost     string
}

func DefaultOptions() Options {
	return Options{
		Container:        DefaultContainer,
		Interface:        DefaultInterface,
		ConfigPath:       DefaultConfigPath,
		ClientsTablePath: DefaultClientsTablePath,
		LockPath:         DefaultLockPath,
	}
}

func (o Options) withDefaults() Options {
	defaults := DefaultOptions()
	if o.Container == "" {
		o.Container = defaults.Container
	}
	if o.Interface == "" {
		o.Interface = defaults.Interface
	}
	if o.ConfigPath == "" {
		o.ConfigPath = defaults.ConfigPath
	}
	if o.ClientsTablePath == "" {
		o.ClientsTablePath = defaults.ClientsTablePath
	}
	if o.LockPath == "" {
		o.LockPath = defaults.LockPath
	}
	return o
}

type Service struct {
	opts   Options
	docker DockerClient
	now    func() time.Time
}

func NewService(opts Options) *Service {
	return &Service{
		opts:   opts.withDefaults(),
		docker: NewDockerClient(),
		now:    time.Now,
	}
}

type InspectResult struct {
	Container        string   `json:"container"`
	ContainerRunning bool     `json:"container_running"`
	ContainerImage   string   `json:"container_image"`
	ContainerCreated string   `json:"container_created"`
	Interface        string   `json:"interface"`
	RuntimeInterface string   `json:"runtime_interface"`
	RuntimePublicKey string   `json:"runtime_public_key"`
	ListenPort       string   `json:"listen_port"`
	ConfigPath       string   `json:"config_path"`
	ConfigExists     bool     `json:"config_exists"`
	ConfigMode       string   `json:"config_mode,omitempty"`
	ConfigSize       int64    `json:"config_size,omitempty"`
	ClientsTablePath string   `json:"clients_table_path"`
	ClientsTableMode string   `json:"clients_table_mode,omitempty"`
	PeerCountConfig  int      `json:"peer_count_config"`
	PeerCountRuntime int      `json:"peer_count_runtime"`
	Warnings         []string `json:"warnings,omitempty"`
}

type PeerView struct {
	PublicKey         string         `json:"public_key"`
	Name              string         `json:"name,omitempty"`
	AllowedIPsConfig  []string       `json:"allowed_ips_config,omitempty"`
	AllowedIPsRuntime []string       `json:"allowed_ips_runtime,omitempty"`
	InConfig          bool           `json:"in_config"`
	InRuntime         bool           `json:"in_runtime"`
	InClientsTable    bool           `json:"in_clients_table"`
	Endpoint          string         `json:"endpoint,omitempty"`
	LatestHandshake   string         `json:"latest_handshake,omitempty"`
	TransferReceived  string         `json:"transfer_received,omitempty"`
	TransferSent      string         `json:"transfer_sent,omitempty"`
	UserData          map[string]any `json:"user_data,omitempty"`
}

type IssueRequest struct {
	Name         string
	DNS          []string
	EndpointHost string
}

type IssueResult struct {
	PublicKey string `json:"public_key"`
	ClientIP  string `json:"client_ip"`
	Config    string `json:"config"`
	VPNURL    string `json:"vpn_url"`
}

type RevokeResult struct {
	Revoked   bool   `json:"revoked"`
	PublicKey string `json:"public_key"`
}

func (s *Service) Inspect(ctx context.Context) (InspectResult, error) {
	info, err := s.docker.ContainerInfo(ctx, s.opts.Container)
	if err != nil {
		return InspectResult{}, err
	}
	configInfo, err := s.docker.FileInfo(ctx, s.opts.Container, s.opts.ConfigPath)
	if err != nil {
		return InspectResult{}, err
	}
	clientsInfo, err := s.docker.FileInfo(ctx, s.opts.Container, s.opts.ClientsTablePath)
	if err != nil {
		return InspectResult{}, err
	}
	configText, err := s.docker.ReadFile(ctx, s.opts.Container, s.opts.ConfigPath)
	if err != nil {
		return InspectResult{}, err
	}
	cfg, err := awg.ParseConfig(configText)
	if err != nil {
		return InspectResult{}, err
	}
	runtimeText, err := s.docker.AWGShow(ctx, s.opts.Container, s.opts.Interface)
	if err != nil {
		return InspectResult{}, err
	}
	runtime := awg.ParseAWGShow(runtimeText)

	warnings := []string{}
	if configInfo.Mode != "" && configInfo.Mode != "600" {
		warnings = append(warnings, fmt.Sprintf("config mode is %s, expected 600", configInfo.Mode))
	}
	if clientsInfo.Exists && clientsInfo.Mode != "600" {
		warnings = append(warnings, fmt.Sprintf("clientsTable mode is %s, expected 600", clientsInfo.Mode))
	}
	if runtime.InterfaceName != "" && runtime.InterfaceName != s.opts.Interface {
		warnings = append(warnings, fmt.Sprintf("runtime interface is %s, expected %s", runtime.InterfaceName, s.opts.Interface))
	}

	return InspectResult{
		Container:        s.opts.Container,
		ContainerRunning: info.Running,
		ContainerImage:   info.Image,
		ContainerCreated: info.Created,
		Interface:        s.opts.Interface,
		RuntimeInterface: runtime.InterfaceName,
		RuntimePublicKey: runtime.PublicKey,
		ListenPort:       firstNonEmpty(runtime.ListenPort, cfg.ListenPort()),
		ConfigPath:       s.opts.ConfigPath,
		ConfigExists:     configInfo.Exists,
		ConfigMode:       configInfo.Mode,
		ConfigSize:       configInfo.Size,
		ClientsTablePath: s.opts.ClientsTablePath,
		ClientsTableMode: clientsInfo.Mode,
		PeerCountConfig:  len(cfg.Peers),
		PeerCountRuntime: len(runtime.Peers),
		Warnings:         warnings,
	}, nil
}

func (s *Service) Peers(ctx context.Context) ([]PeerView, error) {
	cfg, table, runtime, err := s.readState(ctx)
	if err != nil {
		return nil, err
	}
	return mergePeers(cfg, table, runtime), nil
}

func (s *Service) Issue(ctx context.Context, req IssueRequest) (IssueResult, error) {
	if strings.TrimSpace(req.Name) == "" {
		return IssueResult{}, fmt.Errorf("name is required")
	}
	endpointHost := firstNonEmpty(req.EndpointHost, s.opts.EndpointHost, os.Getenv("VPN_AGENT_ENDPOINT_HOST"))
	if endpointHost == "" {
		return IssueResult{}, fmt.Errorf("endpoint host is required; pass --endpoint-host or set VPN_AGENT_ENDPOINT_HOST")
	}

	lock, err := AcquireLock(s.opts.LockPath)
	if err != nil {
		return IssueResult{}, fmt.Errorf("acquire lock %s: %w", s.opts.LockPath, err)
	}
	defer lock.Release()

	cfg, table, runtime, err := s.readState(ctx)
	if err != nil {
		return IssueResult{}, err
	}
	if err := cfg.Validate(); err != nil {
		return IssueResult{}, err
	}

	privateKey, err := s.docker.GeneratePrivateKey(ctx, s.opts.Container)
	if err != nil {
		return IssueResult{}, err
	}
	publicKey, err := s.docker.PublicKey(ctx, s.opts.Container, privateKey)
	if err != nil {
		return IssueResult{}, err
	}
	if _, exists := cfg.FindPeer(publicKey); exists {
		return IssueResult{}, fmt.Errorf("generated duplicate public key %q", publicKey)
	}

	// Reserve IPs seen only in runtime as well: a peer present in `awg show`
	// but missing from the config file must not have its address reissued.
	runtimeUsed := []string{}
	for _, peer := range runtime.Peers {
		runtimeUsed = append(runtimeUsed, peer.AllowedIPs...)
	}
	clientIP, err := awg.AllocateFreeIPv4(cfg, runtimeUsed...)
	if err != nil {
		return IssueResult{}, err
	}
	allowedIP := clientIP.String() + "/32"
	serverPublicKeyPath, pskPath := keyPathsForConfig(s.opts.ConfigPath)
	serverPublicKey, err := s.readTrimmed(ctx, serverPublicKeyPath)
	if err != nil {
		return IssueResult{}, err
	}
	psk, err := s.readTrimmed(ctx, pskPath)
	if err != nil {
		return IssueResult{}, err
	}

	cfg.AddPeer(awg.Peer{
		PublicKey:    publicKey,
		PresharedKey: psk,
		AllowedIPs:   []string{allowedIP},
	})
	if err := cfg.Validate(); err != nil {
		return IssueResult{}, err
	}
	table.AddOrUpdate(publicKey, req.Name, allowedIP, s.now())
	clientConfig, err := awg.RenderClientConfig(cfg, awg.ClientConfigParams{
		ClientPrivateKey: privateKey,
		ClientIP:         clientIP,
		ServerPublicKey:  serverPublicKey,
		PresharedKey:     psk,
		EndpointHost:     endpointHost,
		DNS:              req.DNS,
	})
	if err != nil {
		return IssueResult{}, err
	}
	vpnURL, err := awg.RenderAmneziaShareURI(cfg, awg.ShareURIParams{
		EndpointHost:        endpointHost,
		DNS:                 req.DNS,
		NativeConfig:        clientConfig,
		ClientPrivateKey:    privateKey,
		ClientPublicKey:     publicKey,
		ClientIP:            clientIP,
		ServerPublicKey:     serverPublicKey,
		PresharedKey:        psk,
		AllowedIPs:          []string{"0.0.0.0/0", "::/0"},
		PersistentKeepalive: "25",
		MTU:                 "1376",
		Description:         req.Name,
	})
	if err != nil {
		return IssueResult{}, err
	}

	backups, err := s.backup(ctx)
	if err != nil {
		return IssueResult{}, err
	}
	if err := s.writeState(ctx, cfg, table); err != nil {
		return IssueResult{}, s.rollback(ctx, backups, err)
	}
	if err := s.docker.SyncConf(ctx, s.opts.Container, s.opts.Interface, s.opts.ConfigPath); err != nil {
		return IssueResult{}, s.rollback(ctx, backups, err)
	}
	runtimeText, err := s.docker.AWGShow(ctx, s.opts.Container, s.opts.Interface)
	if err != nil {
		return IssueResult{}, s.rollback(ctx, backups, err)
	}
	if !awg.ParseAWGShow(runtimeText).HasPeer(publicKey) {
		return IssueResult{}, s.rollback(ctx, backups, fmt.Errorf("peer %q not found in runtime after sync", publicKey))
	}

	return IssueResult{PublicKey: publicKey, ClientIP: clientIP.String(), Config: clientConfig, VPNURL: vpnURL}, nil
}

func (s *Service) Revoke(ctx context.Context, publicKey string) (RevokeResult, error) {
	publicKey = strings.TrimSpace(publicKey)
	if publicKey == "" {
		return RevokeResult{}, fmt.Errorf("public key is required")
	}

	lock, err := AcquireLock(s.opts.LockPath)
	if err != nil {
		return RevokeResult{}, fmt.Errorf("acquire lock %s: %w", s.opts.LockPath, err)
	}
	defer lock.Release()

	cfg, table, _, err := s.readState(ctx)
	if err != nil {
		return RevokeResult{}, err
	}
	if _, exists := cfg.FindPeer(publicKey); !exists {
		return RevokeResult{}, fmt.Errorf("peer %q not found in config", publicKey)
	}
	if err := cfg.Validate(); err != nil {
		return RevokeResult{}, err
	}
	backups, err := s.backup(ctx)
	if err != nil {
		return RevokeResult{}, err
	}

	cfg.RemovePeer(publicKey)
	table.Remove(publicKey)
	if err := cfg.Validate(); err != nil {
		return RevokeResult{}, s.rollback(ctx, backups, err)
	}
	if err := s.writeState(ctx, cfg, table); err != nil {
		return RevokeResult{}, s.rollback(ctx, backups, err)
	}
	if err := s.docker.SyncConf(ctx, s.opts.Container, s.opts.Interface, s.opts.ConfigPath); err != nil {
		return RevokeResult{}, s.rollback(ctx, backups, err)
	}
	runtimeText, err := s.docker.AWGShow(ctx, s.opts.Container, s.opts.Interface)
	if err != nil {
		return RevokeResult{}, s.rollback(ctx, backups, err)
	}
	if awg.ParseAWGShow(runtimeText).HasPeer(publicKey) {
		return RevokeResult{}, s.rollback(ctx, backups, fmt.Errorf("peer %q still present in runtime after sync", publicKey))
	}
	return RevokeResult{Revoked: true, PublicKey: publicKey}, nil
}

func (s *Service) readState(ctx context.Context) (*awg.Config, awg.ClientsTable, awg.RuntimeStatus, error) {
	configText, err := s.docker.ReadFile(ctx, s.opts.Container, s.opts.ConfigPath)
	if err != nil {
		return nil, nil, awg.RuntimeStatus{}, err
	}
	cfg, err := awg.ParseConfig(configText)
	if err != nil {
		return nil, nil, awg.RuntimeStatus{}, err
	}
	tableText, err := s.docker.ReadFileOrEmptyArray(ctx, s.opts.Container, s.opts.ClientsTablePath)
	if err != nil {
		return nil, nil, awg.RuntimeStatus{}, err
	}
	table, err := awg.ParseClientsTable(tableText)
	if err != nil {
		return nil, nil, awg.RuntimeStatus{}, err
	}
	runtimeText, err := s.docker.AWGShow(ctx, s.opts.Container, s.opts.Interface)
	if err != nil {
		return nil, nil, awg.RuntimeStatus{}, err
	}
	return cfg, table, awg.ParseAWGShow(runtimeText), nil
}

func (s *Service) readTrimmed(ctx context.Context, filePath string) (string, error) {
	value, err := s.docker.ReadFile(ctx, s.opts.Container, filePath)
	if err != nil {
		return "", err
	}
	value = strings.TrimSpace(value)
	if value == "" {
		return "", fmt.Errorf("%s is empty", filePath)
	}
	return value, nil
}

type backupSet struct {
	ConfigPath       string
	ClientsTablePath string
}

func (s *Service) backup(ctx context.Context) (backupSet, error) {
	suffix := ".bak." + time.Now().UTC().Format("20060102T150405") + fmt.Sprintf(".%d", time.Now().UnixNano())
	backups := backupSet{
		ConfigPath:       s.opts.ConfigPath + suffix,
		ClientsTablePath: s.opts.ClientsTablePath + suffix,
	}
	if err := s.docker.BackupFile(ctx, s.opts.Container, s.opts.ConfigPath, backups.ConfigPath, true); err != nil {
		return backupSet{}, err
	}
	if err := s.docker.BackupFile(ctx, s.opts.Container, s.opts.ClientsTablePath, backups.ClientsTablePath, false); err != nil {
		return backupSet{}, err
	}
	return backups, nil
}

func (s *Service) writeState(ctx context.Context, cfg *awg.Config, table awg.ClientsTable) error {
	if err := s.docker.WriteFileAtomic(ctx, s.opts.Container, s.opts.ConfigPath, []byte(awg.RenderConfig(cfg)), "600"); err != nil {
		return err
	}
	tableData, err := awg.RenderClientsTable(table)
	if err != nil {
		return err
	}
	return s.docker.WriteFileAtomic(ctx, s.opts.Container, s.opts.ClientsTablePath, tableData, "600")
}

func (s *Service) rollback(ctx context.Context, backups backupSet, cause error) error {
	restoreConfigErr := s.docker.RestoreFile(ctx, s.opts.Container, backups.ConfigPath, s.opts.ConfigPath, "600")
	restoreClientsErr := s.docker.RestoreFile(ctx, s.opts.Container, backups.ClientsTablePath, s.opts.ClientsTablePath, "600")
	syncErr := s.docker.SyncConf(ctx, s.opts.Container, s.opts.Interface, s.opts.ConfigPath)

	details := []string{}
	if restoreConfigErr != nil {
		details = append(details, "restore config: "+restoreConfigErr.Error())
	}
	if restoreClientsErr != nil {
		details = append(details, "restore clientsTable: "+restoreClientsErr.Error())
	}
	if syncErr != nil {
		details = append(details, "sync restored config: "+syncErr.Error())
	}
	if len(details) > 0 {
		return fmt.Errorf("%w; rollback failed: %s", cause, strings.Join(details, "; "))
	}
	return fmt.Errorf("%w; rollback completed", cause)
}

func mergePeers(cfg *awg.Config, table awg.ClientsTable, runtime awg.RuntimeStatus) []PeerView {
	views := map[string]*PeerView{}
	get := func(publicKey string) *PeerView {
		view := views[publicKey]
		if view == nil {
			view = &PeerView{PublicKey: publicKey}
			views[publicKey] = view
		}
		return view
	}

	for _, peer := range cfg.Peers {
		view := get(peer.PublicKey)
		view.InConfig = true
		view.AllowedIPsConfig = append([]string{}, peer.AllowedIPs...)
	}
	for _, peer := range runtime.Peers {
		view := get(peer.PublicKey)
		view.InRuntime = true
		view.AllowedIPsRuntime = append([]string{}, peer.AllowedIPs...)
		view.Endpoint = peer.Endpoint
		view.LatestHandshake = peer.LatestHandshake
		view.TransferReceived = peer.TransferReceived
		view.TransferSent = peer.TransferSent
	}
	for _, record := range table {
		view := get(record.ClientID)
		view.InClientsTable = true
		view.UserData = record.UserData
		if name, ok := record.UserData["clientName"].(string); ok {
			view.Name = name
		}
	}

	result := make([]PeerView, 0, len(views))
	for _, view := range views {
		result = append(result, *view)
	}
	sort.Slice(result, func(i, j int) bool {
		leftIP := firstAllowedIP(result[i])
		rightIP := firstAllowedIP(result[j])
		leftAddr, leftOK := parseAddrForSort(leftIP)
		rightAddr, rightOK := parseAddrForSort(rightIP)
		if leftOK && rightOK && leftAddr != rightAddr {
			return leftAddr.Compare(rightAddr) < 0
		}
		return result[i].PublicKey < result[j].PublicKey
	})
	return result
}

func firstAllowedIP(view PeerView) string {
	if len(view.AllowedIPsConfig) > 0 {
		return view.AllowedIPsConfig[0]
	}
	if len(view.AllowedIPsRuntime) > 0 {
		return view.AllowedIPsRuntime[0]
	}
	return ""
}

func parseAddrForSort(value string) (netip.Addr, bool) {
	if prefix, err := netip.ParsePrefix(value); err == nil {
		return prefix.Addr(), true
	}
	if addr, err := netip.ParseAddr(value); err == nil {
		return addr, true
	}
	return netip.Addr{}, false
}

func keyPathsForConfig(configPath string) (serverPublicKeyPath string, pskPath string) {
	dir := path.Dir(configPath)
	if dir == "." || dir == "/" {
		return DefaultServerPublicKey, DefaultPresharedKey
	}
	return path.Join(dir, "wireguard_server_public_key.key"), path.Join(dir, "wireguard_psk.key")
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			return value
		}
	}
	return ""
}
