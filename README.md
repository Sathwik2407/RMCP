# RMCP Order System — Backend

**Raj Multi Color Print · Kakinada · ESTD 1983**

A full-stack order management system for wedding card printing.

---

## Stack

| Layer     | Technology         |
|-----------|--------------------|
| Backend   | Python 3 + Flask   |
| Database  | PostgreSQL         |
| Frontend  | Vanilla HTML/JS    |

Database hosted on Railway with automatic schema initialization on app startup.

---

## Setup & Run

### Requirements
- Python 3.8+
- Flask (`pip install flask`)

### Start the server

```bash
cd rmcp-backend
python3 server.py
```

Or use the start script:
```bash
bash start.sh
```

The app runs at: **http://localhost:5050**

---

## API Endpoints

### Orders
| Method | URL                        | Description             |
|--------|----------------------------|-------------------------|
| GET    | /api/orders                | List all orders         |
| POST   | /api/orders                | Create new order        |
| GET    | /api/orders/:id            | Get single order        |
| PUT    | /api/orders/:id            | Update full order       |
| PATCH  | /api/orders/:id/status     | Update status only      |
| DELETE | /api/orders/:id            | Delete order            |

### Stock
| Method | URL               | Description              |
|--------|-------------------|--------------------------|
| GET    | /api/stock        | List all stock entries   |
| POST   | /api/stock        | Add / top-up stock       |
| DELETE | /api/stock/:num   | Remove stock entry       |

### Stats
| Method | URL         | Description          |
|--------|-------------|----------------------|
| GET    | /api/stats  | Dashboard summary    |

---

## Data Storage

- Database: PostgreSQL (Railway-managed)
- Connection via `DATABASE_URL` environment variable
- Demo seed data loads automatically if the database is empty
- All data persists across deployments with automatic backups

---

## Frontend Features

- ✅ All Orders register with search and filters
- ✅ Designer Queue (cards needing design/proof)
- ✅ Print Queue with Lane A (Urgent) / Lane B (Normal)
- ✅ Stock Inventory with low-stock alerts
- ✅ Bill Estimation → Convert to Work Order
- ✅ Sales Report with revenue summary
- ✅ WhatsApp Message Templates (Telugu)
- ✅ Live backend connection indicator
- ✅ Order detail modal with status update
- ✅ Edit & Delete orders

---

## Order Status Flow

```
New → Design → Proof Sent → Confirmed → Printing → Ready → Delivered
```
