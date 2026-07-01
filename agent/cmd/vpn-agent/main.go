package main

import (
	"os"

	"vpn-control-app/agent/internal/cli"
)

func main() {
	os.Exit(cli.Run(os.Args[1:], os.Stdout, os.Stderr))
}
