# Peer-to-Peer Shopping System

This project implements a Peer-to-Peer (P2P) Shopping System that allows users to buy and sell items through a server-mediated communication model. The system uses **UDP** for general communication and **TCP** for secure transactions, ensuring the safety and efficiency of peer interactions.

---

## Features

- **Registration and Deregistration**: Peers can register with the server to participate in the system and deregister when done.
- **Item Searching and Offering**: Buyers can search for items, and sellers can offer items with a specified price.
- **Secure Transactions**: Sensitive buyer-seller information is transmitted securely via TCP.
- **Dynamic Negotiation**: The server facilitates price negotiations between buyers and sellers if no offer matches the buyer's maximum price.
- **Persistent State**: Both server and peers persist their state to handle restarts without data loss.
- **Logging**: Comprehensive logging of activities for debugging and tracking purposes.

---

## Technologies Used

- **Programming Language**: Python
- **Networking**: UDP and TCP sockets
- **Data Persistence**: JSON-based storage for peer inventory and server state
- **Threading**: Multithreaded architecture for concurrent request handling
- **Logging**: Centralized logging for peers and server

---

## How It Works

### System Overview
1. **Registration**: A peer registers with the server using its unique name and socket details.
2. **Item Search**: Buyers send item search requests to the server, which forwards the search to all registered sellers.
3. **Offers**: Sellers respond with offers if the item is available in their inventory.
4. **Negotiation**: If no valid offers match, the server negotiates with the seller offering the lowest price.
5. **Transaction Finalization**: Once a buyer accepts an offer, TCP connections handle sensitive data exchange (e.g., credit card details and shipping addresses).

---

## Installation

### Prerequisites
- Python 3.6 or higher installed on your system.

### Steps
1. Clone the repository:
   ```bash
   git clone https://github.com/rishit2003/Peer-to-Peer-Shopping-System.git
   cd Peer-to-Peer-Shopping-System
   ```

2. Install dependencies (if any).

3. Run the server:
   ```bash
   python server.py
   ```

4. Run a peer client:
   ```bash
   python peer.py
   ```

---

## Usage

1. **Start the Server**:
   - Run `server.py` and enter the desired UDP port when prompted.

2. **Start a Peer**:
   - Run `peer.py` for each peer and provide the server IP, server UDP port, peer name, and peer's UDP and TCP ports.

3. **Interactive Menu**:
   - The peer provides options to register, deregister, search for items, add inventory items, and exit.

---

## Project Structure

### Peer Side
```
Peer-to-Peer-Shopping-System/
│
├── peer.py                 # Main script for peer operations
├── <peer_name>_inventory.json  # Inventory storage for each peer
├── <peer_name>.log         # Peer log file
└── README.md               # Project documentation
```
### Server Side
```
Peer-to-Peer-Shopping-System/
│
├── server.py               # Main script for server operation
├── server.json             # Persistent state storage for the server
├── server.log              # Server log file
└── README.md               # Project documentation
```

---

## Example Workflow

1. **Register a Peer**:  
   Peer1 sends a `REGISTER` request to the server.

2. **Search for an Item**:  
   Peer1 sends a `LOOKING_FOR` request for an item (e.g., "Laptop").

3. **Receive Offers**:  
   Sellers respond with `OFFER` messages if the item is available.

4. **Transaction Finalization**:  
   Upon acceptance, a TCP connection handles secure credit card and shipping details.

---

## Screenshots

- **Server Startup**  
  ![Server Startup](screenshots/server_startup.png)

- **Peer Registration**  
  ![Peer Registration](screenshots/peer_registration.png)

- **Item Search**  
  ![Item Search](screenshots/item_search.png)

- **Transaction Finalization**  
  ![Transaction Finalization](screenshots/transaction_finalization.png)


---

## Logging

- **Server Logs**: Logs server operations, requests, and state updates in `server.log`.
- **Peer Logs**: Each peer logs its activities (e.g., sent messages, inventory updates) in `<peer_name>.log`.

---

## Future Enhancements

- Add a GUI for easier interaction.
- Implement user authentication for additional security.
- Optimize message handling for scalability.

---

## Contributors

- **Rishit Mittal** ([rishit2003](https://github.com/rishit2003))
- **Rayan Alkayal** ([Rayan99k](https://github.com/Rayan99k))
- **Mohammad Natsheh** ([Mordred311](https://github.com/Mordred311))

---
