import { useState, useCallback, useRef, type ReactNode } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
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
  /** The number of the update, its name ("Update 7"). */
  number: number;
}

export function CreateProjectDialog({ trigger, open: openProp, onOpenChange, onProjectCreated, database, number }: CreateProjectDialogProps) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = useCallback(
    (nextOpen: boolean) => {
      setOpenState(nextOpen);
      onOpenChange?.(nextOpen);
    },
    [onOpenChange],
  );
  const [options, setOptions] = useState<Record<string, unknown>>({});
  const uploadSectionRef = useRef<UploadSectionHandle>(null);
  const [uploadSnapshot, setUploadSnapshot] = useState<UploadSectionSnapshot>({ hasFile: false, status: null });

  const resetState = useCallback(() => {
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
      const formData = new FormData();
      formData.append("projectName", `Update ${number}`);
      formData.append("databaseId", String(database.id));
      formData.append("file", file, file.name);
      formData.append("options", JSON.stringify(options));
      return formData;
    },
    [number, options, database.id],
  );

  const isCreateDisabled = !uploadSnapshot.hasFile || uploadSnapshot.status === "uploading";

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
          <DialogTitle>New update #{number}</DialogTitle>
          <DialogDescription>
            Upload a RIS file with the new reports. They are matched against the studies of{" "}
            <span className="font-medium text-foreground">{database.name}</span>.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>RIS file</Label>
            <UploadSection
              ref={uploadSectionRef}
              onUploadSuccess={handleUploadSuccess}
              buildFormData={buildFormData}
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
            Create update
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
