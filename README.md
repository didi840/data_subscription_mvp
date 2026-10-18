# Data Subscription App MVP

A Flask + MongoDB MVP for a Nigerian data subscription business.

## Included
- User registration/login
- User dashboard
- Wallet
- Demo wallet funding
- MTN, Airtel, Glo and 9mobile plans
- Demo data purchase
- Transaction history
- Admin dashboard
- Add/disable data plans
- Health-check endpoint

## Important
The payment and data purchase flows are DEMO flows. No real money or real mobile data is delivered.

For production, replace the demo wallet funding with a real payment gateway and replace the demo purchase section in `buy_data()` with a verified VTU/data API integration. Add webhook verification, idempotency, audit logs, rate limits, proper secrets, HTTPS and production error handling before taking real payments.

## Setup
1. Install Python.
2. Create a virtual environment.
3. Run `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set your MongoDB URI.
5. Run `python app.py`
6. Open http://127.0.0.1:5000

Demo admin:
Email: admin@example.com
Password: Admin123!

Change this password before using the project for anything real.
