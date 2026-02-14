import hashlib
import ecdsa
from ecdsa import SigningKey, SECP256k1
import binascii
import os

class KeyPair:
    def __init__(self, private_key=None):
        if private_key:
            if isinstance(private_key, str):
                private_key = binascii.unhexlify(private_key)
            self.private_key = SigningKey.from_string(
                private_key, curve=SECP256k1
            )
        else:
            self.private_key = SigningKey.generate(curve=SECP256k1)
        
        self.public_key = self.private_key.get_verifying_key()
    
    @classmethod
    def from_seed(cls, seed):
        """Derive keypair from seed phrase (simplified)"""
        if isinstance(seed, str):
            seed = seed.encode()
        # Use SHA256 of seed as private key (Simple derivation)
        # In production, use BIP-32/39 standard derivation
        private_key_bytes = hashlib.sha256(seed).digest()
        return cls(private_key=binascii.hexlify(private_key_bytes).decode())
    
    def get_private_key_hex(self):
        return binascii.hexlify(self.private_key.to_string()).decode()
    
    def get_public_key_hex(self):
        return binascii.hexlify(self.public_key.to_string()).decode()
    
    def get_address(self):
        """Generate wallet address from public key"""
        return self.public_key_to_address(self.get_public_key_hex())

    @staticmethod
    def public_key_to_address(public_key_hex):
        """Generate wallet address from public key hex"""
        sha256_hash = hashlib.sha256(public_key_hex.encode()).hexdigest()
        ripemd160 = hashlib.new('ripemd160')
        ripemd160.update(sha256_hash.encode())
        return ripemd160.hexdigest()[:20]  # Take first 20 characters
    
    def sign_message(self, message):
        """Sign a message with private key"""
        message_hash = hashlib.sha256(message.encode()).digest()
        signature = self.private_key.sign(message_hash)
        return binascii.hexlify(signature).decode()
    
    @staticmethod
    def verify_signature(message, signature, public_key_hex):
        """Verify signature using public key"""
        try:
            public_key = ecdsa.VerifyingKey.from_string(
                binascii.unhexlify(public_key_hex), curve=SECP256k1
            )
            # Create a verifying key from the public key hex
            # signature is hex string, convert to bytes
            # message is string, convert to bytes and hash
            
            # The library might expect the raw message or the hash depending on method
            # Here we use the same method as signing: hash the message first
            if isinstance(message, str):
                message = message.encode()
            message_hash = hashlib.sha256(message).digest()
            
            return public_key.verify(binascii.unhexlify(signature), message_hash)
        except Exception as e:
            # print(f"Verification error: {e}")
            return False
