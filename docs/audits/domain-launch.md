# Page 47 subdomain launch

Date: 8 September 2026.

The selected public hostname is now DNS- and TLS-ready:

- `page47.xcover.online` resolves to `13.62.181.128`;
- the dedicated Nginx virtual host passes `nginx -t`;
- HTTP requests redirect with `301` to `https://page47.xcover.online/...`;
- the certificate subject is `CN = page47.xcover.online` and expires on
  7 December 2026;
- `https://page47.xcover.online/healthz` returns
  `{"status":"ok","service":"Page 47"}`;
- the public root returns HTTP 200; and
- the Seattle ledger endpoint is readable through the subdomain.

`sudo certbot renew --dry-run --no-random-sleep-on-renew` completed with exit
code 0 for both the new certificate and the existing `xcover.online`
certificate. The final virtual host retains
`/.well-known/acme-challenge/` from `/var/www/certbot` so future renewal does
not depend on a one-time certificate issuance.

The existing `https://xcover.online/page47/healthz` route also returned the
Page 47 health response during this check. The VPS application configuration
still uses `public_path: /page47`; the root-path configuration and
`/page47/web/public-url` SSM value remain a separate controlled rollout step.
No legacy route was removed or redirected.
