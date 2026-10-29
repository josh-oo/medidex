import { useState, useCallback, useRef, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProjectUploadOptionsSlot } from "@/context/study-report-slots-context";
import { UploadSection, type UploadSectionHandle, type UploadSectionSnapshot } from "@/components/ui/upload/upload-section";
import type { StudyDatabase } from "@/lib/databases";

interface CreateProjectDialogProps {
  /** Opens the dialog; leave it out to open the dialog from elsewhere (`open`, `onOpenChange`). */
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onProjectCreated?: () => void;
  /** The study database the reports are matched against and added to. */
  database: StudyDatabase;
}

export function CreateProjectDialog({ trigger, open: openProp, onOpenChange, onProjectCreated, database }: CreateProjectDialogProps) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = useCallback(
    (nextOpen: boolean) => {
      setOpenState(nextOpen);
      onOpenChange?.(nextOpen);
    },
    [onOpenChange],
  );
  const [projectName, setProjectName] = useState("");
  const [options, setOptions] = useState<Record<string, unknown>>({});
  const uploadSectionRef = useRef<UploadSectionHandle>(null);
  const [uploadSnapshot, setUploadSnapshot] = useState<UploadSectionSnapshot>({ hasFile: false, status: null });

  const resetState = useCallback(() => {
    setProjectName("");
    setOptions({});
    setUploadSnapshot({ hasFile: false, status: null });
  }, []);

  const handleUploadSuccess = useCallback(
    () => {
      setOpen(false);
      resetState();
      onProjectCreated?.();
    },
    [resetState, onProjectCreated, setOpen],
  );

  const buildFormData = useCallback(
    (file: File) => {
      const trimmedName = projectName.trim();
      if (!trimmedName) {
        throw new Error("Please enter a project name before uploading.");
      }
      const formData = new FormData();
      formData.append("projectName", trimmedName);
      formData.append("databaseId", String(database.id));
      formData.append("file", file, file.name);
      formData.append("options", JSON.stringify(options));
      return formData;
    },
    [projectName, options, database.id],
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
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Project</DialogTitle>
          <DialogDescription>
            Provide a project name and upload a RIS file to start processing. Its reports are matched against the
            studies of <span className="font-medium text-foreground">{database.name}</span>.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="project-name">Project name</Label>
            <Input
              id="project-name"
              placeholder="e.g. 7th Update"
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
          <ProjectUploadOptionsSlot options={options} onChange={setOptions} />
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
