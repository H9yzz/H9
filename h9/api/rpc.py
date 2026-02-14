from flask import Blueprint, request, jsonify
from h9.core.state import state
from h9.blockchain.transaction import Transaction

rpc = Blueprint('rpc', __name__)

@rpc.route('/json_rpc', methods=['POST'])
def json_rpc_handler():
    try:
        data = request.json
        if not data or 'jsonrpc' not in data or data['jsonrpc'] != '2.0':
            return jsonify({'error': {'code': -32600, 'message': 'Invalid Request'}, 'id': None})
            
        method = data.get('method')
        params = data.get('params', [])
        req_id = data.get('id')
        
        result = None
        error = None
        
        # Dispatch specific methods
        if method == 'get_block_count':
            result = len(state.blockchain.chain)
            
        elif method == 'get_balance':
            # params: [address]
            if not params or not isinstance(params, list):
                error = {'code': -32602, 'message': 'Invalid params'}
            else:
                address = params[0]
                result = state.blockchain.get_balance(address)
                
        elif method == 'send_raw_transaction':
            # params: [signed_tx_blob_string] or [signed_tx_dict]
            # We assume it matches the structure of broadcast_transaction
            if not params or not isinstance(params, list):
                error = {'code': -32602, 'message': 'Invalid params'}
            else:
                import json
                tx_input = params[0]
                if isinstance(tx_input, str):
                    try:
                        tx_data = json.loads(tx_input)
                    except:
                        error = {'code': -32700, 'message': 'Parse error'}
                        tx_data = None
                else:
                    tx_data = tx_input
                
                if tx_data:
                    try:
                        tx = Transaction.from_dict(tx_data)
                        if tx.public_key:
                             from h9.crypto.keys import KeyPair
                             derived = KeyPair.public_key_to_address(tx.public_key)
                             if derived != tx.sender:
                                 raise ValueError("Public Key mismatch")

                        if state.blockchain.add_transaction(tx):
                            result = tx.tx_id
                        else:
                            error = {'code': -32000, 'message': 'Transaction rejected'}
                    except Exception as e:
                        error = {'code': -32602, 'message': f'Invalid transaction: {str(e)}'}

        elif method == 'get_transaction':
             # params: [tx_id]
             # Not efficiently implemented in blockchain.py yet (needs index), 
             # but we can scan.
             if not params:
                 error = {'code': -32602, 'message': 'Invalid params'}
             else:
                 tx_id = params[0]
                 found = False
                 for block in state.blockchain.chain:
                     for tx in block.transactions:
                         if tx.tx_id == tx_id:
                             result = tx.to_dict()
                             result['block_height'] = block.index
                             result['block_hash'] = block.hash
                             found = True
                             break
                     if found: break
                 if not found:
                     # Check pending
                     for tx in state.blockchain.pending_transactions:
                         if tx.tx_id == tx_id:
                             result = tx.to_dict()
                             result['status'] = 'pending'
                             found = True
                             break
                 
                 if not found:
                     error = {'code': -32001, 'message': 'Transaction not found'}

        else:
            error = {'code': -32601, 'message': 'Method not found'}
            
        if error:
            return jsonify({'jsonrpc': '2.0', 'error': error, 'id': req_id})
        else:
            return jsonify({'jsonrpc': '2.0', 'result': result, 'id': req_id})
            
    except Exception as e:
        return jsonify({'jsonrpc': '2.0', 'error': {'code': -32603, 'message': f'Internal error: {str(e)}'}, 'id': None})
