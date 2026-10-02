# smrt

A utility to configure your TP-Link Easy Smart Switch
on Linux or Mac OS X. This tool is written in Python.

Supposedly supported switches:

* TL-SG105E (tested)
* TL-SG108E (tested)
* TL-SG108PE
* TL-SG1016DE
* TL-SG1024DE

## Discover switches

### Simple discovery

```
$ ./discovery.py
```

### Multiple interfaces

If more than one interface, error message gives the list:

```
Error: more than 1 interface. Use -i or --interface to specify the name
Interfaces:
    'enp3s0'
    'virbr0'
    'virbr0-nic'
```

### Default output

Give the right interface:
```
$ ./discovery.py -i enp3s0
```

Output (found 2 switches) is JSON:
```
[
  {
    "host_ip": "192.168.9.36",
    "host_mac": "ba:ff:ee:ff:ac:ee",
    "switch": {
      "type": "TL-SG108E",
      "hostname": "sg108ev4",
      "mac": "01:01:01:01:01:01",
      "firmware": "1.0.0 Build 20181120 Rel.40749",
      "hardware": "TL-SG108E 4.0",
      "dhcp": false,
      "ip_addr": "192.168.9.202",
      "ip_mask": "255.255.255.0",
      "gateway": "192.168.9.1",
      "v4": true
    }
  },
  {
    "host_ip": "192.168.9.36",
    "host_mac": "ba:ff:ee:ff:ac:ee",
    "switch": {
      "type": "TL-SG108E",
      "hostname": "sg108ev1",
      "mac": "02:02:02:02:02:02",
      "firmware": "1.1.2 Build 20141017 Rel.50749",
      "hardware": "TL-SG108E 1.0",
      "dhcp": false,
      "ip_addr": "192.168.9.203",
      "ip_mask": "255.255.255.0",
      "gateway": "192.168.9.1",
      "v4": true
    }
  }
]
```

### Command output with -c

With switch `-c` or `--command`, each switch entry gets a `command` field with the syntax for using smrt with right arguments

```
$ ./discovery.py -i enp3s0 -c
[
  {
    "host_ip": "192.168.9.36",
    "host_mac": "ba:ff:ee:ff:ac:ee",
    "switch": {
      "type": "TL-SG108E",
      "hostname": "sg108ev4",
      "mac": "01:01:01:01:01:01",
      ...
    },
    "command": "./smrt.py --username admin --password admin --host-mac=ba:ff:ee:ff:ac:ee --ip-address=192.168.9.36 --switch-mac 01:01:01:01:01:01"
  },
  ...
]
```

### Alias

After discovery, setting an shell alias reduces command size

```
$ alias smrt='python ~/smrt/smrt.py --switch-mac 60:E3:27:83:25:3F  --ip-address 192.168.9.36 --host-mac=ba.ff.ee.ff.ac.ee  --username admin --password admin'
```

## smrt.py

### without command gives list of command

```
$ ./smrt.py --username admin --password admin --host-mac=ba.ff.ee.ff.ac.ee --ip-address=192.168.9.36 --switch-mac 01:01:01:01:01:01
{
  "actions": [
    "type",
    "hostname",
    "mac",
    "ip_addr",
    "ip_mask",
    "gateway",
    ...
  ]
}
```

Note: not all actions are of interest. Some TP-link code (13: "v4", 14: "v6", 8707: "vlan_filler") correspond to unknown codes but are presents in output, so must be presents in code/command list.

### vlan

```
$ smrt vlan # use alias

{
  "vlan_enabled": "01",
  "vlan": [
    {"vlan": 1, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "Default_VLAN"},
    {"vlan": 90, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "LAN"},
    {"vlan": 100, "members": "1,2,3", "tagged": "1", "name": "vlan_test_1"}
  ]
}
```

### pvid

```
$ smrt pvid
[
  {"port": 1, "pvid": 90},
  {"port": 2, "pvid": 90},
  {"port": 3, "pvid": 90},
  {"port": 4, "pvid": 90},
  {"port": 5, "pvid": 90},
  {"port": 6, "pvid": 90},
  {"port": 7, "pvid": 90},
  {"port": 8, "pvid": 90}
]
```

### stats

```
$ smrt stats
[
  {"port": 1, "status": "enabled", "speed": 1000, "duplex": "full", "tx_good": 48, "tx_bad": 0, "rx_good": 6356, "rx_bad": 14},
  {"port": 2, "status": "enabled", "speed": 0, "duplex": "none", "tx_good": 0, "tx_bad": 0, "rx_good": 0, "rx_bad": 0},
  {"port": 3, "status": "enabled", "speed": 0, "duplex": "none", "tx_good": 0, "tx_bad": 0, "rx_good": 0, "rx_bad": 0},
  {"port": 4, "status": "enabled", "speed": 100, "duplex": "full", "tx_good": 6404, "tx_bad": 0, "rx_good": 0, "rx_bad": 14},
  ...
]
```

Counter fields are unsigned packet counters (they wrap at 2^32). `status` is the port admin state (enabled/disabled), not link state. `speed` is the negotiated link speed in Mbps (0 = no link); `duplex` is "full", "half", or "none".

### smrt ports

```
$ smrt ports
[
  {"port": 1, "status": "enabled", "lag": 0, "speed_configured": null, "duplex_configured": null, "speed_actual": 1000, "duplex_actual": "full", "flow_control_configured": "off", "flow_control_actual": "off"},
  {"port": 2, "status": "enabled", "lag": 0, "speed_configured": null, "duplex_configured": null, "speed_actual": 0, "duplex_actual": "none", "flow_control_configured": "off", "flow_control_actual": "off"},
  {"port": 3, "status": "enabled", "lag": 0, "speed_configured": null, "duplex_configured": null, "speed_actual": 0, "duplex_actual": "none", "flow_control_configured": "off", "flow_control_actual": "off"},
  ...
]
```

`speed_configured`/`duplex_configured` are null when the port is set to Auto; `speed_actual`/`duplex_actual` use the same codes as stats. Flow control: off/on.
## Set VLAN settings

### Syntax

`smrt.py` shows parameters and can change them for VLANs if `--vlan` is present

Specific VLAN parameters:

* `--vlan`: vlan number (1-4093)
* `--vlan_name`: acceptable vlan name for TP-Link switch 
* `--vlan_member`: comma separated list without space of member ports. Ex: 1,2,4
* `--vlan_tagged`: comma separated list without space of tagged ports. Ex: 1,2
* `--vlan_pvid`: set pvid to `--vlan` for given ports

### Example 1 : add new vlan 120

```
$ smrt vlan
{
  "vlan_enabled": "01",
  "vlan": [
    {"vlan": 1, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "Default_VLAN"},
    {"vlan": 90, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "LAN"},
    {"vlan": 100, "members": "1,2,3", "tagged": "1", "name": "vlan_test_1"}
  ]
}
$ smrt --vlan 120 --vlan_name "vlan_test_2" --vlan_member 1,4,5,6 --vlan_tagged 1
{
  "vlan_enabled": "01",
  "vlan": [
    {"vlan": 1, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "Default_VLAN"},
    {"vlan": 90, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "LAN"},
    {"vlan": 100, "members": "1,2,3", "tagged": "1", "name": "vlan_test_1"},
    {"vlan": 120, "members": "1,4,5,6", "tagged": "1", "name": "vlan_test_2"}
  ]
}
```

### Example 2 : change to pvid 120 for ports 5 and 6

Note : vlan must exist (see example 1) before this command.

```
$ smrt pvid
[
  {"port": 1, "pvid": 90},
  {"port": 2, "pvid": 90},
  {"port": 3, "pvid": 90},
  {"port": 4, "pvid": 90},
  {"port": 5, "pvid": 90},
  {"port": 6, "pvid": 90},
  {"port": 7, "pvid": 90},
  {"port": 8, "pvid": 90}
]
$ smrt --vlan 120 --vlan_pvid 5,6
[
  {"port": 1, "pvid": 90},
  {"port": 2, "pvid": 90},
  {"port": 3, "pvid": 90},
  {"port": 4, "pvid": 90},
  {"port": 5, "pvid": 120},
  {"port": 6, "pvid": 120},
  {"port": 7, "pvid": 90},
  {"port": 8, "pvid": 90}
]
```

### Exemple 3 : remove vlan 120

```
$ smrt --vlan 120 --delete
{
  "vlan_enabled": "01",
  "vlan": [
    {"vlan": 1, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "Default_VLAN"},
    {"vlan": 90, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "LAN"},
    {"vlan": 100, "members": "1,2,3", "tagged": "1", "name": "vlan_test_1"}
  ]
}
```

Note that, for PVID, corresponding ports are reinitialized to vlan 1:
```
$ smrt pvid
[
  {"port": 1, "pvid": 90},
  {"port": 2, "pvid": 90},
  {"port": 3, "pvid": 90},
  {"port": 4, "pvid": 90},
  {"port": 5, "pvid": 1},
  {"port": 6, "pvid": 1},
  {"port": 7, "pvid": 90},
  {"port": 8, "pvid": 90}
]
```

### Exemple 4 : add new vlan and pvid

```
$ smrt --vlan 130 --vlan_name "vlan_test_3" --vlan_member 1,4,5,6 --vlan_tagged 1 --vlan_pvid 4,5,6
{
  "vlan_enabled": "01",
  "vlan": [
    {"vlan": 1, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "Default_VLAN"},
    {"vlan": 90, "members": "1,2,3,4,5,6,7,8", "tagged": "", "name": "LAN"},
    {"vlan": 100, "members": "1,2,3", "tagged": "1", "name": "vlan_test_1"},
    {"vlan": 130, "members": "1,4,5,6", "tagged": "1", "name": "vlan_test_3"}
  ],
  "pvid": [
    {"port": 1, "pvid": 90},
    {"port": 2, "pvid": 90},
    {"port": 3, "pvid": 90},
    {"port": 4, "pvid": 130},
    {"port": 5, "pvid": 130},
    {"port": 6, "pvid": 130},
    {"port": 7, "pvid": 90},
    {"port": 8, "pvid": 90}
  ]
}
```
