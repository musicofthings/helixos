# Public landing site

The visitor landing page lives in [`apps/site`](../apps/site) and deploys as a static build.

Primary target: **Cloudflare Pages**.

It is a static site (HTML/CSS/JS), separate from the product UI in `apps/web`.

## Edit locally

```bash
cd apps/site
npm run build
npm run preview   # http://127.0.0.1:4173
```

Source files:

| File | Purpose |
| --- | --- |
| `index.html` | Landing markup |
| `styles.css` | Visual system |
| `main.js` | Scroll reveal + light motion + 3D fallback handling |
| `scripts/build.mjs` | Copies into `dist/` |
| `assets/3d/` | 3D model + fallback poster |
| `_headers` / `_redirects` | Cloudflare caching + routing rules |
| `wrangler.toml` | Cloudflare Pages build metadata |

Use relative asset URLs (`./styles.css`) so the site works under any domain/path.

## Publish on Cloudflare Pages

1. Cloudflare Dashboard → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**.
2. Select this repository and configure:
   - **Framework preset:** None
   - **Root directory:** `apps/site`
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Node version:** `22`
3. Set production branch to `main`.
4. Add custom domain and enable HTTPS.

Cloudflare automatically creates preview deployments for pull requests.

### GitHub Actions deploy (recommended in this repo)

This repository includes [`.github/workflows/cloudflare-pages.yml`](../.github/workflows/cloudflare-pages.yml), which builds `apps/site` and deploys with Wrangler:

- `push` to `main` → production deploy
- `pull_request` → preview deploy (same-repo PRs)

Set these GitHub repository secrets:

- `CLOUDFLARE_API_TOKEN` (Pages edit permissions)
- `CLOUDFLARE_ACCOUNT_ID`

Optional repository variable:

- `CLOUDFLARE_PAGES_PROJECT` (defaults to `helixos-site`)

### One-time Cloudflare API token setup

1. Cloudflare Dashboard → **My Profile** → **API Tokens** → **Create Token**.
2. Start from **Edit Cloudflare Workers** template.
3. Scope to the target account hosting Pages.
4. Save token into GitHub secret `CLOUDFLARE_API_TOKEN`.

### DNS cutover checklist

1. Add custom domain in the Pages project.
2. Update registrar DNS to Cloudflare nameservers (if not already).
3. Ensure apex and `www` records point to Cloudflare Pages target.
4. Enable:
   - **Always Use HTTPS**
   - **HTTP/3**
   - **Brotli**
5. Validate:
   - `https://<domain>` loads
   - 3D hero and fallback assets load from `/assets/3d/`
   - no mixed-content warnings
   - mobile LCP remains within target budget.

## Legacy GitHub Pages workflow

[`.github/workflows/pages.yml`](../.github/workflows/pages.yml) remains as a manual fallback deployment path.

## Downloads

The Download CTA points at:

https://github.com/musicofthings/helixos/releases/latest

macOS DMGs are produced by [`.github/workflows/release-desktop.yml`](../.github/workflows/release-desktop.yml) when you push a tag like `v0.1.0` (or run the workflow manually). The asset is published as `HelixOS-mac-x64.dmg`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

Builds are not Apple-notarized yet; Gatekeeper may require a Privacy & Security allow on first open.

The public site now lives on Cloudflare Pages at [https://helixos.pages.dev/](https://helixos.pages.dev/).
