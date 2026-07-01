package awg

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"net/netip"
	"strings"
)

type ShareURIParams struct {
	EndpointHost        string
	DNS                 []string
	NativeConfig        string
	ClientPrivateKey    string
	ClientPublicKey     string
	ClientIP            netip.Addr
	ServerPublicKey     string
	PresharedKey        string
	AllowedIPs          []string
	PersistentKeepalive string
	MTU                 string
	Description         string
}

func RenderAmneziaShareURI(server *Config, params ShareURIParams) (string, error) {
	if params.EndpointHost == "" {
		return "", fmt.Errorf("endpoint host is required")
	}
	if params.NativeConfig == "" {
		return "", fmt.Errorf("native config is required")
	}
	if params.ClientPrivateKey == "" || params.ClientPublicKey == "" || params.ServerPublicKey == "" || params.PresharedKey == "" {
		return "", fmt.Errorf("client and server keys are required")
	}
	if !params.ClientIP.IsValid() {
		return "", fmt.Errorf("client IP is required")
	}
	port := server.ListenPort()
	if port == "" {
		return "", fmt.Errorf("server ListenPort is required")
	}
	dns := params.DNS
	if len(dns) == 0 {
		dns = []string{"1.1.1.1", "8.8.8.8"}
	}
	allowedIPs := params.AllowedIPs
	if len(allowedIPs) == 0 {
		allowedIPs = []string{"0.0.0.0/0", "::/0"}
	}
	keepalive := firstNonEmpty(params.PersistentKeepalive, "25")
	mtu := firstNonEmpty(params.MTU, "1376")

	clientJSON := map[string]any{
		"config":                params.NativeConfig,
		"hostName":              params.EndpointHost,
		"port":                  mustAtoi(port),
		"client_ip":             params.ClientIP.String(),
		"client_priv_key":       params.ClientPrivateKey,
		"client_pub_key":        params.ClientPublicKey,
		"server_pub_key":        params.ServerPublicKey,
		"psk_key":               params.PresharedKey,
		"clientId":              params.ClientPublicKey,
		"allowed_ips":           allowedIPs,
		"persistent_keep_alive": keepalive,
		"mtu":                   mtu,
	}
	copyAWGFields(server, clientJSON)
	clientConfigJSON, err := marshalCompactJSON(clientJSON)
	if err != nil {
		return "", err
	}

	awgJSON := map[string]any{
		"port":             port,
		"transport_proto":  "udp",
		"protocol_version": "2",
		"subnet_address":   subnetAddress(server),
		"subnet_cidr":      subnetCIDR(server),
		"last_config":      string(clientConfigJSON),
	}
	copyAWGFields(server, awgJSON)

	containerJSON := map[string]any{
		"container": "amnezia-awg2",
		"awg":       awgJSON,
	}
	root := map[string]any{
		"hostName":         params.EndpointHost,
		"containers":       []any{containerJSON},
		"defaultContainer": "amnezia-awg2",
	}
	if params.Description != "" {
		root["description"] = params.Description
	}
	if len(dns) > 0 {
		root["dns1"] = dns[0]
	}
	if len(dns) > 1 {
		root["dns2"] = dns[1]
	}

	rootJSON, err := marshalIndentedJSON(root)
	if err != nil {
		return "", err
	}
	compressed, err := qCompress(rootJSON, 8)
	if err != nil {
		return "", err
	}
	return "vpn://" + base64.RawURLEncoding.EncodeToString(compressed), nil
}

func qCompress(input []byte, level int) ([]byte, error) {
	var out bytes.Buffer
	if len(input) > int(^uint32(0)) {
		return nil, fmt.Errorf("config is too large")
	}
	var length [4]byte
	binary.BigEndian.PutUint32(length[:], uint32(len(input)))
	out.Write(length[:])
	writer, err := zlib.NewWriterLevel(&out, level)
	if err != nil {
		return nil, err
	}
	if _, err := writer.Write(input); err != nil {
		writer.Close()
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func marshalCompactJSON(value any) ([]byte, error) {
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(out.Bytes(), []byte("\n")), nil
}

func marshalIndentedJSON(value any) ([]byte, error) {
	var out bytes.Buffer
	encoder := json.NewEncoder(&out)
	encoder.SetEscapeHTML(false)
	encoder.SetIndent("", "    ")
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func copyAWGFields(server *Config, dst map[string]any) {
	mapping := map[string]string{
		"Jc":   "Jc",
		"Jmin": "Jmin",
		"Jmax": "Jmax",
		"S1":   "S1",
		"S2":   "S2",
		"S3":   "S3",
		"S4":   "S4",
		"H1":   "H1",
		"H2":   "H2",
		"H3":   "H3",
		"H4":   "H4",
		"I1":   "I1",
		"I2":   "I2",
		"I3":   "I3",
		"I4":   "I4",
		"I5":   "I5",
	}
	for configKey, jsonKey := range mapping {
		if value, ok := server.InterfaceValue(configKey); ok {
			dst[jsonKey] = value
		}
	}
}

func subnetAddress(server *Config) string {
	value, ok := server.InterfaceAddress()
	if !ok {
		return ""
	}
	if idx := strings.Index(value, "/"); idx >= 0 {
		return value[:idx]
	}
	return value
}

func subnetCIDR(server *Config) string {
	value, ok := server.InterfaceAddress()
	if !ok {
		return ""
	}
	if idx := strings.Index(value, "/"); idx >= 0 && idx+1 < len(value) {
		return value[idx+1:]
	}
	return "24"
}

func mustAtoi(value string) int {
	n := 0
	for _, r := range value {
		if r < '0' || r > '9' {
			return 0
		}
		n = n*10 + int(r-'0')
	}
	return n
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
