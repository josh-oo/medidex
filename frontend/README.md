# Medidex

A Next.js application with user authentication and role-based access control.

## Prerequisites

- Node.js 20.x or higher
- PostgreSQL 14.x or higher
- npm (or pnpm/yarn/bun)

## Installation

1. Clone the repository and install dependencies:

```bash
npm install
```

2. Create a `.env` file in the root directory:

```bash
cp env.template .env
```

3. Edit `.env` and configure your database:

```env
DATABASE_URL="postgresql://username:password@localhost:5432/medidex?schema=public"
```

Replace `username`, `password`, and database name with your PostgreSQL credentials.

4. Generate Prisma
```bash
npx prisma generate
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Common Prisma Commands

```bash
# Generate Prisma Client
npx prisma generate

# Run migrations
npx prisma migrate deploy

# Create new migration (development)
npx prisma migrate dev --name migration_name

# Open database GUI
npx prisma studio

# Reset database (deletes all data)
npx prisma migrate reset
```

## Build for Production

```bash
npm run build
npm run start
```

## Environment Variables

### Required

- `DATABASE_URL` - PostgreSQL connection string

### Optional

- `BETTER_AUTH_SECRET` - Auth secret key (auto-generated in development)
- `BETTER_AUTH_URL` - Base URL (default: http://localhost:3000)

## Tech Stack

- Next.js 16
- TypeScript
- PostgreSQL
- Prisma ORM
- Better Auth
- Tailwind CSS
- Radix UI
