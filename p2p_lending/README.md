# Peer-to-Peer Lending Matchmaking System (Problem Statement 105)

An intelligent academic peer-to-peer lending matchmaking platform built with **Python, Flask, SQLite, NetworkX, Bootstrap 5, and Chart.js**. The platform matches lenders with borrower loan requests using transparent risk scoring, 4-factor compatibility scoring, and a weighted bipartite graph algorithm.

Academic simulation using simulated test data &mdash; no real money is involved.

---

## ⚡ Quick Start (Windows)

### Option A: 1-Click Batch Launcher (Easiest)
Simply double-click `run_app.bat` in the project root folder. It will automatically:
1. Locate your virtual environment (`.venv`).
2. Start the Flask application server at `http://127.0.0.1:5000`.

### Option B: Terminal Command in VS Code
Open your VS Code terminal (`Ctrl + \``) and run:
```powershell
cd "c:\Users\Anjali\OneDrive\Documents\project assignment\p2p_lending"
..\.venv\Scripts\python.exe app.py
```
Then open your browser and navigate to:
**[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🔑 Demo User Accounts (Password for all: `password123`)

| Role | Name | Email | Purpose / View |
|---|---|---|---|
| **Administrator** | Administrator | `admin@p2p.test` | System stats, 4 Chart.js charts, reports (CSV, XLSX, PDF) |
| **Lender** | Conservative Carla | `carla@p2p.test` | Capital portfolio, accepted loans, expected returns |
| **Lender** | Balanced Bala | `bala@p2p.test` | Medium risk appetite, multi-loan allocations |
| **Lender** | Aggressive Arjun | `arjun@p2p.test` | High yield portfolio, high risk funding |
| **Borrower** | Ravi Kumar | `ravi@p2p.test` | Education loan ($50,000), Low risk (9% rate) |
| **Borrower** | Sunil Verma | `sunil@p2p.test` | Home renovation ($80,000), Medium risk (14% rate) |
| **Borrower** | Meena Iyer | `meena@p2p.test` | Medical loan ($20,000), High risk (20% rate) |

*Tip: The Sign In page (`/login`) and Home page (`/`) have **1-click Quick Demo Login buttons** so you don't even have to type passwords during your college presentation!*

---

## 🏗️ 7-Week Project Architecture

| Module / Week | File(s) | Description |
|---|---|---|
| **Week 1: Setup & DB** | `config.py`, `database.py`, `schema.sql` | 9 SQLite relational tables with foreign keys and performance indexes |
| **Week 2: OOP Profiles** | `models.py`, `profile_service.py`, `audit.py` | User/Lender/Borrower classes, validation, status transitions, audit logs |
| **Week 3: Risk Scoring** | `scoring.py`, `queries.py` | 4-factor risk classification (Low, Med, High), 7 hard checks, plain explanations |
| **Week 4: Matchmaking** | `matching_engine.py` | NetworkX weighted bipartite graph, greedy allocation within lender funds |
| **Week 5: Loan Lifecycle** | `loan_service.py`, `routes/loans.py` | Reducing-balance EMI schedule, paid/late (2% fee)/defaulted simulation |
| **Week 6: Dashboards & API** | `reports.py`, `routes/dashboard.py`, `routes/api.py` | Admin/Lender/Borrower dashboards, Chart.js, REST API, CSV/Excel/PDF exports |
| **Week 7: Testing & Report** | `generate_data.py`, `evaluate.py`, `test_report.md` | Scale evaluation (up to 77,000 pairs), 10 required test scenarios, test suites |

---

## 🧪 Running Automated Tests

Run the full automated test suite (all 95+ unit and integration tests):
```powershell
cd "c:\Users\Anjali\OneDrive\Documents\project assignment\p2p_lending"
..\.venv\Scripts\python.exe -m pytest -v
```

Run weekly demo scripts in the console:
```powershell
python demo_week2.py   # OOP profiles and validation
python demo_week3.py   # Risk scoring & match explanations
python demo_week4.py   # Bipartite graph ranking & allocation
python demo_week5.py   # Loan creation & repayment tracking
python demo_week6.py   # REST API & report generation
```

Generate synthetic datasets and run evaluation:
```powershell
python generate_data.py --lenders 50 --borrowers 80 --out data/sample
python evaluate.py --report test_report.md
```

---

## ❓ Troubleshooting: "This site can’t be reached (127.0.0.1 refused to connect)"

If you see `ERR_CONNECTION_REFUSED` in your browser:
1. **Cause:** The Flask server process is not currently running. When you restart Windows or close the VS Code terminal window, the local web server shuts down.
2. **Fix:** Simply double-click `run_app.bat` or run `..\.venv\Scripts\python.exe app.py` in the terminal, then refresh your browser page at `http://127.0.0.1:5000`.
