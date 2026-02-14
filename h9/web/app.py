from flask import Flask, render_template, redirect, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime, timedelta
from h9.core.state import state  # Import shared state
from h9.crypto.wallet import Wallet
from h9.api.rest_api import api
from h9.api.rpc import rpc
from config import Config

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'h9_secret_key_2024'
socketio = SocketIO(app, cors_allowed_origins="*")

# Register Blueprints
app.register_blueprint(api, url_prefix='/api')
app.register_blueprint(rpc, url_prefix='/api')

# Helper: Load/Create Wallet
def init_default_wallet():
    wallets = Wallet.list_wallets()
    if wallets:
        try:
            state.current_wallet = Wallet(wallets[0])
            print(f"Loaded wallet: {wallets[0]}")
        except Exception as e:
            print(f"⚠️ Failed to load wallet {wallets[0]}: {e}")
            state.current_wallet = None
    else:
        print("⚠️ No wallets found.")
        state.current_wallet = None

init_default_wallet()

# Custom Jinja2 filter for timestamp_to_date
def timestamp_to_date(timestamp):
    try:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return "Unknown Date"

app.jinja_env.filters['timestamp_to_date'] = timestamp_to_date

# Custom error handler for 500 errors
@app.errorhandler(500)
def internal_error(error):
    print(f"⚠️ 500 Error: {str(error)}")
    return render_template('error.html', error_message="An unexpected error occurred. Please check server logs or try again."), 500

# Routes
@app.route('/')
def home():
    return redirect('/wallet')

@app.route('/wallet')
def wallet():
    wallets = Wallet.list_wallets()
    balance = 0
    transactions = []

    if not state.current_wallet and wallets:
        try:
            state.current_wallet = Wallet(wallets[0])
            print(f"✅ Loaded default wallet: {state.current_wallet.name}")
        except Exception as e:
            print(f"⚠️ Failed to load default wallet: {e}")
            state.current_wallet = None

    if state.current_wallet:
        try:
            balance = state.blockchain.get_balance(state.current_wallet.get_address())
            transactions = state.blockchain.get_transaction_history(state.current_wallet.get_address())
        except Exception as e:
            print(f"⚠️ Failed to fetch wallet data: {e}")
            balance = 0
            transactions = []

    return render_template("wallet.html",
                           wallet=state.current_wallet,
                           balance=balance,
                           transactions=transactions,
                           wallets=wallets)
@app.route('/miner')
def miner():
    if not state.current_wallet:
        return render_template('error.html', error_message="No wallet loaded. Please create or switch a wallet first."), 500

    if not state.current_miner:
        from h9.mining.miner import Miner
        state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)

    mining_stats = state.current_miner.get_mining_stats() if state.current_miner else {
        'is_mining': False,
        'hash_rate': 0,
        'blocks_mined': 0,
        'wallet_address': '',
        'difficulty': state.blockchain.difficulty
    }

    return render_template('miner.html', mining_stats=mining_stats)


@app.route('/chain')
def chain():
    # Defensive coding for chain page
    try:
        if not state.blockchain.chain:
            state.blockchain.load_or_create_genesis()
            
        blocks = [block.to_dict() for block in reversed(state.blockchain.chain[-10:])]
        stats = state.blockchain.get_stats()
        return render_template('chain.html', blocks=blocks, stats=stats)
    except Exception as e:
        print(f"Error rendering /chain: {e}")
        return render_template('error.html', error_message=f"Error loading blockchain: {e}")

@app.route('/node')
def node_page():
    peers = state.node.get_peers() if state.node else []
    node_stats = {
        'is_running': state.node.is_running if state.node else False,
        'peer_count': len(peers),
        'port': Config.P2P_PORT
    }
    return render_template('node.html', node_stats=node_stats, peers=peers)

@app.route('/settings')
def settings():
    return render_template('settings.html', config=Config)

# API Endpoints
@app.route('/api/mining/start', methods=['POST'])
def start_mining():
    try:
        if not state.current_wallet:
            return jsonify({'status': 'error', 'message': 'No wallet loaded'}), 400
        
        if not state.current_miner:
            from h9.mining.miner import Miner
            state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)
        
        if not state.current_miner.is_mining:
            state.current_miner.start_mining()
            print(f"✅ Mining started for wallet: {state.current_wallet.name}")
            return jsonify({'status': 'success', 'message': 'Mining started successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Mining is already active'}), 400
            
    except Exception as e:
        print(f"❌ Error starting mining: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/mining/stop', methods=['POST'])
def stop_mining():
    try:
        if state.current_miner and state.current_miner.is_mining:
            state.current_miner.stop_mining()
            print("✅ Mining stopped")
            return jsonify({'status': 'success', 'message': 'Mining stopped successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Mining is not active'}), 400
            
    except Exception as e:
        print(f"❌ Error stopping mining: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/mining/stats')
def get_mining_stats_api():
    try:
        if not state.current_wallet:
            return jsonify({'error': 'No wallet loaded'}), 400
        
        if not state.current_miner:
            from h9.mining.miner import Miner
            state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)
        
        stats = state.current_miner.get_mining_stats() if state.current_miner else {}
        wallet_balance = state.blockchain.get_balance(state.current_wallet.get_address()) if state.current_wallet else 0
        
        return jsonify({
            'hash_rate': stats.get('hash_rate', 0),
            'blocks_mined': stats.get('blocks_mined', 0),
            'total_rewards': stats.get('total_rewards', 0),
            'is_mining': stats.get('is_mining', False),
            'difficulty': state.blockchain.difficulty if hasattr(state.blockchain, 'difficulty') else 1,
            'pending_transactions': len(state.blockchain.pending_transactions) if hasattr(state.blockchain, 'pending_transactions') else 0,
            'wallet_balance': wallet_balance,
            'wallet_address': state.current_wallet.get_address(),
            'mining_reward': stats.get('mining_reward', 1.0),
            'target_block_time': stats.get('target_block_time', 60),
            'total_hash_count': stats.get('total_hash_count', 0),
            'mining_duration': stats.get('mining_duration', 0),
            'timestamp': time.time()
        })
    except Exception as e:
        print(f"❌ Error getting mining stats: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mining/hashrate-history')
def get_hashrate_history():
    if not state.current_miner:
        return jsonify({'error': 'No active miner'}), 400
    
    history = getattr(state.current_miner, 'hash_rate_history', [])
    if not history:
        current_hash_rate = state.current_miner.get_mining_stats().get('hash_rate', 0)
        now = datetime.now()
        history = []
        for i in range(20):
            timestamp = now - timedelta(minutes=i)
            variation = current_hash_rate * 0.1 * (0.5 - abs(i % 10 - 5) / 10)
            hash_rate = max(0, current_hash_rate + variation)
            history.append({
                'timestamp': timestamp.isoformat(),
                'hash_rate': round(hash_rate, 2)
            })
        history.reverse()
    
    return jsonify(history)

@app.route('/api/mining/pending-transactions')
def get_pending_transactions():
    pending_txs = []
    if hasattr(state.blockchain, 'pending_transactions'):
        for tx in state.blockchain.pending_transactions[:10]:
            pending_txs.append({
                'from_address': tx.from_address if hasattr(tx, 'from_address') else 'N/A',
                'to_address': tx.to_address if hasattr(tx, 'to_address') else 'N/A',
                'amount': tx.amount if hasattr(tx, 'amount') else 0,
                'timestamp': getattr(tx, 'timestamp', time.time())
            })
    return jsonify(pending_txs)

@app.route('/wallet/switch', methods=['POST'])
def switch_wallet_route():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'status': 'error', 'message': 'Missing wallet name'}), 400

        name = data.get('name')
        if not name:
            return jsonify({'status': 'error', 'message': 'Wallet name cannot be empty'}), 400

        if name not in Wallet.list_wallets():
            return jsonify({'status': 'error', 'message': f'Wallet {name} not found'}), 404

        try:
            state.current_wallet = Wallet(name)
        except ValueError as e:
            print(f"❌ Failed to load wallet {name}: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500

        if state.current_miner:
            try:
                state.current_miner.stop_mining()
                from h9.mining.miner import Miner
                state.current_miner = Miner(state.current_wallet.get_address(), state.blockchain)
            except Exception as e:
                print(f"❌ Failed to update miner: {e}")
                return jsonify({'status': 'error', 'message': f'Failed to update miner: {str(e)}'}), 500

        print(f"✅ Wallet switched to: {state.current_wallet.name}")
        return jsonify({
            'status': 'success',
            'message': f'Switched to wallet: {name}',
            'wallet': {
                'name': state.current_wallet.name,
                'address': state.current_wallet.get_address(),
                'balance': state.blockchain.get_balance(state.current_wallet.get_address())
            }
        })

    except Exception as e:
        print(f"❌ Wallet switch failed: {e}")
        return jsonify({'status': 'error', 'message': f'Server error: {str(e)}'}), 500

# Helper Functions
def calculate_estimated_block_time(hash_rate):
    if hash_rate <= 0:
        return "∞"
    difficulty = state.blockchain.difficulty if hasattr(state.blockchain, 'difficulty') else 1
    estimated_seconds = (difficulty * 1000000) / hash_rate
    if estimated_seconds < 60:
        return f"{estimated_seconds:.1f}s"
    elif estimated_seconds < 3600:
        return f"{estimated_seconds/60:.1f}m"
    else:
        return f"{estimated_seconds/3600:.1f}h"

def calculate_mining_efficiency(hash_rate, difficulty):
    if difficulty <= 0:
        return 100
    base_efficiency = (hash_rate / (difficulty * 1000)) * 100
    return min(100, max(0, base_efficiency))

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status', {'message': 'Connected to H9'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('get_stats')
def handle_get_stats():
    """Handle explicit stats request from client"""
    send_stats()

def send_stats():
    """Helper to gather and emit stats"""
    try:
        blockchain_stats = state.blockchain.get_stats()
        mining_stats = state.current_miner.get_mining_stats() if state.current_miner else {'is_mining': False}
        wallet_balance = 0
        wallet_address = ''
        
        if state.current_wallet:
            try:
                wallet_balance = state.blockchain.get_balance(state.current_wallet.get_address())
                wallet_address = state.current_wallet.get_address()
            except Exception as e:
                print(f"⚠️ Error getting wallet balance: {e}")
        
        node_stats = {
            'is_running': state.node.is_running if state.node else False,
            'peer_count': len(state.node.get_peers()) if state.node else 0
        }
        
        stats = {
            'blockchain': blockchain_stats,
            'mining': mining_stats,
            'wallet': {
                'address': wallet_address,
                'balance': wallet_balance
            },
            'node': node_stats,
            'timestamp': time.time()
        }
        
        socketio.emit('stats_update', stats)
    except Exception as e:
        print(f"Error sending stats: {e}")

# Periodic Background Updates
def background_updates():
    while True:
        try:
            socketio.sleep(2)
            send_stats()
        except Exception as e:
            print(f"⚠️ Error in background updates: {e}")
            socketio.sleep(5)

socketio.start_background_task(background_updates)

# Run the App
if __name__ == '__main__':
    socketio.run(app, debug=True, port=Config.WEB_PORT)
