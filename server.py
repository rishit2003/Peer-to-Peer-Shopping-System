# server.py
import socket
import threading
import logging
import json
import os
import signal
import sys
import time
import uuid

logging.basicConfig(
    filename="server.log",  # Log to file
    level=logging.INFO,     # Log messages of level INFO and above
    format="%(asctime)s - %(levelname)s - %(message)s"  # Include timestamp and level
)

class Server:
    def __init__(self):
        self.registered_peers = {}
        self.rq_counter = 0
        self.peer_lock = threading.RLock() # Use a reentrant lock
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

    # Save registered peers and active requests to server.json.
    def save_server_state(self):
        with open(self.server_file, "w") as file:
            json.dump({"registered_peers": self.registered_peers, "active_requests": self.active_requests}, file, indent=4)

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
            self.handle_search(message_parts, addr)
        elif msg_type == "OFFER":
            self.handle_offer(message_parts, addr)
        elif msg_type == "ACCEPT" or msg_type == "REFUSE":
            self.handle_seller_response(message_parts, addr)
        elif msg_type == "CANCEL":
            self.handle_cancel(message_parts, addr)
        elif msg_type == "BUY":
            self.handle_tcp(message_parts, addr)
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
                self.registered_peers[name] = {"rq_number": rq_number, 'udp_socket': udp_socket, 'tcp_socket': tcp_socket,"address": tuple(addr),}
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

        # print(f"In Handle Search for {name}")

        with self.peer_lock:
            self.active_requests[rq_number] = {
                'name': name,
                'operation': 'LOOKING_FOR',
                'item_name': item_name,
                'item_description': item_description,
                'max_price': max_price,
                'status': 'Processing',
                'offers': []
            }
            self.save_server_state()

            for peer_name, peer_info in self.registered_peers.items():
                if peer_name != name:
                    search_msg = f"SEARCH {rq_number} {item_name} {item_description}"
                    self.send_udp_response(search_msg, tuple(peer_info['address']))
                    logging.info(f"SEARCH request from {name} forwarded to {peer_name} for item '{item_name}'")

            # Start a timeout thread to handle the case when no offers are received
            def handle_timeout():
                time.sleep(120)  # Wait for 2 min to see if any offers are there
                with self.peer_lock:  # Ensure thread safety
                    buyer_request = self.active_requests.get(rq_number, {})
                    if buyer_request and not buyer_request['offers']:  # No offers received
                        buyer_address = self.registered_peers[name]['address']
                        response_to_buyer = f"NOT_AVAILABLE {rq_number} {item_name} {max_price}"
                        self.send_udp_response(response_to_buyer, buyer_address)
                        logging.info(f"NOT_AVAILABLE sent to {name} for item '{item_name}' with RQ# {rq_number}")

                        # Mark the request as completed without offers
                        buyer_request['status'] = 'No Offers'
                        self.save_server_state()

            threading.Thread(target=handle_timeout, daemon=True).start()


    def handle_offer(self, message_parts, addr):
        rq_number = message_parts[1]
        seller_name = message_parts[2]
        item_name = message_parts[3]
        price = float(message_parts[4])

        logging.info(f"Offer received from {seller_name} for item '{item_name}' at price {price}")

        with self.peer_lock:
            if rq_number not in self.active_requests:
                logging.warning(f"Invalid RQ number in offer: {rq_number}")
                return

            buyer_request = self.active_requests[rq_number]
            max_price = float(buyer_request.get('max_price', 0))
            buyer_name = buyer_request['name']
            buyer_address = self.registered_peers[buyer_name]['address']
            buyer_request.setdefault('offers', []).append({'seller_name': seller_name, 'price': price, 'address': tuple(addr)})

            # Initialize a timeout thread if not already started
            if 'timeout_thread_started' not in buyer_request:
                buyer_request['timeout_thread_started'] = True

                def process_offers_after_timeout():
                    time.sleep(10)  # Wait for 10 seconds
                    with self.peer_lock:  # Ensure thread safety when accessing shared data
                        logging.info(f"Processing offers for request {rq_number} after timeout.")
                        valid_offers = [offer for offer in buyer_request['offers'] if offer['price'] <= max_price]

                        if valid_offers:
                            # Find the cheapest valid offer
                            cheapest_offer = min(valid_offers, key=lambda x: x['price'])
                            # Notify the requester about the cheapest valid offer
                            response_to_buyer = f"FOUND {rq_number} {item_name} {cheapest_offer['price']} from {cheapest_offer['seller_name']}"
                            self.send_udp_response(response_to_buyer, buyer_address)

                            # Send a RESERVE message to the seller
                            reserve_message = f"RESERVE {rq_number} {item_name} {cheapest_offer['price']}"
                            self.send_udp_response(reserve_message, cheapest_offer['address'])
                            logging.info(f"RESERVE message sent to {cheapest_offer['seller_name']} for item '{item_name}' at price {cheapest_offer['price']}")

                            # Update the request status
                            buyer_request['status'] = 'Found'
                            buyer_request['reserved_seller'] = cheapest_offer
                            self.save_server_state()
                            logging.info(f"Item '{item_name}' reserved for {buyer_name} from {cheapest_offer['seller_name']} at price {cheapest_offer['price']}")
                        else:
                            # All offers exceed max price, initiate negotiation with the cheapest offer
                            cheapest_offer = min(buyer_request['offers'], key=lambda x: x['price'])

                            negotiate_message = f"NEGOTIATE {rq_number} {item_name} {max_price}"
                            self.send_udp_response(negotiate_message, cheapest_offer['address'])
                            logging.info(f"Negotiation initiated with {cheapest_offer['seller_name']} for item '{item_name}' at max price {max_price}")

                            # Update the status to indicate negotiation is in progress
                            buyer_request['status'] = 'Negotiating'
                            self.save_server_state()

                threading.Thread(target=process_offers_after_timeout, daemon=True).start()

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

            # Determine the seller from the address
            offers = buyer_request.get('offers', [])
            reserved_seller = next((offer for offer in offers if offer['address'] == tuple(addr)), None)

            if reserved_seller:
                # Update the offer price to the max_price
                reserved_seller['price'] = max_price

                # Update the request with reserved seller information
                buyer_request['reserved_seller'] = reserved_seller

                response_to_buyer = f"FOUND {rq_number} {item_name} {reserved_seller['price']} from {reserved_seller['seller_name']}"
                self.send_udp_response(response_to_buyer, buyer_address)

                buyer_request['status'] = 'Completed'
                self.save_server_state()  # Save the updated state with reserved seller
                logging.info(f"Negotiation successful: {item_name} sold to {buyer_name} by {reserved_seller['seller_name']} at price {reserved_seller['price']}")
            else:
                logging.warning(f"No matching offer found for seller at {addr} in request {rq_number}")
        elif response_type == "REFUSE":
            response_to_buyer = f"NOT_FOUND {rq_number} {item_name} {max_price}"
            self.send_udp_response(response_to_buyer, buyer_address)
            buyer_request['status'] = 'Not Found'
            logging.info(f"Negotiation failed: {item_name} not sold to {buyer_name}")

    # Handles a CANCEL message from the buyer and notifies the seller to cancel the reservation.
    def handle_cancel(self, message_parts, addr):
        rq_number = message_parts[1]
        item_name = message_parts[2]
        price = float(message_parts[3])

        logging.info(f"CANCEL received from buyer for RQ# {rq_number}, item '{item_name}', price {price}")

        with self.peer_lock:
            if rq_number not in self.active_requests:
                logging.warning(f"Invalid RQ number in CANCEL message: {rq_number}")
                return

            buyer_request = self.active_requests[rq_number]
            buyer_name = buyer_request['name']
            buyer_address = self.registered_peers[buyer_name]['address']

            # Check if there is a reserved seller for this request
            reserved_seller = buyer_request.get('reserved_seller')
            if not reserved_seller:
                logging.warning(f"No reserved seller found for RQ# {rq_number}.")
                # response_to_buyer = f"NOT_RESERVED {rq_number} {item_name}"
                # self.send_udp_response(response_to_buyer, addr)
                return

            seller_name = reserved_seller['seller_name']
            seller_address = reserved_seller['address']

            # Send CANCEL message to the seller
            cancel_message = f"CANCEL {rq_number} {item_name} {price}"
            self.send_udp_response(cancel_message, seller_address)
            logging.info(f"CANCEL message sent to seller {seller_name} for item '{item_name}' at {price}")

            # Update the request status
            buyer_request['status'] = 'Cancelled'
            del buyer_request['reserved_seller']  # Remove the reserved seller entry
            self.save_server_state()

    # Handles the TCP transaction between buyer and seller.
    def handle_tcp(self, message_parts, addr):
        rq_number_buy_msg = message_parts[1]
        rq_number = self.generate_rq_number()
        item_name = message_parts[2]
        price = float(message_parts[3])

        logging.info(f"Initiating TCP transaction for RQ# {rq_number_buy_msg}, item '{item_name}', price {price}")

        buyer_conn = None
        seller_conn = None

        # Retrieve buyer and seller info
        with self.peer_lock:
            buyer_request = self.active_requests.get(rq_number_buy_msg)
            if not buyer_request or 'reserved_seller' not in buyer_request:
                logging.warning(f"No reserved seller found for RQ# {rq_number_buy_msg}")
                return

            buyer_name = buyer_request['name']
            seller_name = buyer_request['reserved_seller']['seller_name']
            buyer_info = self.registered_peers[buyer_name]
            seller_info = self.registered_peers[seller_name]

        try:
            # Establish TCP connections
            buyer_address = (buyer_info['address'][0], int(buyer_info['tcp_socket']))
            seller_address = (seller_info['address'][0], int(seller_info['tcp_socket']))

            buyer_conn = socket.create_connection(buyer_address)
            seller_conn = socket.create_connection(seller_address)    # Creating TCP Connection to Buyer and Seller

            logging.info(f"TCP connections established with buyer {buyer_name} and seller {seller_name}")


            try:
                # Send INFORM_Req to buyer and seller
                inform_message = f"INFORM_Req {rq_number} {item_name} {price}"
                buyer_conn.sendall(inform_message.encode())
                seller_conn.sendall(inform_message.encode())

                # Receive INFORM_Res from buyer and seller
                buyer_response = buyer_conn.recv(1024).decode()
                seller_response = seller_conn.recv(1024).decode()
                logging.info(f"Buyer response: {buyer_response}")
                logging.info(f"Seller response: {seller_response}")

                # Process the transaction
                if self.process_transaction(buyer_response, seller_response, price):
                    # Transaction successful: Send Shipping_Info to seller
                    buyer_details = buyer_response.split()
                    shipping_info = f"Shipping_Info {rq_number} {buyer_details[2]} {buyer_details[-1]}"
                    seller_conn.sendall(shipping_info.encode())
                    logging.info(f"Transaction successful. Shipping_Info sent to seller {seller_name} at address {buyer_details[-1]}")

                    # Close buyer connection after sending Shipping_Info to the seller
                    logging.info(f"Closing TCP connection to buyer {buyer_name}")
                    buyer_conn.close()

                else:
                    # Transaction failed: Notify buyer and seller
                    cancel_message = f"CANCEL {rq_number} Transaction failed"
                    buyer_conn.sendall(cancel_message.encode())
                    seller_conn.sendall(cancel_message.encode())
                    logging.warning(f"Transaction failed for RQ# {rq_number}")

                    # Close both connections after sending CANCEL
                    logging.info(f"Closing TCP connections to buyer {buyer_name} and seller {seller_name}")
                    buyer_conn.close()
                    seller_conn.close()
            finally:
                # Ensure the seller connection is closed
                if not seller_conn.close():
                    seller_conn.close()
                    logging.info(f"TCP connection to seller {seller_name} closed.")
        except Exception as e:
            logging.error(f"Error during TCP transaction for RQ# {rq_number}: {e}")
        finally:
            # Ensure the buyer connection is closed in case of errors
            if buyer_conn and not buyer_conn.close:
                buyer_conn.close()
                logging.info(f"TCP connection to buyer {buyer_name} closed.")

    # Simulates the transaction process.
    def process_transaction(self, buyer_response, seller_response, price):
        try:
            # Parse buyer and seller details from INFORM_Res
            buyer_details = buyer_response.split()
            seller_details = seller_response.split()

            buyer_cc = buyer_details[3]
            seller_cc = seller_details[3]
            buyer_name = buyer_details[2]
            transaction_amount = price * 0.9  # 90% goes to the seller

            # Simulate payment
            logging.info(f"Processing payment: Charging {buyer_cc} and crediting {seller_cc} with {transaction_amount}")
            logging.info(f"Server keeps 10% as transaction fee.")

            # Simulate a successful transaction
            return True
        except Exception as e:
            logging.error(f"Error in processing transaction: {e}")
            return False

    # Generate a unique RQ# using UUID.
    def generate_rq_number(self):
        with threading.Lock():
            self.rq_counter += 1
            rq_number = f"Server-{str(uuid.uuid4())}-{self.rq_counter}"
        return rq_number


    def send_udp_response(self, message, addr):
        with self.peer_lock:
            self.server_socket.sendto(message.encode(), addr)
        logging.info(f"Sent UDP response to {addr}: {message}")

    def start(self):
        threading.Thread(target=self.udp_listener).start()

# Determine the server's network IP.
def get_server_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))  # Connect to a public IP to determine local network IP
        return s.getsockname()[0]

def get_server_udp_port():
    return int(input("Enter the UDP port for Server: "))




if __name__ == "__main__":
    server = Server()
    server.start()

