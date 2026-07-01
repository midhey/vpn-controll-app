package awg

import (
	"encoding/json"
	"testing"
	"time"
)

func TestClientsTableAddUpdateRemovePreservesUserData(t *testing.T) {
	table, err := ParseClientsTable(`[
  {
    "clientId": "peer-one",
    "userData": {
      "clientName": "Old",
      "creationDate": "Wed Jul 1 20:10:19 2026",
      "latestHandshake": "1m ago"
    }
  }
]`)
	if err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, 7, 1, 20, 30, 0, 0, time.UTC)
	table.AddOrUpdate("peer-one", "Renamed", "10.8.1.1/32", now)
	record, ok := table.ByPublicKey("peer-one")
	if !ok {
		t.Fatal("peer-one not found")
	}
	if got := record.UserData["latestHandshake"]; got != "1m ago" {
		t.Fatalf("latestHandshake = %v, want preserved", got)
	}
	if got := record.UserData["clientName"]; got != "Renamed" {
		t.Fatalf("clientName = %v", got)
	}

	table.AddOrUpdate("peer-two", "New", "10.8.1.2/32", now)
	if _, ok := table.ByPublicKey("peer-two"); !ok {
		t.Fatal("peer-two not added")
	}
	if !table.Remove("peer-one") {
		t.Fatal("peer-one not removed")
	}

	data, err := RenderClientsTable(table)
	if err != nil {
		t.Fatal(err)
	}
	if !json.Valid(data) {
		t.Fatalf("rendered clientsTable is invalid JSON: %s", string(data))
	}
}

func TestParseLegacyClientsTableObject(t *testing.T) {
	table, err := ParseClientsTable(`{"peer-one":{"clientName":"Legacy"}}`)
	if err != nil {
		t.Fatal(err)
	}
	record, ok := table.ByPublicKey("peer-one")
	if !ok {
		t.Fatal("legacy peer not parsed")
	}
	if got := record.UserData["clientName"]; got != "Legacy" {
		t.Fatalf("clientName = %v", got)
	}
}
