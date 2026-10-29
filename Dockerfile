# Match the measured Node.js version from laboratory 2.
FROM node:22.18.0-bookworm-slim AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

FROM node:22.18.0-bookworm-slim AS runtime
ENV NODE_ENV=production PORT=4567
WORKDIR /app
COPY --from=dependencies --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node package.json ./
COPY --chown=node:node src ./src
COPY --chown=node:node db ./db
COPY --chown=node:node scripts/init-db.js scripts/seed-container.cjs scripts/check-container-data.cjs ./scripts/
USER node
EXPOSE 4567
CMD ["node", "src/server.js"]
