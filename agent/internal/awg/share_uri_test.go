package awg

import (
	"bytes"
	"compress/zlib"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"net/netip"
	"strings"
	"testing"
)

func TestRenderAmneziaShareURI(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	nativeConfig, err := RenderClientConfig(cfg, ClientConfigParams{
		ClientPrivateKey: "client-private",
		ClientIP:         netip.MustParseAddr("10.8.1.2"),
		ServerPublicKey:  "server-public",
		PresharedKey:     "psk",
		EndpointHost:     "72.56.69.23",
		DNS:              []string{"1.1.1.1", "8.8.8.8"},
	})
	if err != nil {
		t.Fatal(err)
	}

	uri, err := RenderAmneziaShareURI(cfg, ShareURIParams{
		EndpointHost:     "72.56.69.23",
		DNS:              []string{"1.1.1.1", "8.8.8.8"},
		NativeConfig:     nativeConfig,
		ClientPrivateKey: "client-private",
		ClientPublicKey:  "client-public",
		ClientIP:         netip.MustParseAddr("10.8.1.2"),
		ServerPublicKey:  "server-public",
		PresharedKey:     "psk",
		Description:      "test",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(uri, "vpn://") {
		t.Fatalf("uri = %q", uri)
	}

	root, rootJSON := decodeShareURI(t, uri)
	if !bytes.Contains(rootJSON, []byte("\"containers\"")) {
		t.Fatalf("decoded config does not contain containers: %s", rootJSON)
	}
	if root["hostName"] != "72.56.69.23" {
		t.Fatalf("hostName = %v", root["hostName"])
	}
	if root["defaultContainer"] != "amnezia-awg2" {
		t.Fatalf("defaultContainer = %v", root["defaultContainer"])
	}
	containers := root["containers"].([]any)
	container := containers[0].(map[string]any)
	if container["container"] != "amnezia-awg2" {
		t.Fatalf("container = %v", container["container"])
	}
	awgJSON := container["awg"].(map[string]any)
	if awgJSON["protocol_version"] != "2" {
		t.Fatalf("protocol_version = %v", awgJSON["protocol_version"])
	}
	if awgJSON["Jc"] != "6" || awgJSON["S4"] != "14" {
		t.Fatalf("missing AWG fields: %#v", awgJSON)
	}
	lastConfigRaw, ok := awgJSON["last_config"].(string)
	if !ok || lastConfigRaw == "" {
		t.Fatalf("last_config = %#v", awgJSON["last_config"])
	}
	if strings.Contains(lastConfigRaw, `\u003c`) {
		t.Fatalf("last_config contains HTML escaping: %s", lastConfigRaw)
	}
	var lastConfig map[string]any
	if err := json.Unmarshal([]byte(lastConfigRaw), &lastConfig); err != nil {
		t.Fatal(err)
	}
	if lastConfig["client_pub_key"] != "client-public" {
		t.Fatalf("client_pub_key = %v", lastConfig["client_pub_key"])
	}
	if lastConfig["config"] != nativeConfig {
		t.Fatal("native config was not embedded in last_config")
	}
}

func decodeShareURI(t *testing.T, uri string) (map[string]any, []byte) {
	t.Helper()
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(uri, "vpn://"))
	if err != nil {
		t.Fatal(err)
	}
	if len(raw) < 4 {
		t.Fatal("compressed payload is too short")
	}
	expectedLen := binary.BigEndian.Uint32(raw[:4])
	reader, err := zlib.NewReader(bytes.NewReader(raw[4:]))
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	jsonBytes, err := io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	if uint32(len(jsonBytes)) != expectedLen {
		t.Fatalf("uncompressed length = %d, want %d", len(jsonBytes), expectedLen)
	}
	var root map[string]any
	if err := json.Unmarshal(jsonBytes, &root); err != nil {
		t.Fatal(err)
	}
	return root, jsonBytes
}
