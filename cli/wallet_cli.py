import argparse
from h9.crypto.wallet import Wallet

def create_wallet(name):
    wallet = Wallet(name)
    print(f"✅ Wallet created: {wallet.name}")
    print(f"📬 Address: {wallet.get_address()}")

def list_wallets():
    wallets = Wallet.list_wallets()
    if wallets:
        print("🔐 Available wallets:")
        for w in wallets:
            print(f" - {w}")
    else:
        print("⚠️ No wallets found.")

def check_balance(name):
    if name not in Wallet.list_wallets():
        print(f"❌ Wallet '{name}' not found.")
        return
    wallet = Wallet(name)
    print(f"🔍 Wallet: {wallet.name}")
    print(f"📬 Address: {wallet.get_address()}")
    print(f"💰 Balance: {wallet.balance} H9")
    print(f"📜 Transactions: {len(wallet.transactions)}")

def show_seed(name):
    if name not in Wallet.list_wallets():
        print(f"❌ Wallet '{name}' not found.")
        return
    wallet = Wallet(name)
    if wallet.seed:
        print(f"🔐 Seed for '{name}':")
        print(wallet.seed)
    else:
        print(f"❌ No seed found for wallet '{name}' (Legacy wallet?)")

def sign_transaction(name, recipient, amount, fee=0.01):
    if name not in Wallet.list_wallets():
        print(f"❌ Wallet '{name}' not found.")
        return
    
    wallet = Wallet(name)
    try:
        tx_blob = wallet.create_transaction_offline(recipient, float(amount), float(fee))
        print("📝 Signed Transaction Blob:")
        print("=" * 60)
        print(tx_blob)
        print("=" * 60)
        print("Copy the above blob and use 'broadcast' command on a connected node.")
    except Exception as e:
        print(f"❌ Error signing transaction: {e}")

def broadcast_transaction(tx_blob):
    import requests
    from config import Config
    
    try:
        # We need to reconstruct the transaction dict or send it raw if API supports it.
        # Current /api/transaction/send expects fields, but let's see if we can add a new endpoint 
        # or adapt the current one.
        # Actually, let's look at how we can implement this.
        # option 1: Add a new endpoint /api/transaction/broadcast that takes the blob.
        # option 2: Client parses blob and sends to /api/transaction/send 
        # (BUT /send currently signs it again! We need a raw endpoint).
        
        # We need to add a new endpoint for raw transactions or modify the existing one.
        # Let's assume we will add /api/transaction/broadcast later in Phase 2.
        # For now, let's try to send it to a new endpoint we will create.
        
        url = f"http://localhost:{Config.WEB_PORT}/api/transaction/broadcast"
        headers = {'Content-Type': 'application/json'}
        response = requests.post(url, data=tx_blob, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result['status'] == 'success':
                print(f"✅ Transaction broadcasted! TX ID: {result.get('tx_id')}")
            else:
                print(f"❌ Broadcast failed: {result.get('message')}")
        else:
            print(f"❌ Server returned error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Connection error: {e}")

def main():
    parser = argparse.ArgumentParser(description="H9 Wallet CLI")
    subparsers = parser.add_subparsers(dest="command")

    parser_create = subparsers.add_parser("create", help="Create a new wallet")
    parser_create.add_argument("name", help="Wallet name")

    parser_restore = subparsers.add_parser("restore", help="Restore wallet from seed")
    parser_restore.add_argument("name", help="Wallet name")
    parser_restore.add_argument("seed", help="Seed phrase (surrounded by quotes)")

    parser_list = subparsers.add_parser("list", help="List wallets")

    parser_balance = subparsers.add_parser("balance", help="Check wallet balance")
    parser_balance.add_argument("name", help="Wallet name")

    parser_seed = subparsers.add_parser("show-seed", help="Show wallet seed phrase")
    parser_seed.add_argument("name", help="Wallet name")
    
    parser_sign = subparsers.add_parser("sign", help="Sign a transaction offline")
    parser_sign.add_argument("name", help="Wallet name")
    parser_sign.add_argument("recipient", help="Recipient address")
    parser_sign.add_argument("amount", help="Amount to send")
    parser_sign.add_argument("--fee", help="Transaction fee", default=0.01)

    parser_broadcast = subparsers.add_parser("broadcast", help="Broadcast a signed transaction")
    parser_broadcast.add_argument("blob", help="Signed transaction blob (JSON)")

    args = parser.parse_args()

    if args.command == "create":
        create_wallet(args.name)
    elif args.command == "restore":
        restore_wallet(args.name, args.seed)
    elif args.command == "list":
        list_wallets()
    elif args.command == "balance":
        check_balance(args.name)
    elif args.command == "show-seed":
        show_seed(args.name)
    elif args.command == "sign":
        sign_transaction(args.name, args.recipient, args.amount, args.fee)
    elif args.command == "broadcast":
        broadcast_transaction(args.blob)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
