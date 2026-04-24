import { useState, useRef } from "react";
import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { uploadTranscript } from "../api";

interface FileEntry {
  id: string;
  name: string;
  size: string;
  status: "queued" | "uploading" | "uploaded" | "failed";
  s3Key?: string;
  error?: string;
}

export function UploadPage() {
  const t = useT();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragOver, setDragOver] = useState(false);

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
    void Promise.all(
      pdfFiles.map((file, index) => {
        const entry = newEntries[index];
        return entry ? uploadOne(file, entry.id) : Promise.resolve();
      })
    );
  };

  const uploadOne = async (file: File, id: string) => {
    setFiles((prev) =>
      prev.map((entry) =>
        entry.id === id
          ? { ...entry, status: "uploading" }
          : entry
      )
    );
    try {
      const result = await uploadTranscript(file);
      setFiles((prev) =>
        prev.map((entry) =>
          entry.id === id
            ? { ...entry, status: "uploaded", s3Key: result.s3Key }
            : entry
        )
      );
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

  return (
    <>
      <PageHeader
        eyebrow="New intake"
        title="Upload transcript"
        subtitle="Upload one or more transcript PDFs. Extraction will begin automatically once submitted."
      />
      <div style={{ padding: "24px 34px 40px", maxWidth: 880 }}>
        <Card
          title="Application details"
          subtitle="Applicant, institution, country, and program details are extracted from the transcript after upload. Application ID is assigned by intake."
        >
          <div style={{ fontSize: 13, color: t.ink2, lineHeight: 1.6 }}>
            Once the PDF is uploaded, S3 starts the extraction pipeline. The case
            appears in the review queue when Nova extraction and rule validation
            finish. If no country is printed on the transcript, the system stores
            USA by default.
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
          <Btn variant="ghost">Cancel</Btn>
          <Btn variant="primary" disabled={files.length === 0 || files.some((f) => f.status === "uploading" || f.status === "queued")}>
            Processing starts automatically
          </Btn>
        </div>
      </div>
    </>
  );
}
