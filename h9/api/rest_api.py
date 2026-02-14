from flask import Blueprint, request, jsonify
from h9.core.state import state
from h9.blockchain.transaction import Transaction
from h9.crypto.wallet import Wallet
from h9.mining.miner import Miner
from config import Config
import time

api = Blueprint('api', __name__)

@api.route('/wallet/create', methods=['POST'])
def create_wallet():
    name = request.json.get('name', f'wallet_{int(time.time())}')
    new_wallet = Wallet(name)
    # Automatically switch to new wallet? Maybe not, just create.
    # But for single-user feel, maybe yes?
    # Let's just create it. The UI creates then reloads, which triggers load logic.
    return jsonify({'status': 'success', 'address': new_wallet.get_address()})


@api.route('/wallet/switch', methods=['POST'])
def switch_wallet():
    name = request.json.get('name')
    if name in Wallet.list_wallets():
        try:
            state.current_wallet = Wallet(name)
            # Update miner if exists
            if state.current_miner:
                 state.current_miner.stop_mining()
                 state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)
                 
            return jsonify({'status': 'success'})
        except Exception as e:
             return jsonify({'status': 'error', 'message': str(e)})
             
    return jsonify({'status': 'error', 'message': 'Wallet not found'})


@api.route('/transaction/send', methods=['POST'])
def send_transaction():
    data = request.json
    recipient = data.get('recipient')
    
    try:
        amount = float(data.get('amount'))
        fee = float(data.get('fee', 0.01))
    except (ValueError, TypeError):
        return jsonify({'status': 'error', 'message': 'Invalid amount or fee'})

    if not state.current_wallet:
        return jsonify({'status': 'error', 'message': 'No wallet selected'})

    balance = state.blockchain.get_balance(state.current_wallet.get_address())
    if balance < amount + fee:
        return jsonify({'status': 'error', 'message': 'Insufficient balance'})

    # Create transaction
    try:
        # We need to use state.current_wallet keys
        # Transaction class needs private key to sign.
        # But wait, Wallet class usually has methods to create tx.
        # Let's see how Wallet creates tx. 
        # Wallet.create_transaction_offline? No, that's for offline.
        # Standard:
        tx = Transaction(state.current_wallet.get_address(), recipient, amount, fee)
        tx.sign_transaction(state.current_wallet.keypair.get_private_key_hex())

        if state.blockchain.add_transaction(tx):
            try:
                state.node.broadcast_transaction(tx) # Broadcast via P2P
            except Exception as e:
                print(f"⚠️ Warning: P2P broadcast failed (transaction is valid locally): {e}")
                
            return jsonify({'status': 'success', 'tx_id': tx.tx_id})
        return jsonify({'status': 'error', 'message': 'Transaction failed verification'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@api.route('/transaction/broadcast', methods=['POST'])
def broadcast_transaction():
    """Endpoint for broadcasting pre-signed transactions (offline signing)"""
    try:
        data = request.json
        tx = Transaction.from_dict(data)
        
        # We assume signature is valid (verified by add_transaction)
        # We assume signature is valid (verified by add_transaction)
        if state.blockchain.add_transaction(tx): 
             try:
                 state.node.broadcast_transaction(tx) # Broadcast via P2P
             except Exception as e:
                 print(f"⚠️ Warning: P2P broadcast failed (transaction is valid locally): {e}")

             return jsonify({'status': 'success', 'tx_id': tx.tx_id})
        else:
             return jsonify({'status': 'error', 'message': 'Transaction rejected by node'})
             
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Invalid transaction data: {str(e)}'})


@api.route('/mining/start', methods=['POST'])
def start_mining():
    if not state.current_wallet:
         return jsonify({'status': 'error', 'message': 'No wallet loaded'})
         
    if not state.current_miner:
         state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)
         
    state.current_miner.start_mining()
    return jsonify({'status': 'success'})


@api.route('/mining/stop', methods=['POST'])
def stop_mining():
    if state.current_miner:
        state.current_miner.stop_mining()
    return jsonify({'status': 'success'})


@api.route('/node/start', methods=['POST'])
def start_node():
    if state.node:
        state.node.start()
    return jsonify({'status': 'success'})


@api.route('/node/stop', methods=['POST'])
def stop_node():
    if state.node:
        state.node.stop()
    return jsonify({'status': 'success'})


@api.route('/stats', methods=['GET'])
def get_stats():
    wallet_data = {}
    if state.current_wallet:
        wallet_data = {
            'address': state.current_wallet.get_address(),
            'balance': state.blockchain.get_balance(state.current_wallet.get_address())
        }
        
    mining_stats = {}
    if state.current_miner:
        mining_stats = state.current_miner.get_mining_stats()
        
    return jsonify({
        'blockchain': state.blockchain.get_stats(),
        'wallet': wallet_data,
        'mining': mining_stats,
        'node': {
            'is_running': state.node.is_running if state.node else False,
            'peer_count': len(state.node.get_peers()) if state.node else 0
        }
    })
