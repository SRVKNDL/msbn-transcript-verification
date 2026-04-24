import { useState, useRef } from "react";
import { useT } from "../theme";
import { PageHeader, Card, Btn } from "../components/Shell";
import { COUNTRIES } from "../countries";

function Field({
  label,
  value,
  onChange,
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  mono?: boolean;
}) {
  const t = useT();
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          color: t.ink3,
          letterSpacing: 0.5,
          textTransform: "uppercase",
          fontFamily: t.mono,
          marginBottom: 5,
        }}
      >
        {label}
      </div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%",
          padding: "9px 12px",
          background: t.surfaceAlt,
          border: `1px solid ${t.line}`,
          borderRadius: 3,
          fontSize: 13,
          color: t.ink,
          fontFamily: mono ? t.mono : "inherit",
          boxSizing: "border-box",
        }}
      />
    </div>
  );
}

interface FileEntry {
  name: string;
  size: string;
  status: "uploading" | "uploaded";
}

export function UploadPage() {
  const t = useT();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [applicantName, setApplicantName] = useState("");
  const [applicationNum, setApplicationNum] = useState("");
  const [institution, setInstitution] = useState("");
  const [country, setCountry] = useState("");
  const [extracting, setExtracting] = useState(false);

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  // Simulated metadata extraction from uploaded transcript
  // In production this calls the Extract Lambda / Nova to read the PDF
  const simulateExtraction = () => {
    setExtracting(true);
    setTimeout(() => {
      setApplicantName("Okonkwo, Patricia A.");
      setApplicationNum("MSBN-2026-" + String(Math.floor(1000 + Math.random() * 9000)));
      setInstitution("St. Therese School of Nursing");
      setCountry("Philippines");
      setExtracting(false);
    }, 1500);
  };

  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const pdfFiles = Array.from(incoming).filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    if (pdfFiles.length === 0) return;
    const isFirstUpload = files.length === 0;
    const newEntries: FileEntry[] = pdfFiles.map((f) => ({
      name: f.name,
      size: formatSize(f.size),
      status: "uploading" as const,
    }));
    setFiles((prev) => [...prev, ...newEntries]);
    setTimeout(
      () =>
        setFiles((prev) =>
          prev.map((x) =>
            x.status === "uploading" ? { ...x, status: "uploaded" as const } : x
          )
        ),
      900
    );
    // Auto-fill metadata on first upload
    if (isFirstUpload) {
      simulateExtraction();
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
          subtitle={
            extracting
              ? "Extracting metadata from transcript..."
              : files.length === 0
                ? "Upload a transcript to auto-fill details"
                : "Match to an existing MSBN application or create a new one"
          }
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 14,
            }}
          >
            <Field label="Applicant name" value={applicantName} onChange={setApplicantName} />
            <Field label="MSBN application #" value={applicationNum} onChange={setApplicationNum} mono />
            <Field label="Institution" value={institution} onChange={setInstitution} />
            <div>
              <div
                style={{
                  fontSize: 10,
                  color: t.ink3,
                  letterSpacing: 0.5,
                  textTransform: "uppercase",
                  fontFamily: t.mono,
                  marginBottom: 5,
                }}
              >
                Country of issue
              </div>
              <select
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                style={{
                  width: "100%",
                  padding: "9px 12px",
                  background: t.surfaceAlt,
                  border: `1px solid ${t.line}`,
                  borderRadius: 3,
                  fontSize: 13,
                  color: t.ink,
                  fontFamily: "inherit",
                  boxSizing: "border-box",
                  cursor: "pointer",
                }}
              >
                {COUNTRIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
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
                  key={i}
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
                  {f.status === "uploading" ? (
                    <span
                      style={{
                        fontSize: 11,
                        color: t.med,
                        fontFamily: t.mono,
                        letterSpacing: 0.4,
                        textTransform: "uppercase",
                      }}
                    >
                      &bull; Uploading
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
                      setFiles((x) => x.filter((_, j) => j !== i));
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
          <Btn variant="outline">Save draft</Btn>
          <Btn variant="primary" disabled={files.length === 0}>
            Submit for extraction &rarr;
          </Btn>
        </div>
      </div>
    </>
  );
}
