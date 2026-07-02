package awg

import (
	"bufio"
	"fmt"
	"net/netip"
	"sort"
	"strings"
)

type InterfaceLine struct {
	Raw       string
	Key       string
	Value     string
	Commented bool
	HasKV     bool
}

type Peer struct {
	PublicKey    string
	PresharedKey string
	AllowedIPs   []string
	// Extra holds raw peer lines the agent does not manage (for example
	// PersistentKeepalive or comments), preserved verbatim across
	// parse/render so a rewrite never silently drops them.
	Extra []string
}

type Config struct {
	Interface []InterfaceLine
	Peers     []Peer
}

func ParseConfig(input string) (*Config, error) {
	cfg := &Config{}
	scanner := bufio.NewScanner(strings.NewReader(input))
	section := ""
	var current *Peer
	lineNo := 0

	flushPeer := func() {
		if current != nil {
			cfg.Peers = append(cfg.Peers, *current)
			current = nil
		}
	}

	for scanner.Scan() {
		lineNo++
		line := strings.TrimRight(scanner.Text(), "\r")
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			name := strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(trimmed, "["), "]"))
			switch strings.ToLower(name) {
			case "interface":
				flushPeer()
				section = "interface"
			case "peer":
				flushPeer()
				section = "peer"
				current = &Peer{}
			default:
				return nil, fmt.Errorf("unsupported section %q on line %d", name, lineNo)
			}
			continue
		}

		switch section {
		case "interface":
			key, value, commented, ok := parseAssignment(line)
			cfg.Interface = append(cfg.Interface, InterfaceLine{
				Raw:       line,
				Key:       key,
				Value:     value,
				Commented: commented,
				HasKV:     ok,
			})
		case "peer":
			if current == nil || trimmed == "" {
				continue
			}
			if strings.HasPrefix(trimmed, "#") {
				current.Extra = append(current.Extra, trimmed)
				continue
			}
			key, value, _, ok := parseAssignment(line)
			if !ok {
				current.Extra = append(current.Extra, trimmed)
				continue
			}
			switch key {
			case "PublicKey":
				current.PublicKey = value
			case "PresharedKey", "PreSharedKey":
				current.PresharedKey = value
			case "AllowedIPs":
				current.AllowedIPs = splitCSV(value)
			default:
				current.Extra = append(current.Extra, trimmed)
			}
		default:
			if trimmed != "" {
				return nil, fmt.Errorf("line %d appears before a section", lineNo)
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, err
	}
	flushPeer()

	if len(cfg.Interface) == 0 {
		return nil, fmt.Errorf("missing [Interface] section")
	}
	return cfg, nil
}

func parseAssignment(line string) (key string, value string, commented bool, ok bool) {
	trimmed := strings.TrimSpace(line)
	if trimmed == "" {
		return "", "", false, false
	}
	if strings.HasPrefix(trimmed, "#") {
		commented = true
		trimmed = strings.TrimSpace(strings.TrimPrefix(trimmed, "#"))
	}
	idx := strings.Index(trimmed, "=")
	if idx < 0 {
		return "", "", commented, false
	}
	key = strings.TrimSpace(trimmed[:idx])
	value = strings.TrimSpace(trimmed[idx+1:])
	if key == "" {
		return "", "", commented, false
	}
	return key, value, commented, true
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

func (c *Config) InterfaceValue(key string) (string, bool) {
	for _, line := range c.Interface {
		if line.HasKV && strings.EqualFold(line.Key, key) {
			return line.Value, true
		}
	}
	return "", false
}

func (c *Config) ListenPort() string {
	value, _ := c.InterfaceValue("ListenPort")
	return value
}

func (c *Config) InterfaceAddress() (string, bool) {
	value, ok := c.InterfaceValue("Address")
	if !ok {
		return "", false
	}
	if idx := strings.Index(value, ","); idx >= 0 {
		value = value[:idx]
	}
	value = strings.TrimSpace(value)
	return value, value != ""
}

func (c *Config) AddPeer(peer Peer) {
	c.Peers = append(c.Peers, peer)
}

func (c *Config) RemovePeer(publicKey string) bool {
	next := c.Peers[:0]
	removed := false
	for _, peer := range c.Peers {
		if peer.PublicKey == publicKey {
			removed = true
			continue
		}
		next = append(next, peer)
	}
	c.Peers = next
	return removed
}

func (c *Config) FindPeer(publicKey string) (Peer, bool) {
	for _, peer := range c.Peers {
		if peer.PublicKey == publicKey {
			return peer, true
		}
	}
	return Peer{}, false
}

func (c *Config) Validate() error {
	if _, ok := c.InterfaceAddress(); !ok {
		return fmt.Errorf("interface Address is required")
	}
	if c.ListenPort() == "" {
		return fmt.Errorf("interface ListenPort is required")
	}

	publicKeys := map[string]struct{}{}
	allowedIPs := map[string]struct{}{}
	for i, peer := range c.Peers {
		if peer.PublicKey == "" {
			return fmt.Errorf("peer %d has empty PublicKey", i+1)
		}
		if _, exists := publicKeys[peer.PublicKey]; exists {
			return fmt.Errorf("duplicate peer PublicKey %q", peer.PublicKey)
		}
		publicKeys[peer.PublicKey] = struct{}{}

		if len(peer.AllowedIPs) == 0 {
			return fmt.Errorf("peer %q has empty AllowedIPs", peer.PublicKey)
		}
		for _, allowed := range peer.AllowedIPs {
			if _, err := netip.ParsePrefix(allowed); err != nil {
				return fmt.Errorf("peer %q has invalid AllowedIPs %q: %w", peer.PublicKey, allowed, err)
			}
			if _, exists := allowedIPs[allowed]; exists {
				return fmt.Errorf("duplicate AllowedIPs %q", allowed)
			}
			allowedIPs[allowed] = struct{}{}
		}
	}
	return nil
}

func RenderConfig(cfg *Config) string {
	var b strings.Builder
	b.WriteString("[Interface]\n")
	lines := trimTrailingEmptyInterfaceLines(cfg.Interface)
	for _, line := range lines {
		b.WriteString(line.Raw)
		b.WriteByte('\n')
	}
	b.WriteByte('\n')

	for _, peer := range cfg.Peers {
		b.WriteString("[Peer]\n")
		b.WriteString("PublicKey = ")
		b.WriteString(peer.PublicKey)
		b.WriteByte('\n')
		if peer.PresharedKey != "" {
			b.WriteString("PresharedKey = ")
			b.WriteString(peer.PresharedKey)
			b.WriteByte('\n')
		}
		b.WriteString("AllowedIPs = ")
		b.WriteString(strings.Join(peer.AllowedIPs, ", "))
		b.WriteByte('\n')
		for _, extra := range peer.Extra {
			b.WriteString(extra)
			b.WriteByte('\n')
		}
		b.WriteByte('\n')
	}
	return b.String()
}

func trimTrailingEmptyInterfaceLines(lines []InterfaceLine) []InterfaceLine {
	end := len(lines)
	for end > 0 && strings.TrimSpace(lines[end-1].Raw) == "" {
		end--
	}
	return lines[:end]
}

func SortedPeerKeys(peers []Peer) []string {
	keys := make([]string, 0, len(peers))
	for _, peer := range peers {
		keys = append(keys, peer.PublicKey)
	}
	sort.Strings(keys)
	return keys
}
