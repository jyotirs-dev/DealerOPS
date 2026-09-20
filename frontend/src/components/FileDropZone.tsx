import { useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import { CloseIcon, UploadIcon } from "./icons";

type FileDropZoneProps = {
  id: string;
  label: string;
  accept: string;
  hint: string;
  files: File[];
  multiple?: boolean;
  onFilesChange: (files: File[]) => void;
};

function isSameFile(a: File, b: File): boolean {
  return a.name === b.name && a.size === b.size && a.lastModified === b.lastModified;
}

function filterAccepted(files: File[], accept: string): File[] {
  const extensions = accept
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter(Boolean);

  if (extensions.length === 0) {
    return files;
  }

  return files.filter((file) =>
    extensions.some((extension) => file.name.toLowerCase().endsWith(extension)),
  );
}

export function FileDropZone({
  id,
  label,
  accept,
  hint,
  files,
  multiple = false,
  onFilesChange,
}: FileDropZoneProps) {
  const [isDraggingOver, setIsDraggingOver] = useState(false);
  const [rejectedCount, setRejectedCount] = useState(0);

  function handleSelection(selected: File[]) {
    const accepted = filterAccepted(selected, accept);
    setRejectedCount(selected.length - accepted.length);
    if (accepted.length === 0) {
      return;
    }
    if (!multiple) {
      onFilesChange(accepted.slice(0, 1));
      return;
    }
    const merged = [...files];
    for (const file of accepted) {
      if (!merged.some((existing) => isSameFile(existing, file))) {
        merged.push(file);
      }
    }
    onFilesChange(merged);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDraggingOver(false);
    handleSelection(Array.from(event.dataTransfer.files));
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleSelection(Array.from(event.target.files ?? []));
    // Reset so removing a file and picking the same one again still fires change.
    event.target.value = "";
  }

  function removeFile(target: File) {
    onFilesChange(files.filter((file) => file !== target));
  }

  return (
    <div className="dropzone-block">
      <label className="dropzone-label" htmlFor={id}>
        {label}
      </label>
      <div
        className={isDraggingOver ? "dropzone dragging" : "dropzone"}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDraggingOver(true);
        }}
        onDragLeave={() => setIsDraggingOver(false)}
        onDrop={handleDrop}
      >
        <span className="dropzone-icon">
          <UploadIcon />
        </span>
        <span className="dropzone-prompt">
          Drag {multiple ? "files" : "a file"} here, or{" "}
          <label className="dropzone-browse" htmlFor={id}>
            browse
          </label>
        </span>
        <span className="dropzone-hint">{hint}</span>
        {rejectedCount > 0 ? (
          <span className="dropzone-error" role="alert">
            {rejectedCount === 1
              ? "1 file was skipped — unsupported file type."
              : `${rejectedCount} files were skipped — unsupported file type.`}
          </span>
        ) : null}
        <input
          id={id}
          name={id}
          type="file"
          accept={accept}
          multiple={multiple}
          className="dropzone-input"
          onChange={handleInputChange}
        />
      </div>

      {files.length > 0 ? (
        <ul className="file-chip-row">
          {files.map((file) => (
            <li key={`${file.name}-${file.size}`} className="file-chip">
              {file.name}
              <button
                type="button"
                className="file-chip-remove"
                aria-label={`Remove ${file.name}`}
                onClick={() => removeFile(file)}
              >
                <CloseIcon size={11} />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
