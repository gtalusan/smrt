#!/usr/bin/env python3

import random
import logging
import argparse
import json
import sys
import ifaces

from protocol import Protocol
from network import Network, ConnectionProblem
from loglevel import loglevel

logger = logging.getLogger(__name__)

class InterfaceProblem(Exception):
    pass

def discover_switches(interface=None):
    if interface is None:
        interfaces = [i for i in ifaces.interfaces() if not i.startswith('lo')]
        if len(interfaces) > 1:
            msg = ["more than 1 interface. Use -i or --interface to specify the name"]
            msg.append("Interfaces:")
            for iface in interfaces:
                msg.append("    " + repr(iface))
            raise InterfaceProblem("\n".join(msg))

    settings = []
    addrs = ifaces.ifaddresses(interface)
    logger.debug("addrs:" + repr(addrs))
    if ifaces.AF_INET not in addrs:
        raise InterfaceProblem("not AF_INET address")
    if ifaces.AF_LINK not in addrs:
        raise InterfaceProblem("not AF_LINK address")

    mac = addrs[ifaces.AF_LINK][0]['addr']
    # take first address of interface
    addr = addrs[ifaces.AF_INET][0]
    if 'broadcast' not in addr or 'addr' not in addr:
        raise InterfaceProblem("no addr or broadcast for address")
    ip = addr['addr']

    net = Network(ip, mac)
    logger.debug((interface, ip, mac))
    net.send(Protocol.DISCOVERY, {})
    ret = []
    while True:
        try:
            header, payload = net.receive()
            ret.append((ip, mac, header, payload))
        except ConnectionProblem:
            break
    return ret

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interface', '-i')
    parser.add_argument('--command', '-c', action="store_true")
    parser.add_argument('--loglevel', '-l', type=loglevel, default='INFO')
    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    try:
        switches = discover_switches(args.interface)
    except InterfaceProblem as e:
        print("Error:", e, file=sys.stderr)
        sys.exit(1)
    else:
        results = []
        for ip, mac, header, payload in switches:
            entry = {
                'host_ip': ip,
                'host_mac': mac,
                'switch': {name: value for id, name, value in payload},
            }
            if args.command:
                p = entry['switch']
                entry['command'] = f"./smrt.py --username admin --password admin --host-mac={mac} --ip-address={ip} --switch-mac {p['mac']}"
            results.append(entry)
        print(json.dumps(results, indent=2, default=str))

if __name__ == "__main__":
    main()
