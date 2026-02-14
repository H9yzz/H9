import socket
import threading
import json
import time
from config import Config, load_peers, save_peers

class Node:
    def __init__(self, blockchain, port=Config.P2P_PORT):
        self.blockchain = blockchain
        self.port = port
        self.peers = set(load_peers())
        self.is_running = False
        self.server_socket = None
        self.peer_threads = []
        
    def start(self):
        """Start the P2P node"""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Start server to accept incoming connections
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(10)
            print(f"P2P Node started on port {self.port}")
            
            # Start accepting connections
            server_thread = threading.Thread(target=self._accept_connections)
            server_thread.daemon = True
            server_thread.start()
            
            # Connect to known peers
            self._connect_to_peers()
            
            # Start peer discovery
            discovery_thread = threading.Thread(target=self._peer_discovery)
            discovery_thread.daemon = True
            discovery_thread.start()
            
        except Exception as e:
            print(f"Failed to start node: {e}")
            self.is_running = False
    
    def stop(self):
        """Stop the P2P node"""
        self.is_running = False
        
        if self.server_socket:
            self.server_socket.close()
            
        for thread in self.peer_threads:
            if thread.is_alive():
                thread.join(timeout=1)
        
        print("P2P Node stopped")
    
    def _accept_connections(self):
        """Accept incoming peer connections"""
        while self.is_running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"New peer connected: {address}")
                
                peer_thread = threading.Thread(
                    target=self._handle_peer, 
                    args=(client_socket, address)
                )
                peer_thread.daemon = True
                peer_thread.start()
                self.peer_threads.append(peer_thread)
                
            except Exception as e:
                if self.is_running:
                    print(f"Error accepting connection: {e}")
    
    def _handle_peer(self, client_socket, address):
        """Handle communication with a peer"""
        try:
            while self.is_running:
                data = client_socket.recv(4096)
                if not data:
                    break
                    
                try:
                    message = json.loads(data.decode())
                    self._handle_message(message, client_socket)
                except json.JSONDecodeError:
                    print(f"Invalid JSON from {address}")
                    
        except Exception as e:
            print(f"Error handling peer {address}: {e}")
        finally:
            client_socket.close()
    
    def _handle_message(self, message, client_socket):
        """Handle incoming messages from peers"""
        msg_type = message.get('type')
        
        if msg_type == 'get_status':
            # Send our status (height, top hash)
            latest = self.blockchain.get_latest_block()
            response = {
                'type': 'status',
                'data': {
                    'height': len(self.blockchain.chain),
                    'best_hash': latest.hash if latest else None,
                    'difficulty': self.blockchain.difficulty
                }
            }
            self._send_message(client_socket, response)
            
        elif msg_type == 'status':
            # Received peer status, check if we need to sync
            peer_height = message['data']['height']
            peer_hash = message['data']['best_hash']
            
            my_height = len(self.blockchain.chain)
            # Simple check: if peer is ahead, request chain
            # In a real system, we'd check hash to handle forks even at same height
            if peer_height > my_height:
                print(f"Peer is ahead (H:{peer_height} > {my_height}). Requesting chain...")
                self._send_message(client_socket, {'type': 'get_chain'})
            else:
                print(f"Peer is synced or behind (H:{peer_height} <= {my_height}).")

        elif msg_type == 'get_chain':
            # Send our blockchain
            response = {
                'type': 'chain',
                'data': [block.to_dict() for block in self.blockchain.chain]
            }
            self._send_message(client_socket, response)
            
        elif msg_type == 'chain':
            # Received a blockchain from peer
            self._handle_received_chain(message['data'])
            
        elif msg_type == 'new_transaction':
            # Received a new transaction
            from h9.blockchain.transaction import Transaction
            tx = Transaction.from_dict(message['data'])
            # Only add if valid and new
            if self.blockchain.add_transaction(tx):
                print(f"Received new TX: {tx.tx_id}")
            
        elif msg_type == 'new_block':
            # Received a new block
            from h9.blockchain.block import Block
            block = Block.from_dict(message['data'])
            self._handle_new_block(block)
            
        elif msg_type == 'peer_list':
            # Received peer list
            new_peers = set(message['data'])
            self.peers.update(new_peers)
            save_peers(list(self.peers))
        
        elif msg_type == 'get_peers':
            # Peer requested our peer list; respond with current peers
            response = {
                'type': 'peer_list',
                'data': list(self.peers)
            }
            self._send_message(client_socket, response)
    
    def _handle_received_chain(self, chain_data):
        """Handle received blockchain from peer"""
        try:
            from h9.blockchain.block import Block
            received_chain = [Block.from_dict(block_data) for block_data in chain_data]
            
            # Check if received chain is longer and valid
            if len(received_chain) > len(self.blockchain.chain):
                # Create temporary blockchain to validate
                temp_blockchain = type(self.blockchain)()
                temp_blockchain.chain = received_chain
                
                if temp_blockchain.is_chain_valid():
                    print("Replacing chain with longer valid chain")
                    
                    # Mempool Preservation:
                    # 1. Save current pending txs
                    old_mempool = list(self.blockchain.pending_transactions)
                    
                    # 2. Add txs from orphaned blocks (blocks in our chain but not in new chain)
                    # Simple approach: Since we are replacing entirely, all our blocks after common ancestor are orphans.
                    # But here we just assume entire replacement.
                    # Actually, we should check which txs from our old chain are NOT in the new chain.
                    # For simplicity in this iteration: just preserve old mempool and try to re-add.
                    
                    self.blockchain.chain = received_chain
                    self.blockchain.save_blockchain()
                    
                    # 3. Re-add valid txs from old mempool
                    print(f"Re-evaluating {len(old_mempool)} pending transactions...")
                    preserved_count = 0
                    self.blockchain.pending_transactions = [] # Clear first
                    for tx in old_mempool:
                        if self.blockchain.add_transaction(tx):
                            preserved_count += 1
                    print(f"Preserved {preserved_count} transactions.")
                    
        except Exception as e:
            print(f"Error handling received chain: {e}")
    
    def _handle_new_block(self, block):
        """Handle new block from peer"""
        try:
            # Verify block is valid and extends our chain
            latest_block = self.blockchain.get_latest_block()
            
            if (block.index == latest_block.index + 1 and 
                block.previous_hash == latest_block.hash and
                block.is_valid(latest_block)):
                
                self.blockchain.chain.append(block)
                self.blockchain.save_blockchain()
                print(f"Added new block #{block.index}")
                
                # Broadcast to other peers
                self._broadcast_block(block)
                
        except Exception as e:
            print(f"Error handling new block: {e}")
    
    def _connect_to_peers(self):
        """Connect to known peers"""
        for peer in list(self.peers):
            try:
                host, port = peer.split(':')
                port = int(port)
                
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect((host, port))
                
                # Request their status (Enhanced Sync)
                message = {'type': 'get_status'}
                self._send_message(peer_socket, message)
                
                # Request their peer list
                message = {'type': 'get_peers'}
                self._send_message(peer_socket, message)
                
                peer_socket.close()
                
            except Exception as e:
                print(f"Failed to connect to peer {peer}: {e}")
                self.peers.discard(peer)
    
    def _peer_discovery(self):
        """Discover new peers periodically"""
        while self.is_running:
            try:
                # Try to discover peers on local network
                self._discover_local_peers()
                time.sleep(30)  # Discovery every 30 seconds
            except Exception as e:
                print(f"Peer discovery error: {e}")
                time.sleep(30)
    
    def _discover_local_peers(self):
        """Discover peers on local network"""
        import subprocess
        import re
        
        try:
            # Get local network range
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True)
            
            for line in result.stdout.split('\n'):
                if 'src' in line and '192.168' in line:
                    network = re.search(r'192\.168\.\d+\.0/24', line)
                    if network:
                        network_base = network.group().split('/')[0][:-1]  # Remove .0
                        
                        # Scan common IP range
                        for i in range(1, 255):
                            ip = f"{network_base}{i}"
                            peer = f"{ip}:{Config.P2P_PORT}"
                            
                            if peer not in self.peers:
                                # Quick check if port is open
                                if self._is_port_open(ip, Config.P2P_PORT):
                                    self.peers.add(peer)
                                    print(f"Discovered new peer: {peer}")
                        break
                        
        except Exception as e:
            print(f"Local discovery error: {e}")
    
    def _is_port_open(self, host, port, timeout=1):
        """Check if a port is open on a host"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except:
            return False
    
    def _send_message(self, socket, message):
        """Send message to peer"""
        try:
            data = json.dumps(message).encode()
            socket.send(data)
        except Exception as e:
            print(f"Error sending message: {e}")
    
    def _broadcast_message(self, message):
        """Broadcast message to all peers"""
        for peer in list(self.peers):
            try:
                host, port = peer.split(':')
                port = int(port)
                
                peer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_socket.connect((host, port))
                self._send_message(peer_socket, message)
                peer_socket.close()
                
            except Exception as e:
                # Connection errors are normal in P2P
                # print(f"DEBUG: Could not broadcast to {peer}: {e}")
                self.peers.discard(peer)
    
    def broadcast_transaction(self, transaction):
        """Broadcast new transaction to peers"""
        message = {
            'type': 'new_transaction',
            'data': transaction.to_dict()
        }
        self._broadcast_message(message)
    
    def _broadcast_block(self, block):
        """Broadcast new block to peers"""
        message = {
            'type': 'new_block',
            'data': block.to_dict()
        }
        self._broadcast_message(message)
    
    def get_peers(self):
        """Get list of connected peers"""
        return list(self.peers)
    
    def add_peer(self, peer_address):
        """Manually add a peer"""
        self.peers.add(peer_address)
        save_peers(list(self.peers))
