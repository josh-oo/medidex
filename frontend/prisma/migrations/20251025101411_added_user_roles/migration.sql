-- CreateEnum
CREATE TYPE "Role" AS ENUM ('ADMIN', 'USER');

-- AlterTable
ALTER TABLE "user" ADD COLUMN     "roles" "Role"[] DEFAULT ARRAY['USER']::"Role"[];
