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
  applicantName: string;
  institution: string;
  country: string;
}

const emptyDraft: ApplicationDraft = {
  applicationId: "",
  applicantName: "",
  institution: "",
  country: "",
};

const applicationIdPattern = /^[A-Za-z0-9._-]+$/;

function cleanExtractedValue(value: string | undefined) {
  return (value ?? "")
    .replace(/[\u0000-\u001f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function extractAfterLabel(text: string, labels: string[]) {
  for (const label of labels) {
    const match = text.match(
      new RegExp(`${label}\\s*[:\\-]?\\s*([^\\n\\r]{2,120})`, "i")
    );
    const value = cleanExtractedValue(match?.[1]);
    if (value) return value;
  }
  return "";
}

async function extractDraftFromPdf(file: File): Promise<Partial<ApplicationDraft>> {
  const buffer = await file.arrayBuffer();
  const text = new TextDecoder("latin1").decode(buffer);
  const filenameBase = file.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ");

  return {
    applicantName:
      extractAfterLabel(text, ["student name", "applicant name", "name"]) ||
      cleanExtractedValue(filenameBase.match(/^([a-z ,.'-]{4,80})/i)?.[1]),
    institution: extractAfterLabel(text, [
      "institution",
      "school",
      "college",
      "university",
    ]),
    country: extractAfterLabel(text, ["country"]),
  };
}

export function UploadPage() {
  const t = useT();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectedFilesRef = useRef<Record<string, File>>({});
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [draft, setDraft] = useState<ApplicationDraft>(emptyDraft);
  const [draftExtractionAttempted, setDraftExtractionAttempted] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timeout = window.setTimeout(() => setToast(null), 4500);
    return () => window.clearTimeout(timeout);
  }, [toast]);

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
    setDraftExtractionAttempted(false);
    void extractDraftFromPdf(pdfFiles[0])
      .then((extracted) => {
        setDraft((current) => ({
          applicationId: current.applicationId,
          applicantName: current.applicantName || extracted.applicantName || "",
          institution: current.institution || extracted.institution || "",
          country: current.country || extracted.country || "",
        }));
      })
      .finally(() => setDraftExtractionAttempted(true));
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
    }
  };

  const startUploads = () => {
    const details = { ...draft };
    void Promise.all(
      files
        .filter((entry) => entry.status === "queued" || entry.status === "failed")
        .map((entry) => {
          const file = selectedFilesRef.current[entry.id];
          return file ? uploadOne(file, entry.id, details) : Promise.resolve();
        })
    );
  };

  const applicationIdMissing = draft.applicationId.trim().length === 0;
  const applicationIdInvalid =
    !applicationIdMissing && !applicationIdPattern.test(draft.applicationId.trim());
  const missingExtractedPlaceholder = draftExtractionAttempted
    ? "Needs manual entry"
    : "";

  return (
    <>
      {toast && (
        <div
          role="status"
          style={{
            position: "fixed",
            right: 24,
            bottom: 24,
            zIndex: 40,
            background: t.surface,
            color: t.ink,
            border: `1px solid ${t.line}`,
            borderTop: `3px solid ${t.ok}`,
            boxShadow: "0 16px 42px rgba(0,0,0,0.24)",
            padding: "12px 16px",
            borderRadius: 3,
            maxWidth: 360,
            fontSize: 13,
            lineHeight: 1.45,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 2 }}>
            Upload complete
          </div>
          <div style={{ color: t.ink3 }}>{toast}</div>
        </div>
      )}
      <PageHeader
        eyebrow="New intake"
        title="Upload transcript"
        subtitle="Upload one or more transcript PDFs. Extraction will begin automatically once submitted."
      />
      <div style={{ padding: "24px 34px 40px", maxWidth: 880 }}>
        <Card
          title="Application details"
          subtitle="Review or enter the applicant information before upload."
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
            }}
          >
            {(
              [
                ["applicantName", "Applicant name"],
                ["institution", "Institution"],
                ["country", "Country"],
                ["applicationId", "Application ID"],
              ] as const
            ).map(([key, label]) => (
              <label
                key={key}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 5,
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
                  {label}
                </span>
                <input
                  value={draft[key]}
                  placeholder={
                    key === "applicationId" ? "" : missingExtractedPlaceholder
                  }
                  required={key === "applicationId"}
                  maxLength={key === "applicationId" ? 80 : undefined}
                  pattern={
                    key === "applicationId" ? applicationIdPattern.source : undefined
                  }
                  title={
                    key === "applicationId"
                      ? "Use letters, numbers, dots, underscores, or hyphens."
                      : undefined
                  }
                  onChange={(e) =>
                    setDraft((current) => ({
                      ...current,
                      [key]: e.target.value,
                    }))
                  }
                  style={{
                    border: `1px solid ${
                      key === "applicationId" && applicationIdInvalid
                        ? t.high
                        : t.line
                    }`,
                    background: t.surfaceAlt,
                    color: t.ink,
                    padding: "9px 10px",
                    borderRadius: 3,
                    fontSize: 13,
                    fontFamily: "inherit",
                    outlineColor: t.accent,
                  }}
                />
              </label>
            ))}
          </div>
        </Card>

        <div style={{ height: 14 }} />

        <Card
          title="Transcript files"
          subtitle="PDF only \u00b7 max 25 MB per file"
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
