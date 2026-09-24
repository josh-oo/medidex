"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock } from "lucide-react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function PendingApprovalPage() {
  const router = useRouter();

  useEffect(() => {
    // Poll for approval; the route forces a token refresh so a newly granted
    // role takes effect immediately instead of waiting for the token to expire.
    const checkApproval = async () => {
      try {
        const response = await fetch("/api/auth/approval-status");
        if (!response.ok) return;
        const data = await response.json();

        if (data.approved) {
          router.push("/");
          router.refresh();
        }
      } catch (error) {
        // Ignore transient errors, try again on the next tick.
      }
    };

    // Check every 3 seconds
    const interval = setInterval(() => {
      void checkApproval();
    }, 3000);

    return () => clearInterval(interval);
  }, [router]);

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            <div className="flex justify-center mb-4">
              <Clock className="h-16 w-16 text-muted-foreground" />
            </div>
            <CardTitle className="text-2xl">Account Pending Approval</CardTitle>
            <CardDescription>
              Your account has been created successfully
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center space-y-4">
            <p className="text-sm text-muted-foreground">
              An administrator needs to approve your account before you can access the platform.
              Once approved, you'll be redirected to the login page automatically.
            </p>
            <p className="text-sm text-muted-foreground">
              If you have any questions, please contact your system administrator.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}