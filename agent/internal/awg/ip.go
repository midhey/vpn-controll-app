package awg

import (
	"encoding/binary"
	"fmt"
	"net/netip"
	"strings"
)

func AllocateFreeIPv4(cfg *Config, extraUsed ...string) (netip.Addr, error) {
	address, ok := cfg.InterfaceAddress()
	if !ok {
		return netip.Addr{}, fmt.Errorf("interface Address is required")
	}
	prefix, err := netip.ParsePrefix(address)
	if err != nil {
		return netip.Addr{}, fmt.Errorf("invalid interface Address %q: %w", address, err)
	}
	if !prefix.Addr().Is4() {
		return netip.Addr{}, fmt.Errorf("only IPv4 allocation is supported, got %q", address)
	}

	used := map[netip.Addr]struct{}{}
	// The interface Address may be the server's own host address rather
	// than the subnet base; never hand it out to a client.
	used[prefix.Addr()] = struct{}{}
	prefix = prefix.Masked()
	for _, peer := range cfg.Peers {
		for _, allowed := range peer.AllowedIPs {
			addr, ok := allowedIPv4Addr(allowed)
			if ok {
				used[addr] = struct{}{}
			}
		}
	}
	for _, allowed := range extraUsed {
		addr, ok := allowedIPv4Addr(allowed)
		if ok {
			used[addr] = struct{}{}
		}
	}

	bits := prefix.Bits()
	if bits <= 0 || bits > 32 {
		return netip.Addr{}, fmt.Errorf("invalid IPv4 prefix %q", address)
	}
	network := addrToUint32(prefix.Addr())
	size := uint64(1) << uint(32-bits)
	if size <= 2 {
		if _, exists := used[prefix.Addr()]; !exists {
			return prefix.Addr(), nil
		}
		return netip.Addr{}, fmt.Errorf("no free IPv4 addresses in %q", prefix.String())
	}

	first := uint64(network) + 1
	lastExclusive := uint64(network) + size - 1
	for candidate := first; candidate < lastExclusive; candidate++ {
		addr := uint32ToAddr(uint32(candidate))
		if _, exists := used[addr]; !exists {
			return addr, nil
		}
	}
	return netip.Addr{}, fmt.Errorf("no free IPv4 addresses in %q", prefix.String())
}

func allowedIPv4Addr(value string) (netip.Addr, bool) {
	value = strings.TrimSpace(value)
	if value == "" {
		return netip.Addr{}, false
	}
	if prefix, err := netip.ParsePrefix(value); err == nil && prefix.Addr().Is4() {
		return prefix.Addr(), true
	}
	if addr, err := netip.ParseAddr(value); err == nil && addr.Is4() {
		return addr, true
	}
	return netip.Addr{}, false
}

func addrToUint32(addr netip.Addr) uint32 {
	raw := addr.As4()
	return binary.BigEndian.Uint32(raw[:])
}

func uint32ToAddr(value uint32) netip.Addr {
	var raw [4]byte
	binary.BigEndian.PutUint32(raw[:], value)
	return netip.AddrFrom4(raw)
}
