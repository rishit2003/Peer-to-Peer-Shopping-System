# server.py
import socket
import threading
import logging
import json
import os
import signal
import sys
import time

logging.basicConfig(
    filename="server.log",  # Log to file
    level=logging.INFO,     # Log messages of level INFO and above
    format="%(asctime)s - %(levelname)s - %(message)s"  # Include timestamp and level
)

class Server:
    def __init__(self):
        self.registered_peers = {}
        self.peer_lock = threading.Lock()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Single socket for both send and receive
        self.server_file = "server.json"
        self.active_requests = {}
        # Load server state from the file, if it is not empty
        self.load_server_state()

    def load_server_state(self):
        if os.path.exists(self.server_file):
            try:
                with open(self.server_file, "r") as file:
                    data = json.load(file)
                    self.registered_peers = data.get("registered_peers", {})
                    self.active_requests = data.get("active_requests", {})
                    print(
                        f"Loaded {len(self.registered_peers)} registered peers and {len(self.active_requests)} active requests.")
            except json.JSONDecodeError as e:
                print(f"Error loading server state: {e}. Starting fresh.")
                self.registered_peers = {}
                self.active_requests = {}
        else:
            self.registered_peers = {}
            self.active_requests = {}
            print("No previous state found. Starting fresh.")

    def save_server_state(self):
        """Save registered peers and active requests to server.json."""

        def convert_sets(obj):
            """Helper function to convert sets to lists recursively."""
            if isinstance(obj, set):
                return list(obj)
            if isinstance(obj, dict):
                return {key: convert_sets(value) for key, value in obj.items()}
            if isinstance(obj, list):
                return [convert_sets(element) for element in obj]
            return obj

        data_to_save = {
            "registered_peers": self.registered_peers,
            "active_requests": convert_sets(self.active_requests)
        }
        with open(self.server_file, "w") as file:
            json.dump(data_to_save, file, indent=4)

    def udp_listener(self):
        server_ip = get_server_ip()
        print(f"Server is running on {server_ip}")
        server_udp_port = get_server_udp_port()
        print(f"listening on UDP port {server_udp_port}.")
        self.server_socket.bind((server_ip, server_udp_port))
        logging.info("Server started, listening on UDP port {server_udp_port}...")

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
            self.handle_search(data, addr)
        elif msg_type == "OFFER":
            self.handle_offer(data, addr)
        elif msg_type == "ACCEPT" or msg_type == "REFUSE":
            self.handle_seller_response(message_parts, addr)
        else:
            logging.warning(f"Unknown message type from {addr}: {data.decode()}")

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
        item_description = " ".join(map(str, message_parts[4:-1]))
        max_price = float(message_parts[-1])

        with self.peer_lock:
            # Identify all registered peers except the requester
            expected_sellers = {peer_name for peer_name in self.registered_peers if peer_name != name}

            self.active_requests[rq_number] = {
                'name': name,
                'operation': 'LOOKING_FOR',
                'item_name': item_name,
                'item_description': item_description,
                'max_price': max_price,
                'status': 'Processing',
                'offers': [],
                'start_time': time.time(),
                'timeout': 10,  # Timeout in seconds
                'expected_sellers': expected_sellers,
            }
            self.save_server_state()

            for peer_name, peer_info in self.registered_peers.items():
                if peer_name != name:
                    search_msg = f"SEARCH {rq_number} {item_name} {item_description}"
                    self.send_udp_response(search_msg, peer_info['address'])
                    logging.info(f"SEARCH request from {name} forwarded to {peer_name} for item '{item_name}'")

    def handle_offer(self, message_parts, addr):
        rq_number = message_parts[1]
        seller_name = message_parts[2]
        item_name = message_parts[3]
        price = float(message_parts[4])

        logging.info(f"Offer received from {seller_name} for item '{item_name}' at price {price}")

        with self.peer_lock:
            if rq_number not in self.active_requests:
                response = f"INVALID_RQ {rq_number} Request not found"
                self.send_udp_response(response, addr)
                logging.warning(f"Invalid RQ number in offer: {rq_number}")
                return

            # Add the offer to the list of offers for this request
            buyer_request = self.active_requests[rq_number]
            buyer_request['offers'].append({'seller_name': seller_name, 'price': price, 'address': addr})
            self.save_server_state()

            # Check if all expected sellers have responded or if the timeout has expired
            start_time = buyer_request['start_time']
            elapsed_time = time.time() - start_time
            expected_sellers = buyer_request['expected_sellers']
            received_sellers = {offer['seller_name'] for offer in buyer_request['offers']}

            if elapsed_time >= buyer_request['timeout'] or expected_sellers.issubset(received_sellers):
                # Process the offers after timeout or when all expected responses are received
                offers = buyer_request['offers']
                max_price = float(buyer_request['max_price'])

                if offers:
                    # Filter offers that meet the buyer's max price
                    valid_offers = [offer for offer in offers if offer['price'] <= max_price]

                    if valid_offers:
                        # Find the cheapest valid offer
                        cheapest_offer = min(valid_offers, key=lambda x: x['price'])
                        buyer_name = buyer_request['name']
                        buyer_address = self.registered_peers[buyer_name]['address']

                        # Notify the requester about the cheapest valid offer
                        response_to_buyer = f"FOUND {rq_number} {item_name} {cheapest_offer['price']} from {cheapest_offer['seller_name']}"
                        self.send_udp_response(response_to_buyer, buyer_address)

                        # Update the request status
                        self.active_requests[rq_number]['status'] = 'Completed'
                        self.active_requests[rq_number]['cheapest_offer'] = cheapest_offer
                        self.save_server_state()
                        logging.info(
                            f"Cheapest valid offer for '{item_name}' reserved for {buyer_name} from {cheapest_offer['seller_name']} at price {cheapest_offer['price']}")
                    else:
                        # All offers exceed max price, initiate negotiation with all sellers
                        for offer in offers:
                            negotiate_message = f"NEGOTIATE {rq_number} {item_name} {max_price}"
                            self.send_udp_response(negotiate_message, offer['address'])
                            logging.info(
                                f"Negotiation initiated with {offer['seller_name']} for item '{item_name}' at max price {max_price}")

                        # Update the status to indicate negotiation is in progress
                        self.active_requests[rq_number]['status'] = 'Negotiating'
                        self.save_server_state()
                else:
                    # No offers received, notify the requester
                    buyer_name = buyer_request['name']
                    buyer_address = self.registered_peers[buyer_name]['address']
                    response_to_buyer = f"NOT_AVAILABLE {rq_number} {item_name} {max_price}"
                    self.send_udp_response(response_to_buyer, buyer_address)
                    self.active_requests[rq_number]['status'] = 'Not Available'
                    self.save_server_state()
                    logging.info(f"No offers found for '{item_name}' for {buyer_name}.")


    def handle_seller_response(self, message_parts, addr):
        rq_number = message_parts[1]
        response_type = message_parts[0]
        item_name = message_parts[2]
        max_price = float(message_parts[3])

        if rq_number not in self.active_requests:
            logging.warning(f"Invalid RQ number in seller response: {rq_number}")
            return

        buyer_request = self.active_requests[rq_number]
        buyer_name = buyer_request['name']
        buyer_address = self.registered_peers[buyer_name]['address']

        if response_type == "ACCEPT":
            response_to_buyer = f"FOUND {rq_number} {item_name} {max_price}"
            self.send_udp_response(response_to_buyer, buyer_address)
            buyer_request['status'] = 'Completed'
            logging.info(f"Negotiation successful: {item_name} sold to {buyer_name} at price {max_price}")
        elif response_type == "REFUSE":
            response_to_buyer = f"NOT_FOUND {rq_number} {item_name} {max_price}"
            self.send_udp_response(response_to_buyer, buyer_address)
            buyer_request['status'] = 'Not Found'
            logging.info(f"Negotiation failed: {item_name} not sold to {buyer_name}")

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

def get_server_udp_port():
    return int(input("Enter the UDP port for Server: "))




if __name__ == "__main__":
    server = Server()
    server.start()

