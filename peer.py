import json
import os
import socket
import sys
import threading
import time
import uuid
import logging
import queue

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

    def __init__(self, name, udp_port, tcp_port):
        self.name = name
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.address = get_local_ip()
        self.client = self.Client(self.generate_rq_number(), name, "Address")
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.address, self.udp_port))  # Bind to listen for messages
        self.response_event = threading.Event()  # Event to signal when a response is received
        self.response_message = None  # Placeholder for the server's response
        self.inventory_file = f"{self.name}_inventory.json"
        self.initialize_inventory()
        self.running = True  # Control flag for threads
        self.threads = []  # To track threads
        self.is_registered = False  # Track registration status
        self.is_waiting = False  # Flag to indicate waiting state
        self.lock = threading.Lock()  # Lock for terminal access
        self.in_negotiation = False
        self.in_found = False
        self.in_tcp = False

        # Synchronization primitives for input handling
        self.input_available_event = threading.Event()
        self.input_received_event = threading.Event()
        self.input_lock = threading.Lock()
        self.input_needed = False
        self.input_prompt = ""
        self.input_response = None

        # Queue for user input
        self.input_queue = queue.Queue()

        # Setting up dynamic logging for this peer
        log_filename = f"{self.name}.log"
        logging.basicConfig(
            filename=log_filename,
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        logging.info(f"Peer {self.name} initialized with UDP port {self.udp_port} and TCP port {self.tcp_port}.")

    # Continuously listens for server messages on a dedicated thread.
    def listen_to_server(self):
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

    #Initialize the inventory file for the peer.
    def initialize_inventory(self):
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

    # Add an item to the peer's inventory.
    def add_item_to_inventory(self, item_name, item_description, price):
        item = {"item_name": item_name, "item_description": item_description, "price": price, "reserved": False}
        # Load existing inventory, update, and save back
        inventory = self.load_inventory()
        inventory.append(item)
        with open(self.inventory_file, "w") as file:
            json.dump(inventory, file, indent=4)
        print(f"Item added to inventory: {item}")

    # Load the inventory from the JSON file.
    def load_inventory(self):
        with open(self.inventory_file, "r") as file:
            return json.load(file)

    # Update the reservation status of an item in the inventory.
    def update_item_reservation(self, item_name, reserved):
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
            logging.info(f"Updated reservation status for item '{item_name}' to {reserved}.")
        else:
            logging.warning(f"Item '{item_name}' not found in inventory.")

    # Handles different types of server messages.
    def handle_server_message(self, data, addr):
        try:
            message = data.decode()
            self.response_message = message  # Set the response message
            message_parts = message.split()
            msg_type = message_parts[0]

            if msg_type == "SEARCH":
                self.handle_search(message_parts)
            elif msg_type == "NEGOTIATE":
                self.response_event.set()
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
            else:
                print(f"Unknown message type received: {msg_type}")
        except Exception as e:
            print(f"Error in handle_server_message: {e}")

    # Handles SEARCH message from the server.
    def handle_search(self, parts):
        rq_number = parts[1]
        item_name = parts[2]
        item_description = " ".join(parts[3:])

        # Check if the item exists in the peer's inventory
        inventory = self.load_inventory()
        for item in inventory:
            if item['item_name'].lower() == item_name.lower() and not item.get("reserved", False):
                # Item found, respond to the server with an OFFER message
                price = item['price']
                offer_msg = f"OFFER {rq_number} {self.name} {item_name} {price}"
                self.send_and_wait_for_response(offer_msg, (server_ip, server_udp_port))
                self.update_item_reservation(item_name, True)  # Mark as reserved
                logging.info(f"Sent OFFER to server: {offer_msg}")
                return

        # If the item is not found, no response is necessary
        logging.warning(f"Item '{item_name}' not found in inventory.")

    # Handles NEGOTIATE message from the server.
    def handle_negotiate(self, parts, addr):
        rq_number = parts[1]
        item_name = parts[2]
        max_price = float(parts[3])

        with self.input_lock:
            self.in_negotiation = True
            self.input_needed = True
            self.input_prompt = f"\nAccept negotiation for {item_name} at {max_price}? (y/n): "
            self.input_response = None

        self.input_received_event.clear()  # Clear event before waiting
        self.input_available_event.set()   # Signal that input is needed

        # Wait for the main thread to handle the input
        self.input_received_event.wait()

        with self.input_lock:
            accept_negotiation = self.input_response.strip().lower()
            self.input_needed = False  # Input has been processed

        if accept_negotiation == 'y':
            response = f"ACCEPT {rq_number} {item_name} {max_price}"
            self.update_item_reservation(item_name, True)
        elif accept_negotiation == 'n':
            response = f"REFUSE {rq_number} {item_name} {max_price}"
            self.update_item_reservation(item_name, False)
            with self.lock:
                self.in_negotiation = False  # Only set to False if refused
        else:
            print("Invalid response received.")
            response = f"REFUSE {rq_number} {item_name} {max_price}"
            self.update_item_reservation(item_name, False)
            with self.lock:
                self.in_negotiation = False  # Only set to False if refused

        # Send the response back to the server
        self.udp_socket.sendto(response.encode(), addr)
        logging.info(f"Sent response to server: {response}")

        with self.input_lock:
            # self.in_negotiation = False
            self.input_available_event.clear()

    def handle_reserved(self, parts):
        self.update_item_reservation(parts[2], True)

    def handle_cancel(self, parts):
        self.update_item_reservation(parts[2], False)

    def handle_found(self, parts, addr):
        rq_number = parts[1]
        item_name = parts[2]
        price = float(parts[3])

        with self.input_lock:
            self.in_found = True
            self.input_needed = True
            self.input_prompt = f"\nItem: {item_name} found at price {price}. Do you want to buy it? (y/n): "
            self.input_response = None

        self.input_received_event.clear()  # Clear event before waiting
        self.input_available_event.set()   # Signal that input is needed

        # Wait for the main thread to handle the input
        self.input_received_event.wait()

        with self.input_lock:
            accept_buy = self.input_response.strip().lower()
            self.input_needed = False  # Input has been processed

        if accept_buy == 'y':
            response = f"BUY {rq_number} {item_name} {price}"
        else:
            response = f"CANCEL {rq_number} {item_name} {price}"

        # Send the response back to the server
        self.udp_socket.sendto(response.encode(), addr)
        logging.info(f"Sent response to server: {response}")

        with self.input_lock:
            self.in_found = False
            self.input_available_event.clear()

    def generate_rq_number(self):
        """Generate a unique RQ# using UUID."""
        return str(uuid.uuid4())

    def send_and_wait_for_response(self, message, server_address, timeout=5):
        """Send a message to the server and wait for a response via listen_to_server."""
        self.response_event.clear()  # Reset the event before sending a message
        self.response_message = None  # Clear any previous response
        try:
            self.udp_socket.sendto(message.encode(), server_address)
            logging.info(f"Message sent: {message}")
            if message.startswith("LOOKING_FOR"):
                self.is_waiting = True  # Start waiting
                if self.response_event.wait(90):  # Wait 90 seconds
                    logging.info(f"Server response received via listen_to_server: {self.response_message}")
                    if "NOT_AVAILABLE" in self.response_message:
                        print(f"Item not available: {self.response_message}")
                        logging.info(f"Item not available: {self.response_message}")
                else:
                    print("Timeout LF: No response from the server.")
                    logging.info("Timeout LF: No response from the server.")
            elif self.response_event.wait(timeout):  # Wait for the response within the timeout
                logging.info(f"Server response received via listen_to_server: {self.response_message}")
            else:
                print("\nTimeout: No response from the server.")
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
        logging.info(f"Sending looking for: {looking_for_msg}")
        self.send_and_wait_for_response(looking_for_msg, (server_ip, server_udp_port))
        self.is_waiting = False  # Stop waiting after the response

    # Continuously listen for incoming TCP connections.
    def tcp_listener(self):
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

    # Continuously handle messages from a single TCP connection.
    def handle_tcp_connection(self, conn, addr):
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
                    self.process_shipping_info(conn, addr, parts)
                    break  # Exit the loop after closing the connection
                elif msg_type == "CANCEL":
                    threading.Thread(target=self.process_cancel_transaction, args=(conn, addr, parts), daemon=True).start()
                else:
                    logging.warning(f"Unknown TCP message type received: {msg_type}")

        except Exception as e:
            logging.error(f"Error handling TCP connection: {e}")
        finally:
            conn.close()
            logging.info(f"Connection with {addr} closed.")

    # Process an INFORM_Req message.
    def process_inform_request(self, conn, addr, parts):
        rq_number, item_name, price = parts[1], parts[2], parts[3]
        logging.info(f"Processing INFORM_Req for RQ#{rq_number}, Item: {item_name}, Price: {price}")

        with self.input_lock:
            self.in_tcp = True
            self.input_needed = True
            self.input_prompt = "Credit Card number: "
            self.input_response = None

        self.input_received_event.clear()
        self.input_available_event.set()
        self.input_received_event.wait()

        with self.input_lock:
            cc_number = self.input_response
            self.input_needed = False

        # Collect expiry date
        with self.input_lock:
            self.input_needed = True
            self.input_prompt = "Expiry date (MM/YY): "
            self.input_response = None

        self.input_received_event.clear()
        self.input_available_event.set()
        self.input_received_event.wait()

        with self.input_lock:
            cc_expiry = self.input_response
            self.input_needed = False

        # Collect address
        with self.input_lock:
            self.input_needed = True
            self.input_prompt = "Address: "
            self.input_response = None

        self.input_received_event.clear()
        self.input_available_event.set()
        self.input_received_event.wait()

        with self.input_lock:
            address = self.input_response
            self.input_needed = False

        # Send INFORM_Res response
        response = f"INFORM_Res {rq_number} {self.name} {cc_number} {cc_expiry} {address}"
        conn.sendall(response.encode())
        logging.info(f"Sent INFORM_Res: {response}")

        with self.input_lock:
            self.in_tcp = False
            self.input_available_event.clear()

        with self.lock:
            self.in_negotiation = False

    # Process a Shipping_Info message.
    def process_shipping_info(self, conn, addr, parts):
        try:
            # Parse the message
            rq_number, buyer_name, buyer_address = parts[1], parts[2], parts[3]
            logging.info(f"Processing Shipping_Info for RQ#{rq_number}, Buyer: {buyer_name}, Address: {buyer_address}")
            print(f"Shipping Info: Send item to {buyer_name} at {buyer_address}.")

            # After processing the message, close the connection
            conn.close()
            logging.info(f"TCP connection with {addr} closed by {self.name} after processing Shipping_Info.")
        except Exception as e:
            logging.error(f"Error processing Shipping_Info: {e}")
        finally:
            if not conn.close:
                conn.close()
            with self.input_lock:
                self.in_tcp = False
                self.input_available_event.clear()

    # Process a CANCEL message.
    def process_cancel_transaction(self, conn, addr, parts):
        rq_number, reason = parts[1], " ".join(parts[2:])
        logging.info(f"Processing CANCEL for RQ#{rq_number}, Reason: {reason}")
        print(f"Transaction cancelled. Reason: {reason}")
        with self.input_lock:
            self.in_tcp = False
            self.input_available_event.clear()

    # Interactive loop for user actions.
    def start_interactive_loop(self):
        try:
            printed_options = False
            while self.running:
                # Check if input is needed by another thread
                if self.input_available_event.is_set():
                    with self.input_lock:
                        prompt = self.input_prompt
                    print(prompt, end='', flush=True)
                    response = self.input_queue.get()
                    with self.input_lock:
                        self.input_response = response
                        self.input_needed = False
                    self.input_available_event.clear()
                    self.input_received_event.set()
                    continue

                # Check if we should display the menu
                with self.lock:
                    if self.in_negotiation or self.in_found or self.in_tcp or self.is_waiting:
                        printed_options = False
                        time.sleep(0.1)
                        continue

                    # Print options only once until user input is processed
                    if not printed_options:
                        print("\nOptions:")
                        print("1. Register")
                        print("2. Deregister")
                        print("3. Look for item")
                        print("4. Add Item to Inventory")
                        print("5. Exit")
                        print("Choose an option (1-5): ", end='', flush=True)
                        printed_options = True  # Mark options as printed

                # Check for user input from the input queue
                try:
                    choice = self.input_queue.get(timeout=0.1)
                except queue.Empty:
                    # No input, sleep briefly to avoid busy waiting
                    time.sleep(0.1)
                    continue

                with self.lock:
                    if self.in_negotiation or self.in_found or self.in_tcp or self.is_waiting:
                        print("\nConsole in use. Please wait.")
                        printed_options = False
                        continue

                    # Process user choice as before
                    if choice in ["3", "4"]:
                        if not self.is_registered:
                            print("You must register with the server before performing this action.")
                            printed_options = False
                            continue
                        # Collect item details
                        print("Item_name: ", end='', flush=True)
                        itemName = self.input_queue.get()
                        print("Description: ", end='', flush=True)
                        itemDescription = self.input_queue.get()
                        print("Price: ", end='', flush=True)
                        itemPrice = float(self.input_queue.get())

                    if choice == '1':
                        self.register_with_server()
                    elif choice == '2':
                        self.deregister_with_server()
                    elif choice == '3':
                        self.looking_for_item_server(itemName, itemDescription, itemPrice)
                        printed_options = False
                        continue
                    elif choice == '4':
                        self.add_item_to_inventory(itemName, itemDescription, itemPrice)
                    elif choice == '5':
                        print("Exiting program.")
                        self.running = False  # Exit gracefully
                        break
                    elif choice.strip() == '':
                        printed_options = False
                    else:
                        print("Invalid choice. Please try again.")
                    # Reset the flag to print options again after input is handled
                    printed_options = False
            print("Exiting interactive loop.")
        except KeyboardInterrupt:
            print("\nInteractive loop interrupted.")
            self.running = False
        finally:
            self.shutdown()

    # Thread function to handle user input.
    def input_thread_function(self):
        while self.running:
            try:
                user_input = input()
                self.input_queue.put(user_input)
            except EOFError:
                break
            except Exception as e:
                logging.error(f"Input thread error: {e}")
                break

    def start(self):
        listen_thread = threading.Thread(target=self.listen_to_server, daemon=True)  # Start listening in a thread
        tcp_listener_thread = threading.Thread(target=self.tcp_listener, daemon=True)  # Start TCP listener
        input_thread = threading.Thread(target=self.input_thread_function, daemon=True)  # Input handling thread
        interactive_thread = threading.Thread(target=self.start_interactive_loop)  # Interactive loop thread

        self.threads.extend([listen_thread, tcp_listener_thread, input_thread, interactive_thread])

        listen_thread.start()
        tcp_listener_thread.start()
        input_thread.start()
        interactive_thread.start()

    # Gracefully shut down the peer.
    def shutdown(self):
        print("Shutting down peer...")
        self.running = False
        self.input_available_event.set()
        self.input_received_event.set()

        try:
            self.udp_socket.close()  # Close the UDP socket
        except Exception as e:
            print(f"Error closing UDP socket: {e}")

        for thread in self.threads:
            if thread is threading.current_thread():
                continue  # Skip joining current thread
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

if __name__ == "__main__":
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
