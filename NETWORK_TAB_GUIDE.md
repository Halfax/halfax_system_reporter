# Network Tab - Quick Reference & Examples

## What You'll See

### Section 1: WiFi Networks Available
Shows all discovered WiFi networks on the system:
```
WIFI NETWORKS AVAILABLE:
  Network: SpectrumSetup-7E
    Interface:  Wireless Network Connection
    Signal:     95%
    Security:   WPA2-Personal
    Status:     🟢 CONNECTED

  Network: GuestNetwork
    Interface:  Wireless Network Connection
    Signal:     75%
    Security:   WPA2-Personal
    Status:     
```

**Information Provided:**
- Network name (SSID)
- WiFi adapter interface name
- Current signal strength percentage
- Security protocol in use
- Whether you're currently connected to it

---

### Section 2: Gateway Information
Shows the default gateway(s) for your network:
```
GATEWAY INFORMATION:
  Gateway:    192.168.1.1
    Interfaces: 2
```

**Information Provided:**
- IP address of the network gateway
- How many network adapters are using this gateway

---

### Section 2.5: Router Scan (UPnP/SSDP)

This optional, read-only utility performs a safe UPnP/SSDP discovery of devices on your local network (for example, routers and other UPnP-enabled appliances). The app will ask for confirmation before scanning.

Notes:
- Uses the optional Python package `miniupnpc` when available. If not installed the UI will display a message explaining the missing dependency and how to enable discovery.
- No elevated privileges are required; the scan performs only local network SSDP discovery.

Example usage:
```
Click "Router Scan" → Confirm → View list of discovered UPnP devices (Model, Location, UDN)
```

---

### Section 3: DNS Servers
Shows all DNS servers configured on your system:
```
DNS SERVERS:
  DNS 1: 8.8.8.8
  DNS 2: 8.8.4.4
  DNS 3: 1.1.1.1
```

**Information Provided:**
- IP addresses of all configured DNS servers
- Order of DNS resolution (primary, secondary, etc.)

---

### Section 4: DHCP Configuration
Shows which adapters have DHCP enabled:
```
DHCP CONFIGURATION:
  Ethernet:
    DHCP: Yes
  WiFi:
    DHCP: Yes
```

**Information Provided:**
- Adapter name
- Whether DHCP is enabled (automatic IP assignment)

---

### Section 5: Network Adapter Configuration
Detailed configuration of each network adapter:
```
NETWORK ADAPTER CONFIGURATION:

  Adapter 1: Realtek PCIe GbE Family Controller
    MAC Address:  00-1F-29-6B-F3-5A
    DHCP Enabled: True
    IP Addresses: 192.168.1.100, fe80::14bf:1c2d:82b6:1fa8%10
    Gateways:     192.168.1.1
    DNS Servers:  8.8.8.8, 8.8.4.4, 1.1.1.1

  Adapter 2: Intel(R) Wireless-AC 9462
    MAC Address:  8C-DC-D4-A6-B3-2C
    DHCP Enabled: True
    IP Addresses: 192.168.1.102
    Gateways:     192.168.1.1
    DNS Servers:  8.8.8.8, 8.8.4.4
```

**Information Provided:**
- Hardware device name and manufacturer
- Physical MAC address (hardware identifier)
- Whether adapter uses DHCP for IP assignment
- Assigned IP addresses (both IPv4 and IPv6)
- Network gateways used by this adapter
- DNS servers assigned to this adapter

---

### Section 6: Network Interfaces
Detailed status of each physical/virtual network interface:
```
NETWORK INTERFACES: 4

  Ethernet 🟢 UP
    Speed:       1000 Mbps
    MTU:         1500
    Type:        Ethernet
    MAC:         00-1F-29-6B-F3-5A
    Description: Realtek PCIe GbE Family Controller
    IP Addresses:
      IPv4   192.168.1.100
             Netmask: 255.255.255.0
      IPv6   fe80::14bf:1c2d:82b6:1fa8%10

  WiFi 🟢 UP
    Speed:       433 Mbps
    MTU:         1500
    Type:        Ethernet
    MAC:         8C-DC-D4-A6-B3-2C
    Description: Intel(R) Wireless-AC 9462
    IP Addresses:
      IPv4   192.168.1.102
             Netmask: 255.255.255.0
      IPv6   fe80::1847:8f14:f4a2:b34b%12

  Loopback 🟢 UP
    Speed:       Unknown
    MTU:         16436
    Type:        Loopback
    IP Addresses:
      IPv4   127.0.0.1
             Netmask: 255.0.0.0
      IPv6   ::1

  VirtualBox 🟢 UP
    Speed:       10 Mbps
    MTU:         1500
    Type:        Virtual
    MAC:         08-00-27-00-00-00
    IP Addresses:
      IPv4   192.168.56.1
             Netmask: 255.255.255.0
```

**Information Provided:**
- Interface name
- Connection status (🟢 UP = connected, ⚫ DOWN = disconnected)
- Connection speed in Mbps
- Maximum Transmission Unit (packet size)
- Type of interface (Ethernet, WiFi, Virtual, Loopback)
- MAC address (physical hardware address)
- Device description/driver
- All IP addresses assigned to interface with subnet masks

---

### Section 7: Connection Statistics
Real-time count of active network connections:
```
CONNECTION STATISTICS:
  Active Connections: 47
    Established: 28
    Listening:   8
    Time Wait:   9
    Close Wait:  2
```

**Information Provided:**
- Total active connections
- **Established**: Fully open TCP connections (data transfer)
- **Listening**: Ports listening for incoming connections
- **Time Wait**: Connections waiting for timeout after closure
- **Close Wait**: Connections waiting for client to close

---

### Section 8: Network I/O Statistics
Cumulative network traffic since system boot:
```
NETWORK I/O STATISTICS:
  Bytes Sent:      3,456,789,012
  Bytes Received:  12,345,678,901
  Packets Sent:    2,345,678
  Packets Recv:    4,567,890
  Errors In:       0
  Errors Out:      0
  Dropped In:      0
  Dropped Out:     0
```

**Information Provided:**
- Total bytes sent/received (cumulative)
- Total packets sent/received (cumulative)
- Transmission errors in/out
- Dropped packets in/out (indicates problems)

---

## Status Indicators

| Symbol | Meaning |
|--------|---------|
| 🟢 UP | Interface is active and connected |
| ⚫ DOWN | Interface is disabled or disconnected |
| 🟢 CONNECTED | WiFi network is currently connected |
| No symbol | Status unknown or not applicable |

---

## Common Questions & Answers

**Q: What does "Speed: Unknown" mean?**  
A: The operating system cannot determine the connection speed. This is normal for virtual interfaces or loopback adapters.

**Q: Why do I see multiple IP addresses?**  
A: Modern systems often have both IPv4 and IPv6 addresses. IPv6 addresses starting with `fe80::` are link-local addresses (automatic, not internet-routable).

**Q: What is the difference between Established and Listening connections?**  
A: Established connections are active data transfers. Listening connections are waiting for incoming requests (like a web server waiting for browser connections).

**Q: Why is MTU 1500?**  
A: 1500 is the standard MTU (Maximum Transmission Unit) for Ethernet networks. Loopback adapters often use 16436.

**Q: What does "Time Wait" mean?**  
A: After TCP connection closes, the OS waits briefly to ensure all packets have been received. These are connections in that waiting state.

**Q: How often is this data updated?**  
A: Data is refreshed when you click "Refresh All" or when you switch tabs. It does not update automatically in real-time.

**Q: What if I see 0 for DNS Servers?**  
A: Your system may be using DHCP-assigned DNS servers, or your DNS configuration is automatic. The tab shows explicitly configured servers.

---

## Troubleshooting

**WiFi section is empty:**
- Your system may not have WiFi hardware
- WiFi may be disabled
- On Linux, `iwconfig` command may not be installed

**DHCP Configuration section is missing:**
- Your network adapters may all use static IP addresses
- This is normal and not a problem

**Some fields show "Unknown":**
- The information may not be available on your system
- Virtual interfaces may not support all properties
- This is expected and not a problem

**Connection Statistics shows 0:**
- No active network connections
- All connections have been closed
- This is normal on a freshly restarted system

---

## What's NOT Shown

This Network tab focuses on configuration and discovery. It does NOT show:
- ❌ Bandwidth usage per application
- ❌ Real-time traffic graphs
- ❌ ARP cache or nearby devices
- ❌ Firewall rules
- ❌ VPN configuration
- ❌ Proxy settings
- ❌ Network shares
- ❌ Packet captures

---

## Tips & Tricks

1. **Find your IP address** - Look in the "Network Interfaces" section under your active adapter (Ethernet or WiFi)
2. **Find your gateway** - Look in "Gateway Information" section
3. **Check DNS configuration** - Look in "DNS Servers" section
4. **See WiFi signal strength** - Look in "WiFi Networks Available" section
5. **Monitor network errors** - Look in "Network I/O Statistics" for Errors In/Out
6. **Count active services** - Look in "Connection Statistics" Listening count
7. **Check total data transferred** - Look in "Network I/O Statistics" for Bytes Sent/Received

