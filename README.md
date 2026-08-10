# 🏭 Classic Industries — Foundry Friends & Finishers Portal

Welcome to the centralized internal operations and inventory tracking dashboard for **Classic Industries (Foundry Friends & Finishers Division)**. This enterprise system automates data capture from delivery challans using generative AI models and feeds a real-time tracking interface hosted securely on Streamlit Cloud.

---

## 🚀 Live Production URL
🔗 **Dashboard Link:** [classicindustires-automation.streamlit.app](https://streamlit.app)

---

## 📂 Repository Architecture

The codebase utilizes a modular view strategy to isolate core dashboard utilities outside of native automatic folder routing locks, ensuring clean deployment builds:

```text
├── app.py                  # Primary Multi-Page Routing Engine
├── requirements.txt        # Server Package Dependencies
├── README.md               # Infrastructure documentation
├── assets/                 # Central Repository Media Folder
│   ├── main_hero.jpg       # Splash Banner
│   └── thumb_fitting.jpg   # Fitting Tab Visual
└── views/                  # UI Interface Submodules
    ├── 1_About_Us.py       # Corporate Splash Landing Hub
    ├── 2_Stock_Master.py   # Inventory KPI Summaries & Donut Charts
    ├── 3_Daily_Ledger.py   # Chronological Cloud Transaction Matrix
    └── 4_System_Guide.py   # On-Site Operator Standard Operating Procedures
```

---

## 🔄 End-to-End Operational Pipeline

```text
[Raw Document Scan]
       │
       ▼
 📁 Google Drive ──► 🤖 Gemini Flash AI ──► 📊 Google Sheets Log ──► [Is Validated ☑️]
                                                                          │
                                                                          ▼
 🌐 Live App ◄─── 📊 Stock Master Engine ◄─── 🔒 Supabase Cloud DB  ◄─────┘
```

1. **Intake & Extraction:** Physical delivery challans are scanned into a dedicated Google Drive folder (`Inward_Challans`). Google Apps Script calls the Gemini Flash AI model to extract structural invoice metrics.
2. **Spreadsheet Quality Check:** Supervisors review the structured data rows inside the Google Sheet (`Daily_Log`) to correct formatting bugs or typos.
3. **Database Sync Trigger:** Checking the `Is Validated` row box runs an HTTP POST transaction, inserting the record straight into the cloud-hosted Supabase table (`staging_ledger`).
4. **Live Dashboard Stream:** The live web application executes direct API queries against Supabase to re-calculate inventory summaries, compute lot deadlines, and update visualization graphs immediately.

---

## 🛠️ Essential Tech Stack

* **Front-End Matrix:** Streamlit Cloud Containerization Engine.
* **Database Ledger:** Supabase Cloud Infrastructure (REST API / `supabase-py` SDK).
* **Analytics Rendering:** Altair Data Visualization Architecture.
* **Intake Integration:** Google Apps Script Execution Engine & Gemini AI Hub.

---

## ⚙️ Maintenance & Updates Guide

### 1. Pushing Dashboard Modifications
This system uses a continuous integration loop linked straight to the primary branch. To make live text changes or alter visuals:
* Use your terminal or browser layout to modify the specific Python target script inside the `views/` folder.
* **Commit changes** straight onto your default **`main`** branch on GitHub.
* Streamlit Cloud monitors this branch and pushes your code revisions live to the public URL within 5 seconds.

### 2. Upgrading Server Package Dependencies
If you need to introduce new statistical libraries, add the package name directly to your root **`requirements.txt`** file:
```text
streamlit
supabase
pandas
numpy
altair
```

### 3. Re-Authenticating Secure Project Secrets
Credentials or project tokens are hidden securely outside of the source files. If keys update, do **not** write them into code. Instead, log into your Streamlit Workspace console, navigate to **Advanced Settings -> Secrets**, and update the TOML array parameters:
```toml
SUPABASE_URL = "https://supabase.co"
SUPABASE_KEY = "your-publishable-anon-key-string"
TABLE_NAME = "staging_ledger"
```

---
🔒 *Internal Proprietary System — Authorized Personnel Only.*
