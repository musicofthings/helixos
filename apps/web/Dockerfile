# Build from the repository root:
#   docker build -f apps/web/Dockerfile -t helixos-web \
#     --build-arg HELIX_API_PROXY_TARGET=https://api.example.com \
#     --build-arg NEXT_PUBLIC_OIDC_AUTHORITY=https://idp.example.com/ \
#     --build-arg NEXT_PUBLIC_OIDC_CLIENT_ID=... .
#
# NEXT_PUBLIC_* values and the proxy target are compiled in at build time, so
# build one image per environment. Everything below is public by design: never
# pass a secret as a build argument.

FROM node:22-alpine AS build
WORKDIR /repo
COPY packages ./packages
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
RUN cd apps/web && npm ci
COPY apps/web ./apps/web

ARG HELIX_API_PROXY_TARGET=http://127.0.0.1:8000
ARG NEXT_PUBLIC_OIDC_AUTHORITY=
ARG NEXT_PUBLIC_OIDC_CLIENT_ID=
ARG NEXT_PUBLIC_OIDC_AUDIENCE=
ARG NEXT_PUBLIC_OIDC_SCOPE=
ARG NEXT_PUBLIC_OIDC_TOKEN_TYPE=
ARG NEXT_PUBLIC_API_TOKEN=
ENV HELIX_STANDALONE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    HELIX_API_PROXY_TARGET=$HELIX_API_PROXY_TARGET \
    NEXT_PUBLIC_API_URL= \
    NEXT_PUBLIC_OIDC_AUTHORITY=$NEXT_PUBLIC_OIDC_AUTHORITY \
    NEXT_PUBLIC_OIDC_CLIENT_ID=$NEXT_PUBLIC_OIDC_CLIENT_ID \
    NEXT_PUBLIC_OIDC_AUDIENCE=$NEXT_PUBLIC_OIDC_AUDIENCE \
    NEXT_PUBLIC_OIDC_SCOPE=$NEXT_PUBLIC_OIDC_SCOPE \
    NEXT_PUBLIC_OIDC_TOKEN_TYPE=$NEXT_PUBLIC_OIDC_TOKEN_TYPE \
    NEXT_PUBLIC_API_TOKEN=$NEXT_PUBLIC_API_TOKEN
RUN cd apps/web && npm run build

FROM node:22-alpine
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:'+process.env.PORT+'/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "apps/web/server.js"]
