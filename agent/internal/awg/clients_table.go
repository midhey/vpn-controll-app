package awg

import (
	"encoding/json"
	"fmt"
	"time"
)

type ClientRecord struct {
	ClientID string         `json:"clientId"`
	UserData map[string]any `json:"userData,omitempty"`
}

type ClientsTable []ClientRecord

func ParseClientsTable(input string) (ClientsTable, error) {
	if len(trimSpaceBytes([]byte(input))) == 0 {
		return ClientsTable{}, nil
	}

	var table ClientsTable
	if err := json.Unmarshal([]byte(input), &table); err == nil {
		for i := range table {
			if table[i].UserData == nil {
				table[i].UserData = map[string]any{}
			}
		}
		return table, nil
	}

	var legacy map[string]map[string]any
	if err := json.Unmarshal([]byte(input), &legacy); err != nil {
		return nil, fmt.Errorf("parse clientsTable: %w", err)
	}
	for clientID, userData := range legacy {
		if userData == nil {
			userData = map[string]any{}
		}
		table = append(table, ClientRecord{ClientID: clientID, UserData: userData})
	}
	return table, nil
}

func RenderClientsTable(table ClientsTable) ([]byte, error) {
	data, err := json.MarshalIndent(table, "", "    ")
	if err != nil {
		return nil, err
	}
	return append(data, '\n'), nil
}

func (t *ClientsTable) AddOrUpdate(publicKey, name, allowedIP string, now time.Time) {
	for i := range *t {
		if (*t)[i].ClientID == publicKey {
			if (*t)[i].UserData == nil {
				(*t)[i].UserData = map[string]any{}
			}
			(*t)[i].UserData["clientName"] = name
			if allowedIP != "" {
				(*t)[i].UserData["allowedIps"] = allowedIP
			}
			if _, ok := (*t)[i].UserData["creationDate"]; !ok {
				(*t)[i].UserData["creationDate"] = formatCreationDate(now)
			}
			return
		}
	}

	userData := map[string]any{
		"clientName":   name,
		"creationDate": formatCreationDate(now),
	}
	if allowedIP != "" {
		userData["allowedIps"] = allowedIP
	}
	*t = append(*t, ClientRecord{ClientID: publicKey, UserData: userData})
}

func (t *ClientsTable) Remove(publicKey string) bool {
	next := (*t)[:0]
	removed := false
	for _, record := range *t {
		if record.ClientID == publicKey {
			removed = true
			continue
		}
		next = append(next, record)
	}
	*t = next
	return removed
}

func (t ClientsTable) ByPublicKey(publicKey string) (ClientRecord, bool) {
	for _, record := range t {
		if record.ClientID == publicKey {
			return record, true
		}
	}
	return ClientRecord{}, false
}

func formatCreationDate(now time.Time) string {
	return now.Local().Format("Mon Jan 2 15:04:05 2006")
}

func trimSpaceBytes(input []byte) []byte {
	start := 0
	for start < len(input) && isSpace(input[start]) {
		start++
	}
	end := len(input)
	for end > start && isSpace(input[end-1]) {
		end--
	}
	return input[start:end]
}

func isSpace(b byte) bool {
	switch b {
	case ' ', '\n', '\r', '\t':
		return true
	default:
		return false
	}
}
