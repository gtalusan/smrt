#!/usr/bin/env python3
"""One tick: wave-batched stats queries across every switch in TP_CREDENTIALS
over a single UDP socket pair, then one batched mosquitto_pub. Stdlib only.

The protocol replies carry the switch MAC and echo the request sequence id,
so independent per-switch sessions multiplex over one socket: wave 1 sends
all token requests, wave 2 all logins, wave 3 all stats queries, each wave
collecting replies until every switch answered. Discovery is skipped -
TP_CREDENTIALS already enumerates the switches - with an optional fallback
(DISCOVER=1) for unlisted switches.
"""

import json
import os
import re
import sys
import time

here = os.path.dirname(os.path.abspath(__file__))
for cand in (here, os.path.dirname(here), "/app"):
    if os.path.exists(os.path.join(cand, "discovery.py")):
        sys.path.insert(0, cand)
        break

import ifaces
from binary import mac_to_bytes, mac_to_str
from protocol import Protocol
from network import Network


def log(msg):
    print(time.strftime("%F %T"), msg, flush=True)


DENY = re.compile(
    r"^(docker|veth|br-|virbr|tun|tap|vnet|tailscale|wg|zt|awdl|llw|utun|anpi|"
    r"bond|erspan|gre|ip6|ip_|sit|ifb|nlmon|teql|gif|stf)"
)


def default_iface():
    try:
        rows = []
        for line in open("/proc/net/route"):
            p = line.split()
            if len(p) >= 7 and p[1] == "00000000" and p[2] != "00000000":
                rows.append((int(p[6]), p[0]))
        if rows:
            return sorted(rows)[0][1]
    except OSError:
        pass
    return None


def candidates():
    if os.environ.get("INTERFACE"):
        return [os.environ["INTERFACE"]]
    out = []
    d = default_iface()
    if d:
        out.append(d)
    for i in ifaces.interfaces():
        if i not in out and not i.startswith("lo") and not DENY.match(i):
            out.append(i)
    return out


def host_addr():
    for iface in candidates():
        try:
            addrs = ifaces.ifaddresses(iface)
        except OSError:
            continue
        if ifaces.AF_INET in addrs and ifaces.AF_LINK in addrs:
            a = addrs[ifaces.AF_INET][0]
            return a["addr"], addrs[ifaces.AF_LINK][0]["addr"]
    return None, None


def norm_mac(m):
    return re.sub(r"[^0-9a-f]", "", m.lower())


def load_creds():
    entries = []
    seen = set()
    for key, v in json.loads(os.environ.get("TP_CREDENTIALS", "{}")).items():
        user = v.get("username") or os.environ.get("DEFAULT_USERNAME") or ""
        pw = v.get("password")
        if pw is None:
            pw = os.environ.get("DEFAULT_PASSWORD") or ""
        if not user:
            log("no credentials for %s; skipping" % key)
            continue
        n = norm_mac(key)
        if n not in seen:
            seen.add(n)
            entries.append([key, user, pw, 0])
    return entries


def discover_extras(known):
    if os.environ.get("DISCOVER") != "1":
        return []
    from discovery import discover_switches, InterfaceProblem
    for iface in candidates():
        try:
            found = discover_switches(iface)
        except (InterfaceProblem, OSError):
            found = []
        if found:
            break
    extras = []
    for host_ip, host_mac, header, payload in found:
        sw = {name: value for id_, name, value in payload}
        mac = sw.get("mac")
        if not mac or norm_mac(mac) in known:
            continue
        user = os.environ.get("DEFAULT_USERNAME", "")
        if not user:
            continue
        log("discovered unlisted switch %s (%s)" % (mac, sw.get("hostname", "?")))
        extras.append([mac, user, os.environ.get("DEFAULT_PASSWORD", ""), 0])
        known.add(norm_mac(mac))
    return extras


def send_wave(net, entries, op_code, make_payload):
    """Send one request per switch and collect replies, demuxed by
    (switch mac, sequence id). Returns {normmac: (header, payload)}."""
    outstanding = {}
    for e in entries:
        net.header["switch_mac"] = mac_to_bytes(e[0])
        net.header["token_id"] = e[3] or 0
        net.send(op_code, make_payload(e))
        outstanding[(net.header["switch_mac"], net.sequence_id)] = e
    got = {}
    net.rs.settimeout(2.0)
    deadline = time.time() + 2.0
    while outstanding and time.time() < deadline:
        try:
            data, addr = net.rs.recvfrom(1500)
        except OSError:
            break
        if data in net.seen:
            continue
        net.seen.add(data)
        try:
            header, payload = Protocol.analyze(Protocol.decode(data))
        except Exception:
            continue
        entry = outstanding.pop((header["switch_mac"], header["sequence_id"]), None)
        if entry is not None:
            got[norm_mac(entry[0])] = (header, payload)
    return got


def encode_remaining_length(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            return bytes(out)


def mqtt_publish(pairs, host, port, username, password, qos, retain):
    """Minimal MQTT 3.1.1 client: one connection, publish every message,
    then DISCONNECT (this broker only sends QoS1 PUBACKs after DISCONNECT)."""
    import socket
    s = socket.create_connection((host, int(port)), timeout=10)

    # CONNECT: MQTT v3.1.1, clean session, keepalive 60, no client id
    flags = 0x02
    if username:
        flags |= 0x80
    if password:
        flags |= 0x40
    payload = b"\x00\x04MQTT\x04" + bytes([flags]) + b"\x00\x3c" + b"\x00\x00"
    if username:
        u = username.encode()
        payload += bytes([0x00, len(u)]) + u
    if password:
        p = password.encode()
        payload += bytes([0x00, len(p)]) + p
    s.sendall(bytes([0x10, len(payload)]) + payload)
    s.recv(4)  # CONNACK

    mid = 0
    for topic, message in pairs:
        mid = (mid + 1) % 65536
        body = bytes([0x00, len(topic)]) + topic.encode()
        if qos > 0:
            body += bytes([mid >> 8, mid & 0xFF])
        body += message.encode()
        s.sendall(bytes([0x30 | (qos << 1) | (1 if retain else 0)]) + encode_remaining_length(len(body)) + body)

    s.sendall(b"\xe0\x00")  # DISCONNECT
    if qos > 0:
        s.settimeout(2)
        while True:
            try:
                if not s.recv(4):
                    break
            except OSError:
                break
    s.close()


def publish(pairs):
    """One message per port, keeping the <base>/<mac>/stats/<port> topic
    contract. Payload is a single-line JSONL object (JSON + trailing
    newline), parseable by both JSON and JSONL consumers. pairs: list of
    (mac, stats-row-dict); all messages go over one MQTT connection."""
    base = os.environ.get("MQTT_TOPIC_BASE", "smrt")
    msgs = [("%s/%s/stats/%s" % (base, mac, row["port"]), json.dumps(row) + "\n")
            for mac, row in pairs]
    if not msgs:
        log("nothing to publish")
        return
    host = os.environ.get("MQTT_HOST", "")
    if not host:
        for topic, message in msgs:
            log("dry-run: %s %s" % (topic, message.strip()))
        log("dry-run: %d messages (MQTT_HOST unset)" % len(msgs))
        return
    try:
        mqtt_publish(msgs, host,
                     os.environ.get("MQTT_PORT", "1883"),
                     os.environ.get("MQTT_USERNAME", ""),
                     os.environ.get("MQTT_PASSWORD", ""),
                     int(os.environ.get("MQTT_QOS", "1")),
                     os.environ.get("MQTT_RETAIN", "0") == "1")
        log("published %d messages" % len(msgs))
    except OSError as e:
        log("publish failed: %s" % e)


def main():
    lock = os.path.join(os.environ.get("TMPDIR", "/tmp"), "smrt-runner.lock")
    try:
        os.mkdir(lock)
    except FileExistsError:
        log("smrt-runner: tick already running, skipping")
        return 0
    try:
        return tick()
    finally:
        os.rmdir(lock)


def tick():
    entries = load_creds()
    entries += discover_extras({norm_mac(e[0]) for e in entries})
    if not entries:
        log("no switches configured (TP_CREDENTIALS); nothing to do")
        return 1

    ip, mac = host_addr()
    if not ip:
        log("no usable interface found")
        return 1
    net = Network(ip, mac)

    log("querying %d switch(es)..." % len(entries))

    # wave 1: token requests
    got = send_wave(net, entries, Protocol.GET, lambda e: [(Protocol.get_id("get_token_id"), b"")])
    ready = []
    for e in entries:
        if norm_mac(e[0]) in got:
            e[3] = got[norm_mac(e[0])][0]["token_id"]
            ready.append(e)
        else:
            log("no token reply from %s; skipping" % mac_to_str(mac_to_bytes(e[0])))

    # wave 2: logins
    def login_payload(e):
        return [(Protocol.get_id("username"), e[1].encode("ascii") + b"\x00"),
                (Protocol.get_id("password"), e[2].encode("ascii") + b"\x00")]
    got2 = send_wave(net, ready, Protocol.LOGIN, login_payload)
    authed = []
    for e in ready:
        n = norm_mac(e[0])
        if n not in got2:
            log("no login reply from %s; skipping" % mac_to_str(mac_to_bytes(e[0])))
        elif got2[n][0]["error_code"] != 0:
            log("login rejected for %s (error %d); skipping"
                % (mac_to_str(mac_to_bytes(e[0])), got2[n][0]["error_code"]))
        else:
            authed.append(e)

    # wave 3: stats queries
    got3 = send_wave(net, authed, Protocol.GET, lambda e: [(Protocol.get_id("stats"), b"")])
    pairs = []
    for e in authed:
        n = norm_mac(e[0])
        if n not in got3:
            log("no stats reply from %s" % mac_to_str(mac_to_bytes(e[0])))
            continue
        macstr = mac_to_str(mac_to_bytes(e[0]))
        for id_, name, row in got3[n][1]:
            if row.get("rx_good", 0) > 0 or row.get("tx_good", 0) > 0:
                pairs.append((macstr, row))

    publish(pairs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
