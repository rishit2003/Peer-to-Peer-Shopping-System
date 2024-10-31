import socket
import threading
import logging

# Setup logging
logging.basicConfig(filename='peers.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Dictionary to store registered peers
registered_peers = {}
# Lock to ensure thread safety when accessing shared data
peer_lock = threading.Lock()


def udp_listener():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(('localhost', 5000))
    logging.info("Server started, listening on UDP port 5000...")  # Log server start

    while True:
        data, addr = server_socket.recvfrom(1024)
        message = data.decode()
        logging.info(f"Received message from {addr}: {message}")  # Log received message
        threading.Thread(target=handle_udp_message, args=(data, addr)).start()


def handle_udp_message(data, addr):
    message = data.decode()
    message_parts = message.split()
    msg_type = message_parts[0]

    if msg_type == "REGISTER":
        handle_register(message_parts, addr)
    elif msg_type == "DE-REGISTER":
        handle_deregister(message_parts, addr)
    elif msg_type == "LOOKING_FOR":
        handle_search(message_parts, addr)
    elif msg_type == "OFFER":
        handle_offer(message_parts, addr)
    else:
        logging.warning(f"Unknown message type from {addr}: {message}")


def handle_register(message_parts, addr):
    rq_number = message_parts[1]
    name = message_parts[2]
    udp_socket = message_parts[4]
    tcp_socket = message_parts[5]       # For Storing the TCP socket for checkout

    with peer_lock:
        if name in registered_peers:
            response = f"REGISTER-DENIED {rq_number} Name already in use"
            logging.info(f"Registration denied for {name} (already in use).")
        else:
            # Register the peer
            registered_peers[name] = {'address': addr, 'udp_socket': udp_socket, 'tcp_socket': tcp_socket}
            response = f"REGISTERED {rq_number}"
            logging.info(f"Registered {name} with UDP port {udp_socket} and TCP port {tcp_socket}")

    send_udp_response(response, addr)


def handle_deregister(message_parts, addr):
    rq_number = message_parts[1]
    name = message_parts[2]

    with peer_lock:
        if name in registered_peers:
            del registered_peers[name]
            logging.info(f"{name} de-registered successfully.")
        else:
            logging.warning(f"DE-REGISTER ignored. {name} not found.")


def handle_search(message_parts, addr):
    rq_number = message_parts[1]
    name = message_parts[2]
    item_name = message_parts[3]
    item_description = " ".join(message_parts[4:-1])
    max_price = message_parts[-1]

    with peer_lock:
        for peer_name, peer_info in registered_peers.items():
            if peer_name != name:
                search_msg = f"SEARCH {rq_number} {item_name} {item_description}"
                send_udp_response(search_msg, peer_info['address'])
                logging.info(f"SEARCH request from {name} forwarded to {peer_name} for item '{item_name}'")


def handle_offer(message_parts, addr):
    rq_number = message_parts[1]
    seller_name = message_parts[2]
    item_name = message_parts[3]
    price = message_parts[4]

    logging.info(f"Offer received from {seller_name} for item '{item_name}' at price {price}")
    #todo: Further logic like negotiation to be handled here


def send_udp_response(message, addr):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.sendto(message.encode(), addr)
    logging.info(f"Sent UDP response to {addr}: {message}")


if __name__ == "__main__":
    udp_thread = threading.Thread(target=udp_listener)
    udp_thread.start()

#todo: create txt file with registered clients and deregistered clients
