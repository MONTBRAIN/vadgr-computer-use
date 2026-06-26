// Copyright 2026 Victor Santiago Montaño Diaz
//
// Licensed under the Apache License, Version 2.0 (the "License").
// http://www.apache.org/licenses/LICENSE-2.0
//
// vadgr-cua-host.exe — the Windows relay shim Chrome spawns via
// connectNative on WSL/Windows. It is a thin stdio<->TCP forwarder (no Python
// on Windows): it reads cua's discovery file (%LOCALAPPDATA%\vadgr-cua\
// browser.port — {port, token}), connects to cua's loopback-TCP listener,
// sends the auth frame, then pumps length-prefixed native-messaging frames
// both ways between Chrome's stdio and cua.
//
// The framing is identical to computer_use/browser/native_host.py: a 4-byte
// little-endian length prefix followed by that many bytes of UTF-8 JSON.
//
// Build (from this directory, on any OS with Go):
//   GOOS=windows GOARCH=amd64 go build -o vadgr-cua-host.exe .

package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"time"
)

type discovery struct {
	Port  int    `json:"port"`
	Token string `json:"token"`
}

// readFrame reads one length-prefixed native-messaging frame.
func readFrame(r io.Reader) ([]byte, error) {
	var hdr [4]byte
	if _, err := io.ReadFull(r, hdr[:]); err != nil {
		return nil, err
	}
	n := binary.LittleEndian.Uint32(hdr[:])
	body := make([]byte, n)
	if _, err := io.ReadFull(r, body); err != nil {
		return nil, err
	}
	return body, nil
}

// writeFrame writes one length-prefixed native-messaging frame.
func writeFrame(w io.Writer, body []byte) error {
	var hdr [4]byte
	binary.LittleEndian.PutUint32(hdr[:], uint32(len(body)))
	if _, err := w.Write(hdr[:]); err != nil {
		return err
	}
	_, err := w.Write(body)
	return err
}

// discoveryPath returns %LOCALAPPDATA%\vadgr-cua\browser.port.
func discoveryPath() string {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		base = filepath.Join(os.Getenv("USERPROFILE"), "AppData", "Local")
	}
	return filepath.Join(base, "vadgr-cua", "browser.port")
}

func readDiscovery() (discovery, error) {
	var d discovery
	raw, err := os.ReadFile(discoveryPath())
	if err != nil {
		return d, err
	}
	err = json.Unmarshal(raw, &d)
	return d, err
}

// emitError sends a clean not_connected result back to the extension.
func emitError(msg string) {
	body, _ := json.Marshal(map[string]any{
		"type": "result", "ok": false,
		"error": map[string]string{"code": "not_connected", "message": msg},
	})
	_ = writeFrame(os.Stdout, body)
}

func dial(d discovery) (net.Conn, error) {
	// WSL2 mirrored networking shares 127.0.0.1 Windows<->WSL; that is the
	// common path. A NAT fallback (the WSL IP) is resolved by cua-side config
	// in the discovery file in a later revision; loopback covers mirrored mode.
	addr := fmt.Sprintf("127.0.0.1:%d", d.Port)
	return net.DialTimeout("tcp", addr, 5*time.Second)
}

func main() {
	d, err := readDiscovery()
	if err != nil {
		emitError("cua is not running (no browser discovery file); start cua first")
		os.Exit(1)
	}
	conn, err := dial(d)
	if err != nil {
		emitError(fmt.Sprintf("cua is not listening on 127.0.0.1:%d; start cua first", d.Port))
		os.Exit(1)
	}
	defer conn.Close()

	// Authenticate before relaying Chrome frames.
	if d.Token != "" {
		auth, _ := json.Marshal(map[string]string{"type": "auth", "token": d.Token})
		if err := writeFrame(conn, auth); err != nil {
			emitError("failed to authenticate to cua")
			os.Exit(1)
		}
	}

	done := make(chan struct{}, 2)

	// Chrome stdin -> cua
	go func() {
		for {
			frame, err := readFrame(os.Stdin)
			if err != nil {
				break
			}
			if err := writeFrame(conn, frame); err != nil {
				break
			}
		}
		done <- struct{}{}
	}()

	// cua -> Chrome stdout
	go func() {
		for {
			frame, err := readFrame(conn)
			if err != nil {
				break
			}
			if err := writeFrame(os.Stdout, frame); err != nil {
				break
			}
		}
		done <- struct{}{}
	}()

	<-done
}
