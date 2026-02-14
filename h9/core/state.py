from h9.blockchain.blockchain import Blockchain
from h9.crypto.wallet import Wallet
from h9.network.node import Node
from h9.mining.miner import Miner

class State:
    def __init__(self):
        self.blockchain = Blockchain()
        self.current_wallet = None
        self.current_miner = None
        self.node = Node(self.blockchain)
        
        # Initialize default wallet if available
        wallets = Wallet.list_wallets()
        if wallets:
            try:
                self.current_wallet = Wallet(wallets[0])
                # Initialize miner with this wallet
                self.current_miner = Miner(self.current_wallet.get_address(), self.blockchain)
            except Exception as e:
                print(f"⚠️ Failed to load default wallet: {e}")

# Global singleton instance
state = State()
