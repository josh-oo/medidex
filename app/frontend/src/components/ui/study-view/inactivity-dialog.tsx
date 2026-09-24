"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Clock } from "lucide-react";

interface InactivityDialogProps {
  isTimerActive: boolean;
  inactivityTimeout?: number;
  dialogTimeout?: number;
  onContinue: () => void;
  onStop: () => void;
}

const INACTIVITY_TIMEOUT_DEFAULT = 60000; // 1 minute
const DIALOG_TIMEOUT_DEFAULT = 120000; // 2 minutes

export function InactivityDialog({
  isTimerActive,
  inactivityTimeout = INACTIVITY_TIMEOUT_DEFAULT,
  dialogTimeout = DIALOG_TIMEOUT_DEFAULT,
  onContinue,
  onStop,
}: InactivityDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const inactivityTimerRef = useRef<NodeJS.Timeout | null>(null);
  const dialogTimerRef = useRef<NodeJS.Timeout | null>(null);
  const lastActivityRef = useRef<number>(Date.now());
  const isContinuingRef = useRef(false);

  const clearDialogTimer = useCallback(() => {
    if (dialogTimerRef.current) {
      clearTimeout(dialogTimerRef.current);
      dialogTimerRef.current = null;
    }
  }, []);

  const resetInactivityTimer = useCallback(() => {
    lastActivityRef.current = Date.now();

    if (inactivityTimerRef.current) {
      clearTimeout(inactivityTimerRef.current);
    }

    if (isTimerActive && !isOpen) {
      inactivityTimerRef.current = setTimeout(() => {
        setIsOpen(true);
      }, inactivityTimeout);
    }
  }, [isTimerActive, isOpen, inactivityTimeout]);

  // Start dialog timeout when dialog opens
  useEffect(() => {
    if (isOpen) {
      clearDialogTimer();
      dialogTimerRef.current = setTimeout(() => {
        setIsOpen(false);
        onStop();
      }, dialogTimeout);
    } else {
      clearDialogTimer();
    }

    return () => {
      clearDialogTimer();
    };
  }, [isOpen, dialogTimeout, onStop, clearDialogTimer]);

  useEffect(() => {
    if (!isTimerActive) {
      if (inactivityTimerRef.current) {
        clearTimeout(inactivityTimerRef.current);
        inactivityTimerRef.current = null;
      }
      clearDialogTimer();
      setIsOpen(false);
      return;
    }

    const handleActivity = () => {
      if (!isOpen) {
        resetInactivityTimer();
      }
    };

    const events = ["click", "scroll", "keydown", "mousemove", "touchstart"];
    events.forEach((event) => {
      window.addEventListener(event, handleActivity, { passive: true });
    });

    resetInactivityTimer();

    return () => {
      events.forEach((event) => {
        window.removeEventListener(event, handleActivity);
      });
      if (inactivityTimerRef.current) {
        clearTimeout(inactivityTimerRef.current);
      }
    };
  }, [isTimerActive, isOpen, resetInactivityTimer, clearDialogTimer]);

  const handleContinue = () => {
    isContinuingRef.current = true;
    clearDialogTimer();
    setIsOpen(false);
    onContinue();

    setTimeout(() => {
      isContinuingRef.current = false;
      resetInactivityTimer();
    }, 0);
  };

  const handleStop = () => {
    clearDialogTimer();
    setIsOpen(false);
    onStop();
  };

  const handleOpenChange = (open: boolean) => {
    if (!open && !isContinuingRef.current) {
      handleStop();
    }
  };

  return (
    <AlertDialog open={isOpen} onOpenChange={handleOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <AlertDialogTitle>Are you still working?</AlertDialogTitle>
          </div>
          <AlertDialogDescription>
            You&apos;ve been inactive for a while. Please confirm that
            you&apos;re still working on this report to continue time tracking.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleStop}>
            Stop tracking
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleContinue}>
            Yes, I&apos;m still working
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
