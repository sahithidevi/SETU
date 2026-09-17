# SETU (సేతు) — Smart Referral & Care Continuity Platform

**SIH 26133 Prototype** | Rural Telangana Healthcare Referral Network

---

## 🚀 How to Run in VS Code

### Method 1: One-Click Run (F5)
1. Open the project folder in VS Code:
   - Go to **File** ➔ **Open Folder...** ➔ Select `/Users/sahithi/Desktop/Setu`
2. Press **`F5`** (or go to the **Run and Debug** tab on the left sidebar and click **Start Debugging** ▶).
3. The integrated terminal will start the server on port `5001`.
4. Open your browser to: **[http://localhost:5001/](http://localhost:5001/)**

---

### Method 2: Using the VS Code Integrated Terminal
1. In VS Code, open the built-in terminal:
   - Press **`Ctrl + ` `** (backtick) or go to **Terminal ➔ New Terminal**.
2. Run the command:
   ```bash
   PORT=5001 python3 server/app.py
   ```
3. You will see:
   ```
   Setu platform running on http://localhost:5001
   ```
4. Click or navigate to: **[http://localhost:5001/](http://localhost:5001/)**

---

## 🎯 Demo Highlights
- **90-Second Showcase**: Click the green **`▶ Run 90s Live Demo`** button at the top right.
- **Telangana Geography**: Real coordinates for Nakrekal, Suryapet, Nalgonda, Khammam, and NIMS Hyderabad.
- **Unified Portal**: All 7 dashboards (Health Worker, Admin, Doctor, ASHA, Passport, Analytics) operate seamlessly in one single website with live Server-Sent Events (SSE).
