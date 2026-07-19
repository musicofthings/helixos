# Public landing site

The visitor landing page lives in [`apps/site`](../apps/site) and deploys to GitHub Pages:

**https://musicofthings.github.io/helixos/**

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
| `main.js` | Scroll reveal + light motion |
| `scripts/build.mjs` | Copies into `dist/` |

Use relative asset URLs (`./styles.css`) so the site works under the `/helixos/` project Pages path.

## Publish

Pushing changes under `apps/site/**` to `main` runs [`.github/workflows/pages.yml`](../.github/workflows/pages.yml).

**One-time GitHub setting:** Repository → Settings → Pages → Source = **GitHub Actions**.

## Downloads

The Download CTA points at:

https://github.com/musicofthings/helixos/releases/latest

macOS DMGs are produced by [`.github/workflows/release-desktop.yml`](../.github/workflows/release-desktop.yml) when you push a tag like `v0.1.0` (or run the workflow manually). The asset is published as `HelixOS-mac-x64.dmg`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

Builds are not Apple-notarized yet; Gatekeeper may require a Privacy & Security allow on first open.
