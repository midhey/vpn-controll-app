package awg

import (
	"net/netip"
	"strings"
	"testing"
)

func TestRenderClientConfigIncludesAWGFields(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	clientConfig, err := RenderClientConfig(cfg, ClientConfigParams{
		ClientPrivateKey: "client-private",
		ClientIP:         netip.MustParseAddr("10.8.1.2"),
		ServerPublicKey:  "server-public",
		PresharedKey:     "psk",
		EndpointHost:     "203.0.113.10",
		DNS:              []string{"1.1.1.1", "8.8.8.8"},
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"Address = 10.8.1.2/32",
		"DNS = 1.1.1.1, 8.8.8.8",
		"Jc = 6",
		"S4 = 14",
		"H4 = 2145755593-2146817391",
		"I1 = <r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001>",
		"Endpoint = 203.0.113.10:49351",
	} {
		if !strings.Contains(clientConfig, want) {
			t.Fatalf("client config missing %q:\n%s", want, clientConfig)
		}
	}
}
