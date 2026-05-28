# Security Checklist

## Odoo Access

- Use strong admin passwords and MFA where available.
- Assign users to the smallest possible laundry group.
- Link drivers to HR employees and use assigned-job rules.
- Configure user branch access before go-live.
- Review portal users so customers only access their own records.

## API

- Current mobile APIs require authenticated Odoo sessions.
- Add token auth, rate limits, device registration, and audit logging before public app release.
- Keep API routes company-aware and branch-aware.

## Deployment

- Use HTTPS only.
- Hide database manager endpoints.
- Put Odoo behind Nginx or Cloudflare.
- Enable WAF and request size limits.
- Keep PostgreSQL private.

## Secrets

- Do not commit SSH keys, API tokens, database passwords, or local machine paths.
- Use environment variables and secret managers.

## Backups

- Encrypt backups.
- Store offsite copies.
- Test restore procedures regularly.
