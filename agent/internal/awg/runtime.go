package awg

import (
	"bufio"
	"strings"
)

type RuntimeStatus struct {
	InterfaceName string
	PublicKey     string
	ListenPort    string
	Peers         []RuntimePeer
	Raw           string
}

type RuntimePeer struct {
	PublicKey        string
	Endpoint         string
	AllowedIPs       []string
	LatestHandshake  string
	TransferReceived string
	TransferSent     string
}

func ParseAWGShow(input string) RuntimeStatus {
	status := RuntimeStatus{Raw: input}
	scanner := bufio.NewScanner(strings.NewReader(input))
	var current *RuntimePeer

	flushPeer := func() {
		if current != nil {
			status.Peers = append(status.Peers, *current)
			current = nil
		}
	}

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		switch {
		case strings.HasPrefix(line, "interface:"):
			flushPeer()
			status.InterfaceName = strings.TrimSpace(strings.TrimPrefix(line, "interface:"))
		case strings.HasPrefix(line, "peer:"):
			flushPeer()
			current = &RuntimePeer{PublicKey: strings.TrimSpace(strings.TrimPrefix(line, "peer:"))}
		case strings.HasPrefix(line, "public key:") && current == nil:
			status.PublicKey = strings.TrimSpace(strings.TrimPrefix(line, "public key:"))
		case strings.HasPrefix(line, "listening port:") && current == nil:
			status.ListenPort = strings.TrimSpace(strings.TrimPrefix(line, "listening port:"))
		case current != nil:
			parseRuntimePeerLine(current, line)
		}
	}
	flushPeer()
	return status
}

func parseRuntimePeerLine(peer *RuntimePeer, line string) {
	switch {
	case strings.HasPrefix(line, "endpoint:"):
		peer.Endpoint = strings.TrimSpace(strings.TrimPrefix(line, "endpoint:"))
	case strings.HasPrefix(line, "allowed ips:"):
		peer.AllowedIPs = splitCSV(strings.TrimSpace(strings.TrimPrefix(line, "allowed ips:")))
	case strings.HasPrefix(line, "latest handshake:"):
		peer.LatestHandshake = strings.TrimSpace(strings.TrimPrefix(line, "latest handshake:"))
	case strings.HasPrefix(line, "transfer:"):
		value := strings.TrimSpace(strings.TrimPrefix(line, "transfer:"))
		parts := strings.Split(value, ",")
		if len(parts) >= 1 {
			peer.TransferReceived = strings.TrimSpace(strings.TrimSuffix(parts[0], " received"))
		}
		if len(parts) >= 2 {
			peer.TransferSent = strings.TrimSpace(strings.TrimSuffix(parts[1], " sent"))
		}
	}
}

func (s RuntimeStatus) HasPeer(publicKey string) bool {
	for _, peer := range s.Peers {
		if peer.PublicKey == publicKey {
			return true
		}
	}
	return false
}
