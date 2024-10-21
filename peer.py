import socket
import threading
import time


# Function to register the peer with the server
def register_with_server(name, udp_port, tcp_port):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # todo: Why RQ# isn't passed as integer?
    register_msg = f"REGISTER RQ# {name} 127.0.0.1 {udp_port} {tcp_port}"
    print(f"Sending registration message: {register_msg}")
    udp_socket.sendto(register_msg.encode(), ('localhost', 5000))

    # Listen for response from server
    data, _ = udp_socket.recvfrom(1024)
    print(f"Server response for {name}: {data.decode()}")


# Function to handle TCP transactions
def handle_tcp_transaction(tcp_port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('localhost', tcp_port))
    server_socket.listen(1)

    conn, addr = server_socket.accept()     # Waits for the TCP connection to be made
    print(f"TCP transaction started with {addr}")

    data = conn.recv(1024).decode()
    print(f"Transaction details: {data}")

    conn.sendall("INFORM_Res Name CC# Exp_Date Address".encode())
    conn.close()


# Function to simulate a peer from input data
def simulate_peer(name, udp_port, tcp_port):
    # Start listening for TCP transactions in a separate thread
    tcp_thread = threading.Thread(target=handle_tcp_transaction, args=(tcp_port,))
    tcp_thread.start()

    # Register with the server
    register_with_server(name, udp_port, tcp_port)


# Read peer data from input file and simulate each peer
def simulate_peers_from_file(filename):
    with open(filename, 'r') as f:
        for line in f:
            # Parse each line as: PeerName UDP_Port TCP_Port
            name, udp_port, tcp_port = line.strip().split()
            udp_port = int(udp_port)
            tcp_port = int(tcp_port)

            # Run each peer in a separate thread for concurrency
            threading.Thread(target=simulate_peer, args=(name, udp_port, tcp_port)).start()
            time.sleep(1)  # Delay to simulate a staggered start


if __name__ == "__main__":
    # Simulate peers from the test_peers.txt file
    simulate_peers_from_file("test_peers.txt")
