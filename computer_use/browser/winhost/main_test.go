package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"testing"
)

func TestBrokerProxyInjectsWindowsTokenAndForwardsLines(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	port := listener.Addr().(*net.TCPAddr).Port
	root := t.TempDir()
	t.Setenv("LOCALAPPDATA", root)
	if err := os.MkdirAll(filepath.Join(root, "vadgr-cua"), 0o700); err != nil {
		t.Fatal(err)
	}
	endpoint, _ := json.Marshal(map[string]any{
		"host": "127.0.0.1", "port": port, "token": "windows-secret",
	})
	if err := os.WriteFile(brokerEndpointPath(), endpoint, 0o600); err != nil {
		t.Fatal(err)
	}

	done := make(chan error, 1)
	go func() {
		conn, acceptErr := listener.Accept()
		if acceptErr != nil {
			done <- acceptErr
			return
		}
		defer conn.Close()
		line, readErr := bufio.NewReader(conn).ReadBytes('\n')
		if readErr != nil {
			done <- readErr
			return
		}
		var hello map[string]any
		if err := json.Unmarshal(line, &hello); err != nil {
			done <- err
			return
		}
		if hello["token"] != "windows-secret" {
			done <- fmt.Errorf("proxy forwarded the caller token: %#v", hello["token"])
			return
		}
		_, writeErr := conn.Write([]byte("{\"ok\":true}\n"))
		done <- writeErr
	}()

	input := bytes.NewBufferString("{\"token\":null,\"client_id\":null}\n")
	var output bytes.Buffer
	if code := brokerProxy(input, &output); code != 0 {
		t.Fatalf("brokerProxy returned %d", code)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	if output.String() != "{\"ok\":true}\n" {
		t.Fatalf("unexpected proxy output: %q", output.String())
	}
}

func TestBrokerProxyReportsMissingDiscovery(t *testing.T) {
	t.Setenv("LOCALAPPDATA", t.TempDir())
	var output bytes.Buffer
	if code := brokerProxy(bytes.NewBuffer(nil), &output); code == 0 {
		t.Fatal("brokerProxy accepted missing discovery")
	}
	var reply map[string]any
	if err := json.Unmarshal(output.Bytes(), &reply); err != nil {
		t.Fatalf("invalid broker error: %v", err)
	}
	errorBody := reply["error"].(map[string]any)
	if errorBody["code"] != "browser_broker_discovery_invalid" {
		t.Fatalf("unexpected code: %#v", errorBody["code"])
	}
	if errorBody["remediation"] == "enable Windows interop" {
		t.Fatal("broker discovery failure was reported as interop")
	}
}

func TestBrokerEndpointPathHonorsExplicitIsolatedPath(t *testing.T) {
	isolated := filepath.Join(t.TempDir(), "isolated-broker.json")
	t.Setenv("VADGR_CUA_BROKER_ENDPOINT", isolated)
	t.Setenv("LOCALAPPDATA", filepath.Join(t.TempDir(), "owner-local"))
	if actual := brokerEndpointPath(); actual != isolated {
		t.Fatalf("broker endpoint = %q, want %q", actual, isolated)
	}
}

func TestDiscoveryPathHonorsExplicitIsolatedPath(t *testing.T) {
	isolated := filepath.Join(t.TempDir(), "isolated-browser.port")
	t.Setenv("VADGR_CUA_BROWSER_DISCOVERY", isolated)
	t.Setenv("LOCALAPPDATA", filepath.Join(t.TempDir(), "owner-local"))
	if actual := discoveryPath(); actual != isolated {
		t.Fatalf("browser discovery = %q, want %q", actual, isolated)
	}
}
