package awg

import (
	"fmt"
	"net/netip"
	"strings"
)

type ClientConfigParams struct {
	ClientPrivateKey string
	ClientIP         netip.Addr
	ServerPublicKey  string
	PresharedKey     string
	EndpointHost     string
	DNS              []string
}

func RenderClientConfig(server *Config, params ClientConfigParams) (string, error) {
	if params.ClientPrivateKey == "" {
		return "", fmt.Errorf("client private key is required")
	}
	if params.ServerPublicKey == "" {
		return "", fmt.Errorf("server public key is required")
	}
	if params.PresharedKey == "" {
		return "", fmt.Errorf("preshared key is required")
	}
	if params.EndpointHost == "" {
		return "", fmt.Errorf("endpoint host is required")
	}
	port := server.ListenPort()
	if port == "" {
		return "", fmt.Errorf("server ListenPort is required")
	}
	if !params.ClientIP.IsValid() {
		return "", fmt.Errorf("client IP is required")
	}
	dns := params.DNS
	if len(dns) == 0 {
		dns = []string{"1.1.1.1", "8.8.8.8"}
	}

	var b strings.Builder
	b.WriteString("[Interface]\n")
	b.WriteString("Address = ")
	b.WriteString(params.ClientIP.String())
	b.WriteString("/32\n")
	b.WriteString("DNS = ")
	b.WriteString(strings.Join(dns, ", "))
	b.WriteByte('\n')
	b.WriteString("PrivateKey = ")
	b.WriteString(params.ClientPrivateKey)
	b.WriteByte('\n')

	for _, key := range []string{"Jc", "Jmin", "Jmax", "S1", "S2", "S3", "S4", "H1", "H2", "H3", "H4", "I1", "I2", "I3", "I4", "I5"} {
		if value, ok := server.InterfaceValue(key); ok {
			b.WriteString(key)
			b.WriteString(" = ")
			b.WriteString(value)
			b.WriteByte('\n')
		}
	}

	b.WriteString("\n[Peer]\n")
	b.WriteString("PublicKey = ")
	b.WriteString(params.ServerPublicKey)
	b.WriteByte('\n')
	b.WriteString("PresharedKey = ")
	b.WriteString(params.PresharedKey)
	b.WriteByte('\n')
	b.WriteString("AllowedIPs = 0.0.0.0/0, ::/0\n")
	b.WriteString("Endpoint = ")
	b.WriteString(params.EndpointHost)
	b.WriteByte(':')
	b.WriteString(port)
	b.WriteByte('\n')
	b.WriteString("PersistentKeepalive = 25\n")
	return b.String(), nil
}
