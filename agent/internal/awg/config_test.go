package awg

import (
	"strings"
	"testing"
)

const sampleConfig = `[Interface]
PrivateKey = server-private
Address = 10.8.1.0/24
ListenPort = 49351
Jc = 6
Jmin = 10
Jmax = 50
S1 = 43
S2 = 109
S3 = 19
S4 = 14
H1 = 1545622519-1885974417
H2 = 1892645461-1906088258
H3 = 2136010924-2144271940
H4 = 2145755593-2146817391
# I1 = <r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001>
# I2 = 
# I3 = 
# I4 = 
# I5 = 
[Peer]
PublicKey = peer-one
PresharedKey = psk
AllowedIPs = 10.8.1.1/32

[Peer]
PublicKey = peer-three
PresharedKey = psk
AllowedIPs = 10.8.1.3/32
`

func TestParseRenderRoundTripPreservesInterfaceAndPeers(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(cfg.Peers), 2; got != want {
		t.Fatalf("peer count = %d, want %d", got, want)
	}
	if got, _ := cfg.InterfaceValue("I1"); !strings.HasPrefix(got, "<r 2>") {
		t.Fatalf("I1 = %q, want commented value", got)
	}
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}

	rendered := RenderConfig(cfg)
	reparsed, err := ParseConfig(rendered)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(reparsed.Peers), len(cfg.Peers); got != want {
		t.Fatalf("reparsed peer count = %d, want %d", got, want)
	}
	if got, _ := reparsed.InterfaceValue("H4"); got != "2145755593-2146817391" {
		t.Fatalf("H4 = %q", got)
	}
}

func TestParseRenderPreservesUnknownPeerLines(t *testing.T) {
	config := strings.Replace(sampleConfig,
		"PublicKey = peer-one",
		"PublicKey = peer-one\nPersistentKeepalive = 25\n# managed by hand",
		1)
	cfg, err := ParseConfig(config)
	if err != nil {
		t.Fatal(err)
	}
	peer, ok := cfg.FindPeer("peer-one")
	if !ok {
		t.Fatal("peer-one not found")
	}
	if got, want := len(peer.Extra), 2; got != want {
		t.Fatalf("extra lines = %#v, want %d entries", peer.Extra, want)
	}

	rendered := RenderConfig(cfg)
	if !strings.Contains(rendered, "PersistentKeepalive = 25") {
		t.Fatalf("rendered config lost PersistentKeepalive:\n%s", rendered)
	}
	if !strings.Contains(rendered, "# managed by hand") {
		t.Fatalf("rendered config lost peer comment:\n%s", rendered)
	}

	reparsed, err := ParseConfig(rendered)
	if err != nil {
		t.Fatal(err)
	}
	if RenderConfig(reparsed) != rendered {
		t.Fatal("render is not stable across parse/render cycles")
	}
}

func TestAddRemovePeer(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	cfg.AddPeer(Peer{PublicKey: "peer-two", PresharedKey: "psk", AllowedIPs: []string{"10.8.1.2/32"}})
	if err := cfg.Validate(); err != nil {
		t.Fatal(err)
	}
	if _, ok := cfg.FindPeer("peer-two"); !ok {
		t.Fatal("peer-two not found after add")
	}
	if !cfg.RemovePeer("peer-two") {
		t.Fatal("peer-two not removed")
	}
	if _, ok := cfg.FindPeer("peer-two"); ok {
		t.Fatal("peer-two still found after remove")
	}
}

func TestValidateRejectsOverlappingAllowedIPs(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	cfg.AddPeer(Peer{PublicKey: "peer-wide", PresharedKey: "psk", AllowedIPs: []string{"10.8.1.0/24"}})
	err = cfg.Validate()
	if err == nil {
		t.Fatal("Validate accepted overlapping AllowedIPs")
	}
	if !strings.Contains(err.Error(), "overlaps") {
		t.Fatalf("error = %q, want overlap error", err)
	}
}

func TestAllocateFreeIPv4UsesFirstGap(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	ip, err := AllocateFreeIPv4(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := ip.String(), "10.8.1.2"; got != want {
		t.Fatalf("allocated IP = %s, want %s", got, want)
	}
}

func TestAllocateFreeIPv4SkipsExtraUsed(t *testing.T) {
	cfg, err := ParseConfig(sampleConfig)
	if err != nil {
		t.Fatal(err)
	}
	ip, err := AllocateFreeIPv4(cfg, "10.8.1.2/32", "10.8.1.4/32")
	if err != nil {
		t.Fatal(err)
	}
	if got, want := ip.String(), "10.8.1.5"; got != want {
		t.Fatalf("allocated IP = %s, want %s", got, want)
	}
}

func TestAllocateFreeIPv4ReservesServerAddress(t *testing.T) {
	config := strings.Replace(sampleConfig, "Address = 10.8.1.0/24", "Address = 10.8.1.2/24", 1)
	cfg, err := ParseConfig(config)
	if err != nil {
		t.Fatal(err)
	}
	ip, err := AllocateFreeIPv4(cfg)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := ip.String(), "10.8.1.4"; got != want {
		t.Fatalf("allocated IP = %s, want %s", got, want)
	}
}
