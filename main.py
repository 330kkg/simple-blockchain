# main.py
# Простой блокчейн с Flask API, мемпулом, майнингом и поддержкой веб-интерфейса
# Поддерживает: транзакции, майнинг, синхронизацию узлов, баланс, CORS
# Запуск: python main.py [порт]  (по умолчанию 5000)

import hashlib
import json
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

# ====================== ЛОГИРОВАНИЕ ======================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ====================== КЛАСС BLOCK ======================
class Block:
    def __init__(self, index: int, previous_hash: str, transactions: list, timestamp: datetime = None):
        self.index = index
        self.previous_hash = previous_hash
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.transactions = transactions
        self.nonce = 0
        self.hash = self.calculate_hash()

    def calculate_hash(self) -> str:
        tx_str = json.dumps(self.transactions, ensure_ascii=False, sort_keys=True)
        ts_str = self.timestamp.isoformat()
        block_string = f"{self.index}{self.previous_hash}{ts_str}{tx_str}{self.nonce}"
        return hashlib.sha256(block_string.encode()).hexdigest()

    def mine_block(self, difficulty: int):
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.calculate_hash()
        logger.info(f"Блок {self.index} замайнен: {self.hash}")

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp.isoformat(),
            "transactions": self.transactions,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @staticmethod
    def from_dict(data: dict):
        ts = datetime.fromisoformat(data["timestamp"])
        block = Block(data["index"], data["previous_hash"], data.get("transactions", []), ts)
        block.nonce = data.get("nonce", 0)
        block.hash = data.get("hash", block.calculate_hash())
        return block


# ====================== КЛАСС BLOCKCHAIN ======================
class Blockchain:
    def __init__(self, difficulty: int = 3, mining_reward: float = 50.0, block_capacity: int = 100):
        self.difficulty = difficulty
        self.mining_reward = mining_reward
        self.block_capacity = block_capacity
        self.chain = [self.create_genesis_block()]
        self.mempool = []  # Пул неподтверждённых транзакций
        self.nodes = set()  # Сетевые узлы

    def create_genesis_block(self) -> Block:
        fixed_ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        genesis_tx = {"from": "SYSTEM", "to": "genesis", "amount": 5000.0}
        return Block(0, "0", [genesis_tx], timestamp=fixed_ts)

    def register_node(self, address: str):
        if not address.strip():
            raise ValueError("Адрес узла не может быть пустым")
        self.nodes.add(address)

    def get_latest_block(self) -> Block:
        return self.chain[-1]

    def add_transaction(self, tx: dict):
        required = ("from", "to", "amount")
        for r in required:
            if r not in tx:
                raise ValueError(f"Отсутствует поле: {r}")
        sender, recipient, amount = tx["from"], tx["to"], float(tx["amount"])
        if not sender.strip() or not recipient.strip():
            raise ValueError("Адреса не могут быть пустыми")
        if amount <= 0:
            raise ValueError("Сумма должна быть положительной")

        if sender != "SYSTEM":
            available = self.get_balance(sender)
            pending_out = sum(t["amount"] for t in self.mempool if t["from"] == sender)
            if available - pending_out < amount - 1e-9:
                raise ValueError("Недостаточно средств")

        self.mempool.append({"from": sender, "to": recipient, "amount": amount})

    def mine_block(self, miner_address: str):
        if not miner_address.strip():
            raise ValueError("Адрес майнера не может быть пустым")

        txs = self.mempool[:self.block_capacity]
        reward_tx = {"from": "SYSTEM", "to": miner_address, "amount": self.mining_reward}
        txs.append(reward_tx)

        new_block = Block(len(self.chain), self.get_latest_block().hash, txs)
        new_block.mine_block(self.difficulty)
        self.chain.append(new_block)

        # Удаляем включённые транзакции (кроме награды)
        included = {json.dumps(tx, sort_keys=True, ensure_ascii=False) for tx in txs if tx["from"] != "SYSTEM"}
        self.mempool = [tx for tx in self.mempool if json.dumps(tx, sort_keys=True, ensure_ascii=False) not in included]

        return new_block

    def get_balance(self, address: str) -> float:
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.get("from") == address and tx.get("from") != "SYSTEM":
                    balance -= tx.get("amount", 0)
                if tx.get("to") == address:
                    balance += tx.get("amount", 0)
        return balance

    def is_chain_valid(self, chain=None) -> bool:
        chain = chain or self.chain
        balances = {}
        for i, block in enumerate(chain):
            if block.hash != block.calculate_hash():
                return False
            if i > 0:
                prev = chain[i-1]
                if block.previous_hash != prev.hash or block.index != i or block.timestamp <= prev.timestamp:
                    return False

            for tx in block.transactions:
                sender, recipient, amount = tx["from"], tx["to"], float(tx["amount"])
                if amount < 0:
                    return False
                if sender != "SYSTEM":
                    balances[sender] = balances.get(sender, 0.0)
                    if balances[sender] < amount - 1e-9:
                        return False
                    balances[sender] -= amount
                balances[recipient] = balances.get(recipient, 0.0) + amount
        return True

    def replace_chain(self, new_chain: list) -> bool:
        if len(new_chain) > len(self.chain) and self.is_chain_valid(new_chain):
            self.chain = new_chain
            return True
        return False

    def to_dict(self):
        return [b.to_dict() for b in self.chain]


# ====================== FLASK API ======================
app = Flask(__name__)
CORS(app)  # Для веб-интерфейса
blockchain = Blockchain()

@app.route("/chain", methods=["GET"])
def get_chain():
    return jsonify(blockchain.to_dict()), 200

@app.route("/nodes", methods=["GET"])
def get_nodes():
    return jsonify({"nodes": list(blockchain.nodes)}), 200

@app.route("/register_node", methods=["POST"])
def register_node():
    data = request.get_json()
    if not data or "node" not in data:
        return jsonify({"error": "Требуется 'node'"}), 400
    blockchain.register_node(data["node"])
    return jsonify({"message": "Узел добавлен", "nodes": list(blockchain.nodes)}), 201

@app.route("/transactions", methods=["GET"])
def get_mempool():
    return jsonify(blockchain.mempool), 200

@app.route("/transactions/new", methods=["POST"])
def new_transaction():
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON обязателен"}), 400
    try:
        tx = {"from": data["sender"], "to": data["recipient"], "amount": data["amount"]}
        blockchain.add_transaction(tx)
        return jsonify({"message": "Транзакция добавлена"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/mine", methods=["POST"])
def mine():
    data = request.get_json() or {}
    miner = data.get("miner")
    if not miner:
        return jsonify({"error": "Укажите 'miner'"}), 400
    try:
        block = blockchain.mine_block(miner)
        for node in blockchain.nodes:
            try:
                requests.post(f"{node}/receive_block", json=block.to_dict(), timeout=2)
            except:
                pass
        return jsonify(block.to_dict()), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/receive_block", methods=["POST"])
def receive_block():
    data = request.get_json()
    try:
        block = Block.from_dict(data)
        if block.previous_hash == blockchain.get_latest_block().hash and blockchain.is_chain_valid(blockchain.chain + [block]):
            blockchain.chain.append(block)
            included = {json.dumps(tx, sort_keys=True, ensure_ascii=False) for tx in block.transactions if tx["from"] != "SYSTEM"}
            blockchain.mempool = [tx for tx in blockchain.mempool if json.dumps(tx, sort_keys=True, ensure_ascii=False) not in included]
            return jsonify({"message": "Блок принят"}), 200
    except:
        pass
    return jsonify({"message": "Блок отклонён"}), 400

@app.route("/sync", methods=["GET"])
def sync():
    longest = blockchain.chain
    for node in blockchain.nodes:
        try:
            r = requests.get(f"{node}/chain", timeout=2)
            chain = [Block.from_dict(b) for b in r.json()]
            if len(chain) > len(longest) and blockchain.is_chain_valid(chain):
                longest = chain
        except:
            pass
    replaced = blockchain.replace_chain(longest)
    return jsonify({"replaced": replaced, "length": len(blockchain.chain)}), 200

@app.route("/balance/<address>", methods=["GET"])
def balance(address):
    return jsonify({"address": address, "balance": blockchain.get_balance(address)}), 200


# ====================== ЗАПУСК ======================
if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    logger.info(f"Запуск узла на порту {port}")
    app.run(host="0.0.0.0", port=port)