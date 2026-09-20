import { auth } from "../lib/auth";
import prisma from "../lib/db";

const email = process.env.ADMIN_EMAIL?.trim();
const password = process.env.ADMIN_PASSWORD;
const name = process.env.ADMIN_NAME?.trim() || "Administrator";

async function seedAdmin() {
  if (!email && !password) {
    console.log("ADMIN_EMAIL and ADMIN_PASSWORD are not set; skipping admin seed.");
    return;
  }

  if (!email || !password) {
    throw new Error("ADMIN_EMAIL and ADMIN_PASSWORD must both be set to seed the admin account.");
  }

  let user = await prisma.user.findUnique({ where: { email } });

  if (!user) {
    const result = await auth.api.signUpEmail({
      body: { email, password, name },
    });

    if ("error" in result || !result.user) {
      throw new Error("Better Auth did not create the admin account.");
    }

    user = await prisma.user.findUniqueOrThrow({ where: { id: result.user.id } });
  }

  await prisma.user.update({
    where: { id: user.id },
    data: {
      roles: ["ADMIN"],
      isApproved: true,
      emailVerified: true,
    },
  });

  console.log(`Admin account is ready for ${email}.`);
}

seedAdmin()
  .catch((error) => {
    console.error("Failed to seed admin account:", error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
