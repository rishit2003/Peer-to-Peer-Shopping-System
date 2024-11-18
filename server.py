# server.py
import socket
import threading
import logging

class Server:
    def __init__(self):
        self.registered_peers = {}
        self.peer_lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Single socket for both send and receive
        self.file_name = "server.txt"

    def udp_listener(self):
        self.server_socket.bind(('localhost', 5000))
        logging.info("Server started, listening on UDP port 5000...")

        while True:
            data, addr = self.server_socket.recvfrom(1024)
            threading.Thread(target=self.handle_udp_message, args=(data, addr)).start()

    def handle_udp_message(self, data, addr):
        message = data.decode()
        message_parts = message.split()
        msg_type = message_parts[0]

        if msg_type == "REGISTER":
            self.handle_register(message_parts, addr)
        elif msg_type == "DE-REGISTER":
            self.handle_deregister(message_parts, addr)
        elif msg_type == "LOOKING_FOR":
            self.handle_search(message_parts, addr)
        elif msg_type == "OFFER":
            self.handle_offer(message_parts, addr)
        else:
            logging.warning(f"Unknown message type from {addr}: {message}")

    def handle_register(self, message_parts, addr):
        rq_number = message_parts[1]
        name = message_parts[2]
        udp_socket = message_parts[4]
        tcp_socket = message_parts[5]

        with self.peer_lock:
            if name in self.registered_peers:
                response = f"REGISTER-DENIED {rq_number} Name already in use"
            else:
                self.registered_peers[name] = {'address': addr, 'udp_socket': udp_socket, 'tcp_socket': tcp_socket}
                self.update_peer_file()  # Update the file to include the new registration
                response = f"REGISTERED {rq_number}"
        self.send_udp_response(response, addr)

    def handle_deregister(self, message_parts, addr):
        rq_number = message_parts[1]
        name = message_parts[2]

        with self.peer_lock:
            if name in self.registered_peers:
                del self.registered_peers[name]
                self.update_peer_file()  # Update the file to reflect the deregistration
                response = f"DE-REGISTERED {rq_number}"
            else:
                response = f"DE-REGISTER-DENIED {rq_number} Name not found"
        self.send_udp_response(response, addr)

    def update_peer_file(self):
        """Writes the current list of registered peers to the server.txt file."""
        with open(self.file_name, "w") as file:  # Overwrite the file with the current state
            for name, details in self.registered_peers.items():
                addr = details['address']
                udp_socket = details['udp_socket']
                tcp_socket = details['tcp_socket']
                file.write(f"{name}, UDP: {udp_socket}, TCP: {tcp_socket}, Address: {addr}\n")

    def handle_search(self, message_parts, addr):
        rq_number = message_parts[1]
        name = message_parts[2]
        item_name = message_parts[3]
        item_description = " ".join(message_parts[4:-1])
        max_price = message_parts[-1]

        with self.peer_lock:
            for peer_name, peer_info in self.registered_peers.items():
                if peer_name != name:
                    search_msg = f"SEARCH {rq_number} {item_name} {item_description} {max_price}"
                    self.send_udp_response(search_msg, peer_info['address'])
                    logging.info(f"SEARCH request from {name} forwarded to {peer_name} for item '{item_name}'")


    def handle_offer(self, message_parts, addr):
        rq_number = message_parts[1]
        seller_name = message_parts[2]
        item_name = message_parts[3]
        price = message_parts[4]

        logging.info(f"Offer received from {seller_name} for item '{item_name}' at price {price}")
        # TODO: Further logic like negotiation to be handled here


    def send_udp_response(self, message, addr):
        with self.peer_lock:
            self.server_socket.sendto(message.encode(), addr)
        logging.info(f"Sent UDP response to {addr}: {message}")

    def start(self):
        threading.Thread(target=self.udp_listener).start()


if __name__ == "__main__":
    server = Server()
    server.start()


