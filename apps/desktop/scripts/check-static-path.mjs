/**
 * Smoke checks for packaged UI static-path containment.
 * Run: node apps/desktop/scripts/check-static-path.mjs
 */
import assert from "node:assert/strict";
import path from "node:path";

function resolveSafeStaticPath(root, pathname) {
  const base = path.resolve(root);
  let relative = pathname;
  if (relative.endsWith("/")) {
    relative = `${relative}index.html`;
  }
  if (relative === "" || relative === "/") {
    relative = "/index.html";
  }
  relative = relative.replace(/^\/+/, "");
  const resolved = path.resolve(base, relative);
  const out = path.relative(base, resolved);
  if (out.startsWith("..") || path.isAbsolute(out)) {
    return null;
  }
  return resolved;
}

const root = "/Users/x/HelixOS.app/Contents/Resources/web";

assert.equal(
  resolveSafeStaticPath(root, "/index.html"),
  path.join(root, "index.html")
);
assert.equal(
  resolveSafeStaticPath(root, "/_next/static/chunk.js"),
  path.join(root, "_next/static/chunk.js")
);
assert.equal(resolveSafeStaticPath(root, "/../pyvenv/pyvenv.cfg"), null);
assert.equal(
  resolveSafeStaticPath(root, decodeURIComponent("/..%2fpyvenv%2fpyvenv.cfg")),
  null
);
assert.equal(resolveSafeStaticPath(root, "/../webkit/secret"), null);

console.log("resolveSafeStaticPath checks passed");
