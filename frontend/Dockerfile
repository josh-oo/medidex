# 1. Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app

# Install git
RUN apk add --no-cache git

# Clone the repository
RUN git clone https://github.com/MaxiMittel/medidex.git .

# Update API_BASE_URL in apiClient.ts
#TODO remove this once API_BASE_URL is an env var
RUN sed -i "s|const API_BASE_URL = `${process.env.MEERKAT_API_URL}/api`|const API_BASE_URL = process.env.BACKEND_API_URL \|\| 'http://logic:8002'|g" lib/api/apiClient.ts

# Provide dummy DATABASE_URL for prisma generate during npm ci
ENV DATABASE_URL="postgresql://dummy:dummy@localhost:5432/dummy"

RUN npm ci

# 2. Build the application
FROM node:20-alpine AS builder
WORKDIR /app

# Copy everything from deps stage (includes cloned repo + node_modules)
COPY --from=deps /app ./

# Generate Prisma Client (required before build)
ENV DATABASE_URL="postgresql://dummy:dummy@localhost:5432/dummy"
RUN npx prisma generate
RUN npm run build

# 3. Production runner
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Create non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy built assets
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/app/generated ./app/generated
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./
COPY --from=builder /app/prisma ./prisma

USER nextjs

CMD ["npm", "run", "start"]