# Security and launch notes

- Never commit `.env` or live payment secrets.
- Payment is considered paid only when a verified provider webhook confirms capture.
- The demo checkout is explicitly non-paying and does not issue tickets.
- Ticket validation requires admin session authentication and prevents a stored ticket from being used twice.
- The initial sample database creates a default local admin. Replace credentials before public deployment.
- For production, implement CSRF protection, rate limits, email verification, login throttling, MFA, audit logs, durable ticket delivery, refund/cancel workflows, inventory holds, and transactional/idempotent payment handling.
