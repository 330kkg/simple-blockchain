# Простой блокчейн на Python

## Запуск

```bash
pip install -r requirements.txt
python main.py 5000

## API
GET /chain — цепочка
POST /transactions/new → { "sender": "A", "recipient":"B", "amount": 10 }
POST /mine → { "miner": "miner1" }
GET /balance/<address>
POST /register_node → { "node": "http://localhost:5001" }

## Несколько узлов
python main.py 5000
python main.py 5001
python main.py 5002

## Веб-интерфейс
Подключи фронтенд на http://localhost:5173 — CORS включён.

