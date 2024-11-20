# peer.py
import json
import os
import socket
import threading
import time

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
        self.client = self.Client(self.generate_rq_number(), name, self.address)
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((self.address, self.udp_port))  # Bind to listen for messages
        self.response_event = threading.Event()  # Event to signal when a response is received
        self.response_message = None  # Placeholder for the server's response
        self.inventory_file = f"{self.name}_inventory.json"
        self.initialize_inventory()

    def listen_to_server(self):
        """Continuously listens for server messages on a dedicated thread."""
        print(f"{self.name} is now listening for server messages...")
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                self.response_message = data.decode()
                print(f"Message from {addr}: {self.response_message}")
                self.response_event.set()  # Signal that a response has been received
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
            print(f"Inventory file already exists: {self.inventory_file}")

    def add_item_to_inventory(self, item_name, item_description, price):
        """Add an item to the peer's inventory."""
        item = {"item_name": item_name, "item_description": item_description, "price": price}
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

    def handle_server_message(self, message, addr):
        """Handles different types of server messages."""
        parts = message.split()
        msg_type = parts[0]

        if msg_type == "SEARCH":
            self.handle_search(parts)   # TODO: Need to implement this
        elif msg_type == "NEGOTIATE":
            self.handle_negotiate(parts, addr)
        elif msg_type == "FOUND":
            self.handle_found(parts)       # TODO: Need to implement this
        elif msg_type == "NOT_FOUND":
            self.handle_not_found(parts)    # TODO: Need to implement this
        else:
            print(f"Unknown message type received: {msg_type}")

    def handle_negotiate(self, parts, addr):
        """Handles NEGOTIATE message from the server."""
        rq_number = parts[1]
        item_name = parts[2]
        max_price = float(parts[3])

        print(f"NEGOTIATE received: Buyer willing to pay {max_price} for {item_name}")

        # Logic to decide whether to accept or refuse the negotiation
        accept_negotiation = input(f"Accept negotiation? (yes/no): ").strip().lower()
        if accept_negotiation == "yes":
            response = f"ACCEPT {rq_number} {item_name} {max_price}"
        else:
            response = f"REFUSE {rq_number} {item_name} {max_price}"

        # Send the response back to the server
        self.udp_socket.sendto(response.encode(), addr)
        print(f"Sent response to server: {response}")

    def generate_rq_number(self):
        """Generate a simple RQ# based on IP address and a counter."""
        rq_number = f"{self.address}-{Peer.rq_counter}"
        Peer.rq_counter += 1
        return rq_number

    def send_and_wait_for_response(self, message, server_address, timeout=5):
        """Send a message to the server and wait for a response via listen_to_server."""
        self.response_event.clear()  # Reset the event before sending a message
        self.response_message = None  # Clear any previous response
        try:
            self.udp_socket.sendto(message.encode(), server_address)
            print(f"Message sent: {message}")
            if self.response_event.wait(timeout):  # Wait for the response within the timeout
                print(f"Server response received via listen_to_server: {self.response_message}")
            else:
                print("Timeout: No response from the server.")
        except Exception as e:
            print(f"Error sending message: {e}")

    def register_with_server(self):
        register_msg = f"REGISTER {self.client.rq_number} {self.client.name} {self.client.address} {self.udp_port} {self.tcp_port}"
        print(f"Sending registration message: {register_msg}")
        self.send_and_wait_for_response(register_msg, (server_ip, 5000))

    def deregister_with_server(self):
        deregister_msg = f"DE-REGISTER {self.client.rq_number} {self.client.name}"
        print(f"Sending deregistration message: {deregister_msg}")
        self.send_and_wait_for_response(deregister_msg, (server_ip, 5000))

    def looking_for_item_server(self, itemName, itemDescription, maxPrice):
        looking_for_msg = f"LOOKING_FOR {self.client.rq_number} {self.name} {itemName} {itemDescription} {maxPrice}"
        print(f"Sending looking for: {looking_for_msg}")
        self.send_and_wait_for_response(looking_for_msg, (server_ip, 5000))


    def handle_tcp_transaction(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(('localhost', self.tcp_port))
        server_socket.listen(1)
        try:
            conn, addr = server_socket.accept()
            print(f"TCP transaction started with {addr}")
            data = conn.recv(1024).decode()
            print(f"Transaction details: {data}")
            conn.sendall("INFORM_Res Name CC# Exp_Date Address".encode())
        except Exception as e:
            print(f"Error during TCP transaction: {e}")
        finally:
            server_socket.close()

    def start(self):
        threading.Thread(target=self.listen_to_server, daemon=True).start()  # Start listening in a thread
        threading.Thread(target=self.handle_tcp_transaction).start()  # Start TCP handler in a thread

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

    input_serverIP = input("Enter Server's IP: ")
    server_ip = input_serverIP

    # Single-line input for peer details
    input_line = input("Enter peer details (e.g., Peer1 6000 9000): ")
    name, udp_port, tcp_port = input_line.split()
    udp_port = int(udp_port)
    tcp_port = int(tcp_port)

    # Create Peer object
    peer = Peer(name, udp_port, tcp_port)
    peer.start()  # Start listening and TCP transaction handling

    # Interactive loop for actions
    while True:
        print("\nOptions:")
        print("1. Register")
        print("2. Deregister")
        print("3. Look for item")
        print("4. Add Item to Inventory")
        print("5. Exit")
        choice = input("Choose an option: ")
        if choice == "3" or choice == "4":
            itemName = input("Item_name: ")
            itemDescription = input("Description: ")
            itemPrice = float(input("Price: "))

        if choice == '1':
            peer.register_with_server()
        elif choice == '2':
            peer.deregister_with_server()
        elif choice == '3':
            peer.looking_for_item_server(itemName, itemDescription, itemPrice)
        elif choice == '4':
            peer.add_item_to_inventory(itemName, itemDescription, itemPrice)
        elif choice == '5':
            print("Exiting program.")
            break
        else:
            print("Invalid choice. Please try again.")

