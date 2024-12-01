# peer.py
import json
import os
import select
import socket
import sys
import threading
import time
import uuid
import logging

class Peer:
    class Client:
        class CreditCard:
            def __init__(self, number="0000-0000-0000-0000", expiry_date="00/00"):
                self.number = number
                self.expiry_date = expiry_date

        def __init__(self, rq_number, name, address):
            self.rq_number = rq_number
            self.name = name
            self.address = address
            self.credit_card = self.CreditCard()

    rq_counter = 1

    def __init__(self, name, udp_port, tcp_port):
        self.name = name
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.address = get_local_ip()
        self.client = self.Client(self.generate_rq_number(), name, "1176")
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.address, self.udp_port))  # Bind to listen for messages
        self.response_event = threading.Event()  # Event to signal when a response is received
        self.response_message = None  # Placeholder for the server's response
        self.inventory_file = f"{self.name}_inventory.json"
        self.initialize_inventory()
        self.running = True  # Control flag for threads
        self.threads = []  # To track threads
        self.is_registered = False  # Track registration status
        self.is_waiting = False  # flag to indicate waiting state
        self.lock = threading.Lock()  # Lock for terminal access
        self.in_negotiation = False
        self.in_found = False
        self.in_tcp = False
        self.input_event = threading.Event()    # Event to manage input flow

        # Setting up dynamic logging for this peer
        log_filename = f"{self.name}.log"
        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        logging.info(f"Peer {self.name} initialized with UDP port {self.udp_port} and TCP port {self.tcp_port}.")

    def listen_to_server(self):
        """Continuously listens for server messages on a dedicated thread."""
        print(f"{self.name} is now listening for server messages...")
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                threading.Thread(target=self.handle_server_message, args=(data, addr), daemon=True).start()
                if not self.running:
                    break
            except socket.error as e:
                if not self.running:
                    break
                print(f"Socket error in listen_to_server: {e}")
            except Exception as e:
                print(f"Error while listening to server messages: {e}")
                break

    def initialize_inventory(self):
        """Initialize the inventory file for the peer."""
        if not os.path.exists(self.inventory_file):
            # Create an empty inventory or predefined structure
            inventory = []
            with open(self.inventory_file, "w") as file:
                json.dump(inventory, file, indent=4)
            print(f"Inventory file created: {self.inventory_file}")
        else:
            inventory = self.load_inventory()
            updated_inventory = [
                {**item, "reserved": item.get("reserved", False)} for item in inventory
            ]
            with open(self.inventory_file, "w") as file:
                json.dump(updated_inventory, file, indent=4)
            print(f"Inventory file updated: {self.inventory_file}")

    def add_item_to_inventory(self, item_name, item_description, price):
        """Add an item to the peer's inventory."""
        item = {"item_name": item_name, "item_description": item_description, "price": price, "reserved": False}
        # Load existing inventory, update, and save back
        inventory = self.load_inventory()
        inventory.append(item)
        with open(self.inventory_file, "w") as file:
            json.dump(inventory, file, indent=4)
        print(f"Item added to inventory: {item}")

    def load_inventory(self):
        """Load the inventory from the JSON file."""
        with open(self.inventory_file, "r") as file:
            return json.load(file)

    def update_item_reservation(self, item_name, reserved):
        """Update the reservation status of an item in the inventory."""
        inventory = self.load_inventory()
        updated = False
        for item in inventory:
            if item['item_name'].lower() == item_name.lower():
                item['reserved'] = reserved
                updated = True
                break

        if updated:
            with open(self.inventory_file, "w") as file:
                json.dump(inventory, file, indent=4)
            print(f"Updated reservation status for item '{item_name}' to {reserved}.")
        else:
            # print(f"Item '{item_name}' not found in inventory.")
            logging.warning(f"Item '{item_name}' not found in inventory.")

    def handle_server_message(self, data, addr):
        """Handles different types of server messages."""
        try:
            message = data.decode()
            self.response_message = message  # Set the response message
            message_parts = message.split()
            msg_type = message_parts[0]

            if msg_type == "SEARCH":
                self.handle_search(message_parts)
            elif msg_type == "NEGOTIATE":
                # self.lock.release_lock()
                self.handle_negotiate(message_parts, addr)
            elif msg_type == "FOUND":
                self.response_event.set()
                self.handle_found(message_parts, addr)
            elif msg_type in ["REGISTERED", "DE-REGISTERED", "REGISTER-DENIED", "DE-REGISTER-DENIED", "NOT_AVAILABLE", "NOT_FOUND"]:
                self.response_event.set()
            elif msg_type == "RESERVE":
                self.response_event.set()
                self.handle_reserved(message_parts)
            elif msg_type == "CANCEL":
                self.response_event.set()
                self.handle_cancel(message_parts)
            # elif msg_type == "INFORM_Req":
            #     self.handle_tcp_transaction()
            else:
                print(f"Unknown message type received: {msg_type}")
        except Exception as e:
            print(f"Error in handle_server_message: {e}")

    def handle_search(self, parts):
        """Handles SEARCH message from the server."""
        rq_number = parts[1]
        item_name = parts[2]
        item_description = " ".join(parts[3:])

        # print(f"SEARCH received: Looking for '{item_name}' with description '{item_description}'")

        # Check if the item exists in the peer's inventory
        inventory = self.load_inventory()
        for item in inventory:
            if item['item_name'].lower() == item_name.lower() and not item.get("reserved", False):
                # Item found, respond to the server with an OFFER message
                price = item['price']
                offer_msg = f"OFFER {rq_number} {self.name} {item_name} {price}"
                self.send_and_wait_for_response(offer_msg,(server_ip, server_udp_port))
                self.update_item_reservation(item_name, True)  # Mark as reserved
                # print(f"Sent OFFER to server: {offer_msg}")
                logging.info(f"Sent OFFER to server: {offer_msg}")
                return

        # If the item is not found, no response is necessary
        # print(f"Item '{item_name}' not found in inventory.")
        logging.warning(f"Item '{item_name}' not found in inventory.")

    def handle_negotiate(self, parts, addr):
        """Handles NEGOTIATE message from the server."""
        rq_number = parts[1]
        item_name = parts[2]
        max_price = float(parts[3])

        with self.lock:  # Acquire the lock for terminal interaction
            # print(f"NEGOTIATE received: Buyer willing to pay {max_price} for {item_name}")
            logging.info(print(f"NEGOTIATE received: Buyer willing to pay {max_price} for {item_name}"))
            # Pause interactive loop
            self.input_event.set()  # Signal input should stop elsewhere
            self.in_negotiation = True

        # Logic to decide whether to accept or refuse the negotiation
        while True:
            accept_negotiation = input(f"Accept negotiation? (y/n): ").strip().lower()
            if accept_negotiation == 'y':
                response = f"ACCEPT {rq_number} {item_name} {max_price}"
                self.update_item_reservation(item_name, True)
                break
            elif accept_negotiation == 'n':
                response = f"REFUSE {rq_number} {item_name} {max_price}"
                self.update_item_reservation(item_name, False)
                break
            else:
                print("Invalid response received.")

        # Send the response back to the server
        self.udp_socket.sendto(response.encode(), addr)
        print(f"Sent response to server: {response}")
        # Resume interactive loop
        # self.is_waiting = False

        with self.lock:  # Lock again for thread-safe updates
            self.update_item_reservation(item_name, accept_negotiation == "y")
            self.in_negotiation = False
            self.input_event.clear()  # Allow main loop input handling

    def handle_reserved(self, parts):
        self.update_item_reservation(parts[2], True)

    def handle_cancel(self, parts):
        self.update_item_reservation(parts[2], False)

    def handle_found(self, parts, addr):
        rq_number = parts[1]
        item_name = parts[2]
        price = float(parts[3])

        with self.lock:
            print(f"\nItem: {item_name} found")
            # Pause interactive loop
            self.input_event.set()  # Signal input should stop elsewhere
            self.in_found = True

        accept_buy = input(f"Do you want to Buy {item_name}? (y/n): ").strip().lower()
        if accept_buy == 'y':
            response = f"BUY {rq_number} {item_name} {price}"
        else:
            response = f"CANCEL {rq_number} {item_name} {price}"

        # Send the response back to the server
        self.udp_socket.sendto(response.encode(), addr)
        # print(f"Sent response to server: {response}")
        logging.info(f"Sent response to server: {response}")

        with self.lock:  # Lock again for thread-safe updates
            # self.update_item_reservation(item_name, accept_negotiation == "y")
            self.in_found = False
            self.input_event.clear()


    def generate_rq_number(self):
        """Generate a unique RQ# using UUID."""
        return str(uuid.uuid4())

    def send_and_wait_for_response(self, message, server_address, timeout=5):
        """Send a message to the server and wait for a response via listen_to_server."""
        self.response_event.clear()  # Reset the event before sending a message
        self.response_message = None  # Clear any previous response
        try:
            self.udp_socket.sendto(message.encode(), server_address)
            # print(f"\nMessage sent: {message}")
            logging.info(f"Message sent: {message}")
            if message.startswith("LOOKING_FOR"):
                self.is_waiting = True  # Start waiting
                if self.response_event.wait(90):  # Wait 90 seconds TODO: Should be greater than 2 minutes but keep it at the same for testing
                    # print(f"Server response received via listen_to_server: {self.response_message}")
                    logging.info(f"Server response received via listen_to_server: {self.response_message}")
                    # Handle NOT_AVAILABLE response
                    if "NOT_AVAILABLE" in self.response_message:
                        # print(f"Item not available: {self.response_message}")
                        logging.info(f"Item not available: {self.response_message}")
                else:
                    print("Timeout LF: No response from the server.")
                    logging.info("Timeout LF: No response from the server.")
            elif self.response_event.wait(timeout):  # Wait for the response within the timeout
                # print(f"Server response received via listen_to_server: {self.response_message}")
                logging.info(f"Server response received via listen_to_server: {self.response_message}")
            else:
                print("Timeout: No response from the server.")
                logging.info("Timeout: No response from the server.")
        except Exception as e:
            print(f"Error sending message: {e}")
            logging.warning(f"Error sending message: {e}")
        finally:
            self.is_waiting = False  # End waiting

    def register_with_server(self):
        register_msg = f"REGISTER {self.client.rq_number} {self.client.name} {self.address} {self.udp_port} {self.tcp_port}"
        logging.info(f"Sending registration message: {register_msg}")
        self.send_and_wait_for_response(register_msg, (server_ip, server_udp_port))
        if self.response_message and "REGISTERED" in self.response_message:
            self.is_registered = True
            print("Successfully registered.")
        else:
            print("Registration failed.")

    def deregister_with_server(self):
        deregister_msg = f"DE-REGISTER {self.client.rq_number} {self.client.name}"
        logging.info(f"Sending deregistration message: {deregister_msg}")
        self.send_and_wait_for_response(deregister_msg, (server_ip, server_udp_port))
        if self.response_message and "DE-REGISTERED" in self.response_message:
            self.is_registered = False
            print("Successfully deregistered.")
        else:
            print("De-registration failed.")

    def looking_for_item_server(self, itemName, itemDescription, maxPrice):
        self.is_waiting = True  # Start waiting
        looking_for_msg = f"LOOKING_FOR {self.client.rq_number} {self.name} {itemName} {itemDescription} {maxPrice}"
        # print(f"Sending looking for: {looking_for_msg}")
        logging.info(f"Sending looking for: {looking_for_msg}")
        self.send_and_wait_for_response(looking_for_msg, (server_ip, server_udp_port))
        self.is_waiting = False  # Stop waiting after the response

    def tcp_listener(self):
        """Continuously listen for incoming TCP connections."""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((self.address, self.tcp_port))
        server_socket.listen(5)
        logging.info(f"{self.name} listening for TCP connections on port {self.tcp_port}.")

        while self.running:
            try:
                conn, addr = server_socket.accept()
                logging.info(f"Accepted TCP connection from {addr}")
                # Handle the connection in a separate thread
                threading.Thread(target=self.handle_tcp_connection, args=(conn, addr), daemon=True).start()
            except Exception as e:
                if self.running:
                    logging.error(f"Error accepting TCP connection: {e}")
        server_socket.close()

    def handle_tcp_connection(self, conn, addr):
        """Continuously handle messages from a single TCP connection."""
        logging.info(f"Handling TCP connection from {addr}")
        try:
            while self.running:
                data = conn.recv(1024).decode()
                if not data:
                    logging.info(f"Connection closed by {addr}")
                    break

                logging.info(f"Received TCP message from {addr}: {data}")
                parts = data.split()
                msg_type = parts[0]

                # Spawn a new thread for each message type
                if msg_type == "INFORM_Req":
                    threading.Thread(target=self.process_inform_request, args=(conn, addr, parts), daemon=True).start()
                elif msg_type == "Shipping_Info":
                    threading.Thread(target=self.process_shipping_info, args=(conn, addr, parts), daemon=True).start()
                elif msg_type == "CANCEL":
                    threading.Thread(target=self.process_cancel_transaction, args=(conn, addr, parts),daemon=True).start()
                else:
                    logging.warning(f"Unknown TCP message type received: {msg_type}")

        except Exception as e:
            logging.error(f"Error handling TCP connection: {e}")
        finally:
            conn.close()
            logging.info(f"Connection with {addr} closed.")

    def process_inform_request(self, conn, addr, parts):
        """Process an INFORM_Req message."""
        rq_number, item_name, price = parts[1], parts[2], parts[3]
        logging.info(f"Processing INFORM_Req for RQ#{rq_number}, Item: {item_name}, Price: {price}")

        with self.lock:  # Acquire the lock for terminal interaction
            # Pause interactive loop
            self.input_event.set()  # Signal input should stop elsewhere
            self.in_tcp = True

        # Collect buyer/seller information
        self.client.credit_card.number = input("Credit Card number: ")
        self.client.credit_card.expiry_date = input("Expiry date (MM/YY): ")
        self.client.address = input("Address: ")

        # Send INFORM_Res response
        response = f"INFORM_Res {rq_number} {self.name} {self.client.credit_card.number} {self.client.credit_card.expiry_date} {self.client.address}"
        conn.sendall(response.encode())
        logging.info(f"Sent INFORM_Res: {response}")

        with self.lock:
            self.in_tcp = False
            self.input_event.clear()  # Resume interactive loop

    def process_shipping_info(self, conn, addr, parts):
        """Process a Shipping_Info message."""
        print("In Process Shipping Info")
        rq_number, buyer_name, buyer_address = parts[1], parts[2], parts[3]
        logging.info(f"Processing Shipping_Info for RQ#{rq_number}, Buyer: {buyer_name}, Address: {buyer_address}")
        print(f"Shipping Info: Send item to {buyer_name} at {buyer_address}.")

    def process_cancel_transaction(self, conn, addr, parts):
        """Process a CANCEL message."""
        rq_number, reason = parts[1], " ".join(parts[2:])
        logging.info(f"Processing CANCEL for RQ#{rq_number}, Reason: {reason}")
        print(f"Transaction cancelled. Reason: {reason}")

    # def handle_tcp_transaction(self):
    #     """Handle TCP transactions initiated by the server."""
    #     server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #     server_socket.bind((self.address, self.tcp_port))
    #     server_socket.listen(5)
    #     # print(f"{self.name} ready for TCP transactions on port {self.tcp_port}.")
    #     logging.info(f"{self.name} ready for TCP transactions on port {self.tcp_port}.")
    #
    #     while self.running:
    #         try:
    #             conn, addr = server_socket.accept()
    #             # print(f"TCP transaction started with {addr}")
    #             logging.info(f"TCP transaction started with {addr}")
    #
    #             # Receive INFORM_Req message from the server
    #             data = conn.recv(1024).decode()
    #             with self.lock:  # Acquire the lock for terminal interaction
    #                 # Pause interactive loop
    #                 self.input_event.set()  # Signal input should stop elsewhere
    #                 self.in_tcp = True
    #
    #
    #             if data.startswith("INFORM_Req"):
    #                 # print(f"Received: {data}")
    #                 logging.info(f"Received: {data}")
    #                 parts = data.split()
    #                 rq_number, item_name, price = parts[1], parts[2], parts[3]
    #
    #                 self.client.credit_card.number = input("Credit Card number: ")
    #                 self.client.credit_card.expiry_date = input("Expiry date (MM/YY): ")
    #                 self.client.address = input("Address: ")
    #
    #                 # Respond with INFORM_Res
    #                 response = f"INFORM_Res {rq_number} {self.name} {self.client.credit_card.number} {self.client.credit_card.expiry_date} {self.client.address}"
    #                 conn.sendall(response.encode())
    #                 # print(f"Sent: {response}")
    #                 logging.info(f"Sent: {response}")
    #
    #             # Handle Shipping_Info or CANCEL messages
    #             data = conn.recv(1024).decode()
    #             if data.startswith("Shipping_Info"):
    #                 print(f"Shipping Info received: {data}")
    #                 logging.info(f"Shipping Info received: {data}")
    #             elif data.startswith("CANCEL"):
    #                 print(f"Transaction cancelled: {data}")
    #                 logging.info(f"Transaction cancelled: {data}")
    #             conn.close()
    #
    #         except Exception as e:
    #             if self.running:
    #                 print(f"Error during TCP transaction: {e}")
    #         finally:
    #             with self.lock:
    #                 self.in_tcp = False
    #                 self.input_event.clear()  # Resume interactive loop

    def start_interactive_loop(self):
        """Interactive loop for user actions."""
        try:
            printed_options = False
            while self.running:
                with self.lock:
                    if self.in_negotiation or self.in_found or self.in_tcp or self.is_waiting:
                        # print("Waiting for server response. Please wait...")
                        self.input_event.wait()
                        continue


                # Print options only once until user input is processed
                if not printed_options:
                    print("\nOptions:")
                    print("1. Register")
                    print("2. Deregister")
                    print("3. Look for item")
                    print("4. Add Item to Inventory")
                    print("5. Exit")
                    print("Choose an option (1-5): ", end="", flush=True)
                    printed_options = True  # Mark options as printed

                # Non-blocking input check
                ready, _, _ = select.select([sys.stdin], [], [], 1)  # 1-second timeout
                if ready:
                    choice = sys.stdin.readline().strip()
                    with self.lock:  # Ensure thread-safety while processing
                        if self.in_negotiation or self.in_found or self.in_tcp or self.is_waiting:
                            print("\nConsole in use. Please wait.")
                            continue
                        if choice in ["3", "4"]:
                            if not self.is_registered:
                                print("You must register with the server before performing this action.")
                                continue
                            itemName = input("Item_name: ")
                            itemDescription = input("Description: ")
                            itemPrice = float(input("Price: "))

                        if choice == '1':
                            self.register_with_server()
                        elif choice == '2':
                            self.deregister_with_server()
                        elif choice == '3':
                            self.looking_for_item_server(itemName, itemDescription, itemPrice)
                            continue
                        elif choice == '4':
                            self.add_item_to_inventory(itemName, itemDescription, itemPrice)
                        elif choice == '5':
                            print("Exiting program.")
                            self.running = False  # Exit gracefully
                            break
                        else:
                            print("Invalid choice. Please try again.")

                    # Reset the flag to print options again after input is handled
                    printed_options = False
                else:
                    # No input available; continue to check state
                    continue
        except KeyboardInterrupt:
            print("\nInteractive loop interrupted.")
            self.running = False
        finally:
            self.shutdown()

    def start(self):
        listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)  # Start listening in a thread
        tcp_listener_thread = threading.Thread(target=self.tcp_listener, daemon=True)  # Start TCP listener
        interactive_thread = threading.Thread(target=self.start_interactive_loop)  # Interactive loop thread

        self.threads.extend([listen_thread, tcp_listener_thread, interactive_thread])

        listen_thread.start()
        tcp_listener_thread.start()
        interactive_thread.start()

    def shutdown(self):
        """Gracefully shut down the peer."""
        print("Shutting down peer...")
        self.running = False

        try:
            self.udp_socket.close()  # Close the UDP socket
            if hasattr(self, 'server_socket'):
                self.server_socket.close()  # Close the TCP server socket
        except Exception as e:
            print(f"Error closing UDP socket: {e}")

        for thread in self.threads:
            if thread.is_alive():
                print(f"Waiting for thread {thread.name} to finish...")
                thread.join(timeout=2)  # Wait for each thread to terminate
                if thread.is_alive():
                    print(f"Thread {thread.name} did not terminate.")
        print("Peer shut down successfully.")

def get_local_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        # The IP here (8.8.8.8) is a dummy; no data is sent to it
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]

# def simulate_peers_from_file(filename):
#     with open(filename, 'r') as f:
#         for line in f:
#             name, udp_port, tcp_port = line.strip().split()
#             peer = Peer(name, int(udp_port), int(tcp_port))
#             threading.Thread(target=peer.start).start()
#             time.sleep(1)

if __name__ == "__main__":
    # simulate_peers_from_file("test_peers.txt")
    # Peer1 = Peer(name="Peer1", udp_port=6000, tcp_port=9000, rq_number="RQ1")
    # threading.Thread(target=Peer1.start).start()
    # time.sleep(1)  # Delay to simulate staggered registration
    # Peer2 = Peer(name="Peer2", udp_port=6001, tcp_port=9001, rq_number="RQ2")
    # threading.Thread(target=Peer2.start).start()

    server_ip = input("Enter Server's IP: ")
    server_udp_port = int(input("Enter Server's UDP port: "))

    # Single-line input for peer details
    input_line = input("Enter peer details (e.g., Peer1 6000 9000): ")
    name, udp_port, tcp_port = input_line.split()
    udp_port = int(udp_port)
    tcp_port = int(tcp_port)

    # Create Peer object
    peer = Peer(name, udp_port, tcp_port)
    peer.start()  # Start listening and TCP transaction handling


