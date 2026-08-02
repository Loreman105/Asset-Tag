"""Run Inventory Hub and advertise it as InventoryHub.local on the LAN."""

import socket

from zeroconf import ServiceInfo, Zeroconf

from asset_manager.app import create_app


def local_ipv4_addresses():
    """Find usable LAN addresses without publishing the loopback interface."""
    addresses = set()
    for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = entry[4][0]
        if not address.startswith("127."):
            addresses.add(address)
    return [socket.inet_aton(address) for address in addresses]


def main():
    app = create_app()
    hostname = app.config["INVENTORY_HOSTNAME"].rstrip(".")
    port = app.config["INVENTORY_PORT"]
    info = ServiceInfo(
        "_http._tcp.local.",
        f"{hostname.split('.')[0]}._http._tcp.local.",
        addresses=local_ipv4_addresses(),
        port=port,
        properties={"path": "/"},
        server=f"{hostname}.",
    )
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        zeroconf.unregister_service(info)
        zeroconf.close()


if __name__ == "__main__":
    main()
