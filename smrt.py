#!/usr/bin/env python3

import socket, time, random, argparse, logging, json, sys

from protocol import Protocol
from network import Network, ConnectionProblem
from binary import ports2byte, ports2list

def loglevel(x):
    try:
        return getattr(logging, x.upper())
    except AttributeError:
        raise argparse.ArgumentError('Select a proper loglevel')

def main():
    logger = logging.getLogger(__name__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--switch-mac', '-s')
    parser.add_argument('--host-mac', )
    parser.add_argument('--ip-address', '-i')
    parser.add_argument('--username', '-u')
    parser.add_argument('--password', '-p')
    parser.add_argument('--vlan', type=int)
    parser.add_argument('--vlan_name')
    parser.add_argument('--vlan_member')
    parser.add_argument('--vlan_tagged')
    parser.add_argument('--vlan_pvid')
    parser.add_argument('--delete', action="store_true")
    parser.add_argument('--loglevel', '-l', type=loglevel, default='INFO')
    parser.add_argument('action', default=None, nargs='?')
    args = parser.parse_args()

    logging.basicConfig(level=args.loglevel)
    net = Network(args.ip_address, args.host_mac, args.switch_mac)
    actions = Protocol.tp_ids

    if args.action not in Protocol.tp_ids and not args.vlan:
            print(json.dumps({'actions': list(actions.keys())}, indent=2))
    else:
        try:
            net.login(args.username, args.password)
            if args.vlan:
                if args.vlan_member or args.vlan_tagged or args.delete:
                    if (args.delete):
                        v = Protocol.set_vlan(int(args.vlan), 0, 0, "")
                    else:
                        v = Protocol.set_vlan(int(args.vlan), ports2byte(args.vlan_member), ports2byte(args.vlan_tagged), args.vlan_name)
                    l = [(actions["vlan"], v)]

                if args.vlan_pvid is not None:
                    l = []
                    for port in ports2list(args.vlan_pvid):
                        if port != 0:
                            l.append( (actions["pvid"], Protocol.set_pvid(args.vlan, port)) )
                header, payload = net.set(args.username, args.password, l)
            elif args.action in actions:
                header, payload = net.query(Protocol.GET, [(actions[args.action], b'')])
        except ConnectionProblem:
            print(json.dumps({'error': 'no reply from switch'}), file=sys.stderr)
            sys.exit(1)
        print(json.dumps(render(payload), indent=2, default=str))

def render(payload):
    # vlan_filler is protocol padding, ignore it
    payload = [entry for entry in payload if entry[1] != 'vlan_filler']
    names = [name for id, name, value in payload]
    # per-port actions: one dict per port, each carrying its port number
    if len(payload) > 1 and all(name == names[0] for name in names):
        return [value for id, name, value in payload]
    # unique or mixed fields: object keyed by field name
    result = {}
    for id, name, value in payload:
        if name not in result:
            result[name] = value
        elif isinstance(result[name], list):
            result[name].append(value)
        else:
            result[name] = [result[name], value]
    return result

if __name__ == "__main__":
    main()
