# server.py
import socket
import threading
import logging
import json
import os

class Server:
    def __init__(self):
        self.registered_peers = {}
        self.peer_lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Single socket for both send and receive
        self.server_file = "server.json"
        self.active_requests = {}
        # Load server state from the file, if it exists
        self.load_server_state()

    def load_server_state(self):
        """Load registered peers and active requests from server.json."""
        if os.path.exists(self.server_file):
            with open(self.server_file, "r") as file:
                data = json.load(file)
                self.registered_peers = data.get("registered_peers", {})
                self.active_requests = data.get("active_requests", {})
        else:
            self.registered_peers = {}
            self.active_requests = {}

    def save_server_state(self):
        """Save registered peers and active requests to server.json."""
        with open(self.server_file, "w") as file:
            json.dump({"registered_peers": self.registered_peers, "active_requests": self.active_requests}, file, indent=4)

    def udp_listener(self):
        server_ip = get_server_ip()
        print(f"Server is running on {server_ip}, listening on UDP port 5000")
        self.server_socket.bind((server_ip, 5000))
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
            # Add the request to active_requests
            self.active_requests[rq_number] = {'name': name, 'operation': 'REGISTER', 'status': 'Processing'}
            self.save_server_state()  # Save the new request to requests.json

            if name in self.registered_peers:
                response = f"REGISTER-DENIED {rq_number} Name already in use"
                self.active_requests[rq_number]['status'] = 'Failed'
            else:
                self.registered_peers[name] = {"rq_number": rq_number, 'udp_socket': udp_socket, 'tcp_socket': tcp_socket,'address': addr}
                response = f"REGISTERED {rq_number}"
                self.active_requests[rq_number]['status'] = 'Completed'
            self.save_server_state()  # Update the request status in requests.json

        self.send_udp_response(response, addr)

    def handle_deregister(self, message_parts, addr):
        rq_number = message_parts[1]
        name = message_parts[2]

        with self.peer_lock:
            # Add the request to active_requests
            self.active_requests[rq_number] = {'name': name, 'operation': 'DE-REGISTER', 'status': 'Processing'}
            self.save_server_state()

            if name in self.registered_peers:
                del self.registered_peers[name]
                # Remove all requests ever made by this peer
                self.active_requests = {
                    rq: details for rq, details in self.active_requests.items() if details['name'] != name
                }
                response = f"DE-REGISTERED {rq_number}"
            else:
                response = f"DE-REGISTER-DENIED {rq_number} Name not found"
                self.active_requests[rq_number]['status'] = 'Failed'
            self.save_server_state()  # Update the request status in requests.json

        self.send_udp_response(response, addr)

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

def get_server_ip():
    """Determine the server's network IP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # Connect to a public IP to determine local network IP
        return s.getsockname()[0]



if __name__ == "__main__":
    server = Server()
    server.start()


