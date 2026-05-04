import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { uploadTranscriptWithDetails } from "../api";

interface FileEntry {
  id: string;
  name: string;
  size: string;
  status: "queued" | "uploading" | "uploaded" | "failed";
  s3Key?: string;
  error?: string;
}

interface ApplicationDraft {
  applicationId: string;
}

function UploadNotification({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  const t = useT();
  const [isClosing, setIsClosing] = useState(false);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      requestClose();
    }, 4200);
    return () => window.clearTimeout(timeout);
  }, []);

  function requestClose() {
    if (isClosing) return;
    setIsClosing(true);
    window.setTimeout(onClose, 150);
  }

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={requestClose}
      style={{
        position: "fixed",
        top: 20,
        left: "50%",
        marginLeft: "-1px",
        zIndex: 60,
        width: "min(500px, calc(100vw - 24px))",
        pointerEvents: "auto",
        animation: `${isClosing ? "uploadNoticeOut" : "uploadNoticeIn"} 150ms cubic-bezier(.22,1,.36,1) forwards`,
      }}
    >
      <style>{`
        @keyframes uploadNoticeIn {
          from {
            opacity: 0;
            transform: translateX(-50%) translateY(-24px) scale(0.96);
          }
          to {
            opacity: 1;
            transform: translateX(-50%) translateY(0) scale(1);
          }
        }
        @keyframes uploadNoticeOut {
          from {
            opacity: 1;
            transform: translateX(-50%) translateY(0) scale(1);
          }
          to {
            opacity: 0;
            transform: translateX(-50%) translateY(-30px) scale(0.94);
          }
        }
      `}</style>
      <div
        style={{
          background: "rgba(255,255,255,0.96)",
          backdropFilter: "blur(14px)",
          WebkitBackdropFilter: "blur(14px)",
          color: t.ink,
          border: `1px solid ${t.line}`,
          boxShadow: "0 22px 52px rgba(15,23,42,0.18)",
          borderRadius: 22,
          padding: "14px 16px 14px 14px",
          display: "grid",
          gridTemplateColumns: "48px 1fr 28px",
          gap: 12,
          alignItems: "center",
        }}
      >
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 16,
            background: `linear-gradient(180deg, ${t.ok} 0%, #1f7f7d 100%)`,
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 20,
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.18)",
          }}
        >
          ↑
        </div>
        <div style={{ minWidth: 0 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 800,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              color: t.ink4,
              fontFamily: t.mono,
              marginBottom: 3,
            }}
          >
            Upload Complete
          </div>
          <div
            style={{
              fontSize: 14,
              lineHeight: 1.45,
              color: t.ink2,
            }}
          >
            {message}
          </div>
        </div>
        <button
          onClick={(event) => {
            event.stopPropagation();
            requestClose();
          }}
          aria-label="Dismiss upload notification"
          style={{
            border: "none",
            background: "transparent",
            color: t.ink4,
            cursor: "pointer",
            fontSize: 20,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ×
        </button>
      </div>
    </div>
  );
}

const emptyDraft: ApplicationDraft = {
  applicationId: "",
};

const applicationIdPattern = /^[A-Za-z0-9._-]+$/;

function buildTemporaryApplicantName(applicationId: string) {
  return `USER-${applicationId.trim()}`;
}

export function UploadPage() {
  const t = useT();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedFilesRef = useRef<Record<string, File>>({});
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [draft, setDraft] = useState<ApplicationDraft>(emptyDraft);
  const [dragOver, setDragOver] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const pdfFiles = Array.from(incoming).filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    if (pdfFiles.length === 0) return;
    const newEntries: FileEntry[] = pdfFiles.map((f) => ({
      id: crypto.randomUUID(),
      name: f.name,
      size: formatSize(f.size),
      status: "queued" as const,
    }));
    setFiles((prev) => [...prev, ...newEntries]);
    newEntries.forEach((entry, index) => {
      const file = pdfFiles[index];
      if (file) selectedFilesRef.current[entry.id] = file;
    });
  };

  const uploadOne = async (file: File, id: string, details: ApplicationDraft) => {
    setFiles((prev) =>
      prev.map((entry) =>
        entry.id === id
          ? { ...entry, status: "uploading" }
          : entry
      )
    );
    try {
      const result = await uploadTranscriptWithDetails(file, details);
      setFiles((prev) =>
        prev.map((entry) =>
          entry.id === id
            ? { ...entry, status: "uploaded", s3Key: result.s3Key }
            : entry
        )
      );
      setToast(`${file.name} uploaded. Extraction has started.`);
      return true;
    } catch (err) {
      setFiles((prev) =>
        prev.map((entry) =>
          entry.id === id
            ? {
                ...entry,
                status: "failed",
                error: err instanceof Error ? err.message : "Upload failed",
              }
            : entry
        )
      );
      return false;
    }
  };

  const startUploads = () => {
    const details = {
      ...draft,
      applicantName: buildTemporaryApplicantName(draft.applicationId),
    };
    void Promise.all(
      files
        .filter((entry) => entry.status === "queued" || entry.status === "failed")
        .map((entry) => {
          const file = selectedFilesRef.current[entry.id];
          return file ? uploadOne(file, entry.id, details) : Promise.resolve();
        })
    ).then((results) => {
      const succeeded = results.every(Boolean);
      if (!succeeded) return;
      selectedFilesRef.current = {};
      setFiles([]);
      setDraft(emptyDraft);
    });
  };

  const applicationIdMissing = draft.applicationId.trim().length === 0;
  const applicationIdInvalid =
    !applicationIdMissing && !applicationIdPattern.test(draft.applicationId.trim());

  return (
    <>
      {toast && <UploadNotification message={toast} onClose={() => setToast(null)} />}
      <PageHeader
        eyebrow="New intake"
        title="Upload transcript"
        subtitle="Upload one or more transcript PDFs. Extraction will begin automatically once submitted."
      />
      <div style={{ padding: "24px 34px 40px", maxWidth: 880, margin: "0 auto" }}>
        <Card
          title="Application details"
          subtitle="Enter the application ID before upload."
        >
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 5,
              maxWidth: 400,
            }}
          >
            <span
              style={{
                fontSize: 10,
                color: t.ink3,
                letterSpacing: 0.5,
                textTransform: "uppercase",
                fontFamily: t.mono,
              }}
            >
              Application ID
            </span>
            <input
              value={draft.applicationId}
              required
              maxLength={80}
              pattern={applicationIdPattern.source}
              title="Use letters, numbers, dots, underscores, or hyphens."
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  applicationId: e.target.value,
                }))
              }
              style={{
                border: `1px solid ${applicationIdInvalid ? t.high : t.line}`,
                background: t.surfaceAlt,
                color: t.ink,
                padding: "9px 10px",
                borderRadius: 3,
                fontSize: 13,
                fontFamily: "inherit",
                outlineColor: t.accent,
              }}
            />
            {applicationIdInvalid && (
              <span
                style={{
                  color: t.high,
                  fontSize: 11,
                  lineHeight: 1.3,
                }}
              >
                Use letters, numbers, dots, underscores, or hyphens.
              </span>
            )}
          </label>
        </Card>

        <div style={{ height: 14 }} />

        <Card
          title="Transcript files"
          actions={
            <span
              aria-label="PDF only"
              title="PDF only"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 9px",
                border: `1px solid ${t.line}`,
                background: t.surfaceAlt,
                color: t.ink3,
                borderRadius: 999,
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: 0.6,
                textTransform: "uppercase",
                fontFamily: t.mono,
              }}
            >
              <svg
                width="12"
                height="14"
                viewBox="0 0 12 14"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="M1.5 0.5h6L11 4v9a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 1 13V1a.5.5 0 0 1 .5-.5Z"
                  stroke="currentColor"
                  strokeLinejoin="round"
                />
                <path d="M7.5 0.5V4h3" stroke="currentColor" strokeLinejoin="round" />
              </svg>
              PDF
            </span>
          }
        >
          {/* Dropzone */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            style={{ display: "none" }}
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
          />
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              addFiles(e.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${dragOver ? t.accent : t.line}`,
              background: dragOver ? t.accentBg : t.surfaceAlt,
              padding: "36px 20px",
              textAlign: "center",
              borderRadius: 3,
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            <div
              style={{
                fontSize: 28,
                color: t.ink3,
                marginBottom: 8,
                fontFamily: t.serif,
              }}
            >
              &uarr;
            </div>
            <div
              style={{
                fontSize: 15,
                fontWeight: 600,
                color: t.ink,
                fontFamily: t.serif,
              }}
            >
              Drop PDF here or click to browse
            </div>
            <div style={{ fontSize: 12, color: t.ink3, marginTop: 4 }}>
              Multi-page transcripts are OK — each page will be extracted
              separately
            </div>
          </div>

          {/* File list */}
          {files.length > 0 && (
            <div
              style={{
                marginTop: 16,
                border: `1px solid ${t.line2}`,
                borderRadius: 3,
              }}
            >
              {files.map((f, i) => (
                <div
                  key={f.id}
                  style={{
                    padding: "10px 14px",
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    borderBottom:
                      i < files.length - 1
                        ? `1px solid ${t.line2}`
                        : "none",
                  }}
                >
                  <div
                    style={{
                      width: 28,
                      height: 34,
                      border: `1px solid ${t.line}`,
                      background: t.surface,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 9,
                      fontWeight: 700,
                      color: t.ink3,
                      fontFamily: t.mono,
                      borderRadius: 2,
                    }}
                  >
                    PDF
                  </div>
                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 500,
                        color: t.ink,
                        fontFamily: t.mono,
                      }}
                    >
                      {f.name}
                    </div>
                    <div
                      style={{ fontSize: 11, color: t.ink4, marginTop: 2 }}
                    >
                      {f.size}
                    </div>
                  </div>
                  {f.status === "uploading" || f.status === "queued" ? (
                    <span
                      style={{
                        fontSize: 11,
                        color: t.med,
                        fontFamily: t.mono,
                        letterSpacing: 0.4,
                        textTransform: "uppercase",
                      }}
                    >
                      &bull; {f.status === "queued" ? "Queued" : "Uploading"}
                    </span>
                  ) : f.status === "failed" ? (
                    <span
                      title={f.error}
                      style={{
                        fontSize: 11,
                        color: t.high,
                        fontFamily: t.mono,
                        letterSpacing: 0.4,
                        textTransform: "uppercase",
                      }}
                    >
                      &times; Failed
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: 11,
                        color: t.ok,
                        fontFamily: t.mono,
                        letterSpacing: 0.4,
                        textTransform: "uppercase",
                      }}
                    >
                      &check; Ready
                    </span>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      delete selectedFilesRef.current[f.id];
                      setFiles((x) => x.filter((entry) => entry.id !== f.id));
                    }}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: t.ink4,
                      cursor: "pointer",
                      fontSize: 16,
                    }}
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div style={{ height: 14 }} />

        <div
          style={{
            display: "flex",
            gap: 10,
            justifyContent: "flex-end",
          }}
        >
          <Btn variant="ghost" onClick={() => navigate("/dashboard")}>Cancel</Btn>
          <Btn
            variant="primary"
            disabled={
              files.length === 0 ||
              applicationIdMissing ||
              applicationIdInvalid ||
              files.some((f) => f.status === "uploading") ||
              files.every((f) => f.status === "uploaded")
            }
            onClick={startUploads}
          >
            Start processing
          </Btn>
        </div>
      </div>
    </>
  );
}
