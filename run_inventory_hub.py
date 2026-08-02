"""Run Inventory Hub and advertise InventoryHub.local without external mDNS binaries."""

import socket
import struct
import threading

from asset_manager.app import create_app


def local_ipv4_addresses():
    addresses = set()
    for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = entry[4][0]
        if not address.startswith("127."):
            addresses.add(address)
    return sorted(addresses)


def encode_name(name):
    return b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.rstrip(".").split(".")) + b"\0"


def decode_name(data, offset):
    labels = []
    jumped = False
    next_offset = offset
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset += 1
            return ".".join(labels), next_offset if jumped else offset
        if length & 0xC0 == 0xC0:
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        offset += 1
        labels.append(data[offset : offset + length].decode("ascii", errors="ignore"))
        offset += length


class MdnsResponder:
    """Minimal responder for A-record mDNS lookups of the Inventory Hub host."""

    multicast_address = ("224.0.0.251", 5353)

    def __init__(self, hostname, address):
        self.hostname = hostname.rstrip(".").lower()
        self.address = address
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(("", 5353))
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton("224.0.0.251") + socket.inet_aton("0.0.0.0"))
        self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)

    def _answer(self, query_id=b"\0\0"):
        return (
            query_id
            + struct.pack("!HHHHH", 0x8400, 0, 1, 0, 0)
            + encode_name(self.hostname)
            + struct.pack("!HHIH", 1, 0x8001, 120, 4)
            + socket.inet_aton(self.address)
        )

    def serve(self):
        self.socket.sendto(self._answer(), self.multicast_address)
        while True:
            data, source = self.socket.recvfrom(9000)
            if len(data) < 12:
                continue
            question_count = struct.unpack("!H", data[4:6])[0]
            offset = 12
            for _ in range(question_count):
                name, offset = decode_name(data, offset)
                if offset + 4 > len(data):
                    break
                question_type, _ = struct.unpack("!HH", data[offset : offset + 4])
                offset += 4
                if name.lower() == self.hostname and question_type in {1, 255}:
                    self.socket.sendto(self._answer(data[:2]), source)
                    break


def main():
    app = create_app()
    hostname = app.config["INVENTORY_HOSTNAME"]
    addresses = local_ipv4_addresses()
    if not addresses:
        raise RuntimeError("No local network IPv4 address was found for mDNS advertising.")
    responder = MdnsResponder(hostname, addresses[0])
    threading.Thread(target=responder.serve, name="inventory-hub-mdns", daemon=True).start()
    app.run(host="0.0.0.0", port=app.config["INVENTORY_PORT"], debug=False)


if __name__ == "__main__":
    main()
