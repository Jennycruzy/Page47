# Page 47 subdomain launch

Date: 9 September 2026.

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

The VPS application now uses `public_path: /`. The subdomain page emits
root-relative links and its APIs are readable at the root path. The existing
`https://xcover.online/page47/healthz` bookmark now returns a `301` to
`https://page47.xcover.online/healthz`, preserving the old entry point while
avoiding links back to the xCover application root. The
`/page47/web/public-url` SSM value is now present in `eu-west-2`. The verified
SES sender is configured and the controlled notification was accepted through
the application path; mailbox receipt remains a separate check.
