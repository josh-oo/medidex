"use client";

import { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from "react";
import { Upload, FileText, X, CheckCircle2, AlertCircle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface UploadFile {
  id: string;
  file: File;
  progress: number;
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
  allowedFileExtension?: string;
  hint?: string;
  uploadUrl?: string;
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
    uploadUrl = "/api/meerkat/projects"
  }: UploadSectionProps,
  ref,
) {
  const [currentFile, setCurrentFile] = useState<UploadFile | null>(null);
  const [isDragging, setIsDragging] = useState(false);
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
      progress: 0,
      status: "pending",
    };

    setCurrentFile(newFile);
    if (autoStart) {
      void uploadFileToServer(newFile);
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const uploadFileToServer = useCallback(async (uploadFile: UploadFile) => {
    let progressInterval: NodeJS.Timeout | null = null;

    try {
      setCurrentFile((prev) =>
        prev && prev.id === uploadFile.id ? { ...prev, status: "uploading", progress: 10 } : prev,
      );

      progressInterval = setInterval(() => {
        setCurrentFile((prev) => {
          if (!prev || prev.id !== uploadFile.id || prev.status !== "uploading") {
            return prev;
          }
          if (prev.progress >= 90) return prev;
          return { ...prev, progress: Math.min(prev.progress + 10, 90) };
        });
      }, 200);

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

      const response = await fetch(uploadUrl, {
        method: "POST",
        body: formData,
        cache: "no-store",
        headers: {
          "Cache-Control": "no-cache",
          Pragma: "no-cache",
        },
      });

      if (!response.ok) {
        const errorMessage = await response.text();
        throw new Error(errorMessage || "Failed to upload file.");
      }

      if (progressInterval) {
        clearInterval(progressInterval);
      }

      setCurrentFile((prev) =>
        prev && prev.id === uploadFile.id
          ? { ...prev, status: "completed", progress: 100 }
          : prev,
      );

      onUploadSuccess?.();
    } catch (error) {
      if (progressInterval) {
        clearInterval(progressInterval);
      }

      let errorMessage = "Failed to upload file";
      if (error instanceof Error) {
        errorMessage = error.message;
      } else if (typeof error === "object" && error !== null) {
        const errorObj = error as Record<string, unknown>;
        const detail = (errorObj as any)?.response?.data?.detail;
        if (typeof detail === "string") {
          errorMessage = detail;
        } else if (detail) {
          errorMessage = JSON.stringify(detail);
        } else if (typeof (errorObj as any)?.message === "string") {
          errorMessage = (errorObj as any).message;
        }
      }

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
  }, [createFormData, onUploadSuccess]);

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

    const risFile = Array.from(droppedFiles).find((file) =>
      file.name.toLowerCase().endsWith(allowedFileExtension),
    );
    if (!risFile) return;

    const newFile: UploadFile = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: risFile,
      progress: 0,
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
    return `${Math.round((bytes / Math.pow(k, i)) * 100) / 100} ${sizes[i]}`;
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
                <Progress value={currentFile.progress} className="h-2" />
                <p className="text-xs text-gray-500 text-right">{currentFile.progress}%</p>
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
