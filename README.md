# Ticketimaster — ticket booking platform starter

**Branding note:** Ticketimaster is an independent prototype and is not affiliated with, endorsed by, or a substitute for Ticketmaster. Use original logos and visual assets, and check trademark and domain availability before public launch.

A responsive Flask + SQLite starter for a USA-focused event discovery and ticketing platform. It includes event search/filtering, event detail pages, quantity selection, a demo-only checkout, an admin dashboard, event management, order list, Stripe Checkout scaffolding, a Stripe webhook endpoint, and a protected ticket-validation endpoint.

## Important status

This is a deployable starter, **not yet a production-ready ticket marketplace**. It does not contain real Ticketmaster inventory or an enabled PayPal payment flow. Sample listings are clearly marked as demo listings. The demo checkout takes no payment and does not issue a valid ticket. Do not advertise the demo inventory as real.

Before accepting real payments, finish and test: PayPal server-side create/capture plus webhook signature verification; production ticket code generation and one-time secure delivery; email delivery; inventory reservations/expiry and concurrency safety; refunds/cancellations; rate limiting and CSRF protection; database migrations/backups; audit logs; taxes/fees and event seller contracts; accessibility and legal review.

## Local run

Python 3.11+ recommended.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open http://127.0.0.1:5000. The initial local admin defaults to `admin` / `change-this-before-deploy` unless environment variables are set. Change these immediately and never expose the default account to the public internet.

## Docker

```bash
cp .env.example .env
# Edit .env and replace every placeholder, especially secrets and admin credentials.
docker compose up --build -d
```

Open http://localhost:5000. Persistent SQLite data is stored in the Docker volume. For a serious production launch, use managed PostgreSQL instead of SQLite and configure backups.

## Stripe setup (test mode first)

1. Create a Stripe account and a test-mode API key.
2. Set `STRIPE_SECRET_KEY` to the test secret key.
3. Configure a webhook endpoint at `https://YOUR_DOMAIN/webhooks/stripe` for `checkout.session.completed` and set `STRIPE_WEBHOOK_SECRET`.
4. Test successful, failed, abandoned and duplicate webhook delivery before switching to live keys.
5. The payment success redirect is not treated as proof of payment; the signed webhook is the source of truth.

This starter's Stripe route is scaffolding. Before launch, add idempotent inventory reservations/rollback on failed or expired sessions and securely deliver the resulting tickets after webhook confirmation.

## PayPal

Create a PayPal Developer account and sandbox REST app to obtain Client ID and Secret. The checkout UI shows a PayPal option, but the server deliberately refuses it until a real create-order/capture flow and verified webhook handler are implemented. Never trust a browser-only approval signal.

## Event data

Sample events are seeded on first database creation. To display authorized real events, obtain a Ticketmaster Developer API key and use the Discovery API only within its terms and branding requirements. Discovery is for event discovery; purchase/hold/primary inventory endpoints require separate partner authorization. Do not scrape protected pages or imply that a discovery listing means tickets are purchasable through Ticketimaster.

## Security checklist before launch

- Replace `FLASK_SECRET_KEY` with a long random secret; use a secret manager.
- Set unique strong `ADMIN_USERNAME` and `ADMIN_PASSWORD`; restrict admin routes behind MFA/IP controls if possible.
- Set `COOKIE_SECURE=1` behind HTTPS.
- Set `ALLOW_DEMO_CHECKOUT=0`.
- Add CSRF protection to all state-changing forms, rate limiting, login lockout, and security monitoring.
- Use managed PostgreSQL, migrations, backups, and a tested restore procedure.
- Finish payment idempotency, stock holds, refunds, ticket delivery, and QR ticket issuance/validation.
- Verify every payment webhook signature and prevent duplicate event processing.
- Review tax, privacy, consumer protection, ADA accessibility, chargeback and ticket-resale requirements for your operating states.

## Suggested deployment

Render, Railway, Fly.io, or a comparable container host can run the Docker image. Add a custom domain and HTTPS, managed PostgreSQL, environment secrets, a persistent logging/monitoring service, and automated backups. Configure `DATABASE_PATH` appropriately if staying on SQLite; PostgreSQL is recommended for concurrent inventory and orders.
