import { NextResponse } from "next/server";
import { getUsers } from "@/app/(root)/user-management/server";

export async function GET() {
  try {
    const users = await getUsers();
    return NextResponse.json({ users });
  } catch (error) {
    console.error("Failed to fetch users", error);
    return NextResponse.json({ error: "Unable to fetch users" }, { status: 500 });
  }
}
