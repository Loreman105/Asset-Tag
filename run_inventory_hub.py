"""Run Inventory Hub and advertise InventoryHub.local over mDNS."""

import socket

from zeroconf import IPVersion, ServiceInfo, Zeroconf

from asset_manager.app import create_app


def local_ipv4_addresses():
    """Return the LAN IPv4 addresses that should be advertised over mDNS."""
    addresses = set()
    for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = entry[4][0]
        if not address.startswith("127."):
            addresses.add(address)
    return sorted(addresses)


def register_mdns(hostname, addresses, port):
    """Advertise the HTTP service and its A record using standard mDNS."""
    hostname = hostname.rstrip(".")
    service_info = ServiceInfo(
        type_="_http._tcp.local.",
        name=f"Inventory Hub._http._tcp.local.",
        server=f"{hostname}.",
        port=port,
        properties={"path": "/"},
        parsed_addresses=addresses,
    )
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    zeroconf.register_service(service_info, allow_name_change=False)
    return zeroconf, service_info


def main():
    app = create_app()
    hostname = app.config["INVENTORY_HOSTNAME"]
    addresses = local_ipv4_addresses()
    if not addresses:
        raise RuntimeError("No local network IPv4 address was found for mDNS advertising.")

    zeroconf, service_info = register_mdns(hostname, addresses, app.config["INVENTORY_PORT"])
    print(f"mDNS advertising {hostname} at {', '.join(addresses)}")
    try:
        app.run(host="0.0.0.0", port=app.config["INVENTORY_PORT"], debug=False)
    finally:
        zeroconf.unregister_service(service_info)
        zeroconf.close()


if __name__ == "__main__":
    main()
