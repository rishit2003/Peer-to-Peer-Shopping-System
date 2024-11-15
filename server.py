# server.py
import socket
import threading
import logging

class Server:
    def __init__(self):
        self.registered_peers = {}
        self.peer_lock = threading.Lock()

    def udp_listener(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_socket.bind(('localhost', 5000))
        logging.info("Server started, listening on UDP port 5000...")

        while True:
            data, addr = server_socket.recvfrom(1024)
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
                response = f"REGISTERED {rq_number}"

        self.send_udp_response(response, addr)

    def handle_deregister(self, message_parts, addr):
        rq_number = message_parts[1]
        name = message_parts[2]

        with self.peer_lock:
            if name in self.registered_peers:
                del self.registered_peers[name]
                response = f"DE-REGISTERED {rq_number}"
            else:
                response = f"DE-REGISTER-DENIED {rq_number} Name not found"
        self.send_udp_response(response, addr)

    def handle_search(self, message_parts, addr):
        # Implementation omitted for brevity
        pass

    def handle_offer(self, message_parts, addr):
        # Implementation omitted for brevity
        pass

    def send_udp_response(self, message, addr):
        with self.peer_lock:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.sendto(message.encode(), addr)
            udp_socket.close()

    def start(self):
        threading.Thread(target=self.udp_listener).start()

if __name__ == "__main__":
    server = Server()
    server.start()
