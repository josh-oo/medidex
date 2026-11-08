import { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from "react";
import { Upload, FileText, X, CheckCircle2, AlertCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import axios from "axios";
import apiClient from "@/lib/api/apiClient";

// Relative to apiClient's baseURL.
const DEFAULT_UPLOAD_URL = "/projects";

// Turns an upload failure into something a user can act on. The backend answers
// with FastAPI's {detail: ...} body: a string for the explicit HTTPExceptions
// (400 unsupported extension, 401 not an admin, 409 project already exists,
// 500 unparseable file), or a list of {loc, msg} for 422 validation errors.
function getUploadErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Could not reach the server. Check your connection and try again.";
    }
    const { status, data } = error.response;
    const detail = data?.detail;
    if (typeof detail === "string" && detail) {
      if (status === 401) return "You are not allowed to upload. Your session may have expired - sign in again.";
      if (status === 409) return "This file has already been uploaded as a project.";
      return detail;
    }
    if (Array.isArray(detail) && detail.length) {
      return detail
        .map((issue) => (typeof issue?.msg === "string" ? issue.msg : null))
        .filter(Boolean)
        .join("; ");
    }
    if (status === 413) return "The file is too large to upload.";
    if (status >= 500) return "The server failed to process the file. Please try again later.";
    return `Upload failed (HTTP ${status}).`;
  }
  return error instanceof Error && error.message ? error.message : "Failed to upload file";
}

const uploadPercent = ({ loaded, file }: UploadFile) =>
  loaded && file.size ? Math.floor((100 * loaded) / file.size) : 0;

interface UploadFile {
  id: string;
  file: File;
  // The bytes sent so far, once the upload reports them.
  loaded?: number;
  status: "pending" | "uploading" | "completed" | "error";
  error?: string;
}

export interface UploadSectionHandle {
  triggerUpload: () => void;
}

export interface UploadSectionSnapshot {
  hasFile: boolean;
  status: UploadFile["status"] | null;
}

interface UploadSectionProps {
  onUploadSuccess?: () => void;
  buildFormData?: (file: File) => FormData;
  disabled?: boolean;
  showUploadButton?: boolean;
  autoStart?: boolean;
  onStateChange?: (snapshot: UploadSectionSnapshot) => void;
  // One extension or several, separated by commas (as the accept attribute of a file input takes them).
  allowedFileExtension?: string;
  hint?: string;
  uploadUrl?: string;
  // Takes precedence over uploadUrl when the endpoint needs something other
  // than a plain "POST FormData" (e.g. the PDF endpoint, which is a PUT).
  // It may report how many of the file's bytes are sent (`onProgress`).
  onUpload?: (file: File, onProgress: (loaded: number, total: number) => void) => Promise<void>;
}

export const UploadSection = forwardRef<UploadSectionHandle, UploadSectionProps>(function UploadSection(
  {
    onUploadSuccess,
    buildFormData,
    disabled = false,
    showUploadButton = false,
    autoStart = true,
    onStateChange,
    allowedFileExtension = ".ris",
    hint = "RIS files only",
    uploadUrl = DEFAULT_UPLOAD_URL,
    onUpload
  }: UploadSectionProps,
  ref,
) {
  const [currentFile, setCurrentFile] = useState<UploadFile | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  // A dropped file we refuse client-side; kept out of currentFile so it can't be uploaded.
  const [rejection, setRejection] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const createFormData = useCallback(
    (file: File) => {
      if (buildFormData) {
        return buildFormData(file);
      }
      const formData = new FormData();
      formData.append("file", file, file.name);
      return formData;
    },
    [buildFormData],
  );

  useEffect(() => {
    onStateChange?.({
      hasFile: Boolean(currentFile),
      status: currentFile?.status ?? null,
    });
  }, [currentFile, onStateChange]);

  const handleUploadClick = () => {
    if (disabled) return;
    fileInputRef.current?.click();
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (disabled) return;
    const selectedFiles = event.target.files;
    if (!selectedFiles?.length) return;

    const selectedFile = selectedFiles[0];
    const newFile: UploadFile = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: selectedFile,
      status: "pending",
    };

    setRejection(null);
    setCurrentFile(newFile);
    if (autoStart) {
      void uploadFileToServer(newFile);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const uploadFileToServer = useCallback(async (uploadFile: UploadFile) => {
    try {
      setCurrentFile((prev) =>
        prev && prev.id === uploadFile.id ? { ...prev, status: "uploading", loaded: undefined } : prev,
      );

      // A part that is sent again (a retry) reports bytes already counted; the bar never goes back for it. The bar and
      // its text only move by whole percents, not on every one of the many progress events.
      const onProgress = (loaded: number) => {
        setCurrentFile((prev) => {
          if (!prev || prev.id !== uploadFile.id || prev.status !== "uploading") return prev;
          const next = { ...prev, loaded: Math.min(loaded, prev.file.size) };
          const moved =
            prev.loaded === undefined ||
            uploadPercent(next) > uploadPercent(prev) ||
            (next.loaded === prev.file.size && prev.loaded < prev.file.size);
          return moved ? next : prev;
        });
      };

      if (onUpload) {
        await onUpload(uploadFile.file, onProgress);
      } else {
        let formData: FormData;
        try {
          formData = createFormData(uploadFile.file);
        } catch (builderError) {
          const builderMessage =
            builderError instanceof Error ? builderError.message : "Unable to prepare upload payload.";
          setCurrentFile((prev) =>
            prev && prev.id === uploadFile.id
              ? {
                  ...prev,
                  status: "error",
                  error: builderMessage,
                }
              : prev,
          );
          return;
        }

        await apiClient.post(uploadUrl, formData, {
          onUploadProgress: (event) => onProgress(event.loaded),
        });
      }

      setCurrentFile((prev) => (prev && prev.id === uploadFile.id ? { ...prev, status: "completed" } : prev));

      onUploadSuccess?.();
    } catch (error) {
      const errorMessage = getUploadErrorMessage(error);

      setCurrentFile((prev) =>
        prev && prev.id === uploadFile.id
          ? {
              ...prev,
              status: "error",
              error: errorMessage,
            }
          : prev,
      );
    }
  }, [createFormData, onUploadSuccess, onUpload, uploadUrl]);

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    if (disabled) return;
    setIsDragging(true);
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    if (disabled) return;
    setIsDragging(false);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    if (disabled) return;
    setIsDragging(false);

    const droppedFiles = event.dataTransfer.files;
    if (!droppedFiles.length) return;

    const extensions = allowedFileExtension.split(",").map((extension) => extension.trim().toLowerCase());
    const risFile = Array.from(droppedFiles).find((file) =>
      extensions.some((extension) => file.name.toLowerCase().endsWith(extension)),
    );
    if (!risFile) {
      setCurrentFile(null);
      setRejection(`Unsupported file type. Please upload a ${extensions.join(" or ")} file.`);
      return;
    }
    setRejection(null);

    const newFile: UploadFile = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: risFile,
      status: "pending",
    };

    setCurrentFile(newFile);
    if (autoStart) {
      void uploadFileToServer(newFile);
    }
  };

  const triggerUpload = useCallback(() => {
    if (!currentFile || currentFile.status === "uploading" || currentFile.status === "completed") {
      return;
    }
    void uploadFileToServer({ ...currentFile, status: "pending" });
  }, [currentFile, uploadFileToServer]);

  useImperativeHandle(
    ref,
    () => ({
      triggerUpload,
    }),
    [triggerUpload],
  );

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(i === 0 ? 0 : 1)} ${sizes[i]}`;
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex items-center justify-center w-full h-32 border-2 border-dashed rounded-lg transition-colors ${
          isDragging
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
            : `border-gray-300 bg-gray-50 hover:bg-gray-100 dark:hover:bg-gray-800 dark:bg-gray-900 dark:border-gray-600 dark:hover:border-gray-500 ${
                disabled ? "opacity-70 cursor-not-allowed" : "cursor-pointer"
              }`
        }`}
        onClick={handleUploadClick}
        aria-disabled={disabled}
      >
        <div className="flex flex-col items-center justify-center pt-5 pb-6 text-center">
          <Upload className="w-8 h-8 mb-2 text-gray-500 dark:text-gray-400" />
          <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">
            {disabled ? (
              "Enter required details to enable uploads"
            ) : (
              <>
                <span className="font-semibold">Click to upload</span> or drag and drop
              </>
            )}
          </p>
          {!disabled && (
            <p className="text-xs text-gray-500 dark:text-gray-400">{hint}</p>
          )}
        </div>
        <input
          ref={fileInputRef}
          id="dropzone-file"
          type="file"
          className="hidden"
          accept={allowedFileExtension}
          onChange={handleFileChange}
          disabled={disabled}
        />
      </div>

      {rejection && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>File not accepted</AlertTitle>
          <AlertDescription>{rejection}</AlertDescription>
        </Alert>
      )}

      {currentFile ? (
        <div className="space-y-3">
          <div className="border rounded-lg p-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2 flex-1 min-w-0">
                <FileText className="w-5 h-5 mt-0.5 shrink-0 text-gray-500" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{currentFile.file.name}</p>
                  <p className="text-xs text-gray-500">{formatFileSize(currentFile.file.size)}</p>
                </div>
                {showUploadButton && (
                <Button
                  type="button"
                  onClick={triggerUpload}
                  disabled={currentFile.status === "uploading" || currentFile.status === "completed"}
                >
                  Upload PDF
                </Button>)}
              </div>
              
            </div>

            {currentFile.status === "uploading" && (
              <div className="space-y-1">
                <Progress value={uploadPercent(currentFile)} className="h-2" />
                <p className="text-xs text-gray-500 text-right tabular-nums">
                  {currentFile.loaded === undefined
                    ? "Starting upload…"
                    : currentFile.loaded < currentFile.file.size
                      ? `${formatFileSize(currentFile.loaded)} of ${formatFileSize(currentFile.file.size)} (${uploadPercent(currentFile)}%)`
                      : "Uploaded, processing…"}
                </p>
              </div>
            )}

            {currentFile.status === "error" && currentFile.error && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Upload failed</AlertTitle>
                <AlertDescription>{currentFile.error}</AlertDescription>
              </Alert>
            )}
          </div>
        </div>
      ) : (
        <></>
      )}
    </div>
  );
});
