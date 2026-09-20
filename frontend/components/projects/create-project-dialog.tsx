"use client";

import { useState, useCallback, useRef, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UploadSection, type UploadSectionHandle, type UploadSectionSnapshot } from "@/components/ui/upload/upload-section";

interface CreateProjectDialogProps {
  trigger: ReactNode;
}

export function CreateProjectDialog({ trigger }: CreateProjectDialogProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const uploadSectionRef = useRef<UploadSectionHandle>(null);
  const [uploadSnapshot, setUploadSnapshot] = useState<UploadSectionSnapshot>({ hasFile: false, status: null });

  const resetState = useCallback(() => {
    setProjectName("");
    setUploadSnapshot({ hasFile: false, status: null });
  }, []);

  const handleUploadSuccess = useCallback(
    () => {
      router.refresh();
      setOpen(false);
      resetState();
    },
    [ resetState, router],
  );

  const buildFormData = useCallback(
    (file: File) => {
      const trimmedName = projectName.trim();
      if (!trimmedName) {
        throw new Error("Please enter a project name before uploading.");
      }
      const formData = new FormData();
      formData.append("projectName", trimmedName);
      formData.append("file", file, file.name);
      return formData;
    },
    [projectName],
  );

  const canUpload = projectName.trim().length > 0;
  const isCreateDisabled = !canUpload || !uploadSnapshot.hasFile || uploadSnapshot.status === "uploading";

  const handleCreateProject = useCallback(() => {
    uploadSectionRef.current?.triggerUpload();
  }, []);

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (!nextOpen) {
          resetState();
        }
      }}
    >
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Project</DialogTitle>
          <DialogDescription>Provide a project name and upload a RIS file to start processing.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              placeholder="e.g. 7th Meerkat Update"
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>RIS file</Label>
            <UploadSection
              ref={uploadSectionRef}
              onUploadSuccess={handleUploadSuccess}
              buildFormData={buildFormData}
              disabled={!canUpload}
              autoStart={false}
              onStateChange={setUploadSnapshot}
            />
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOpen(false);
            }}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleCreateProject} disabled={isCreateDisabled}>
            Create project
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
