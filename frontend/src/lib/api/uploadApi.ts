import clientApi from "./clientApi";

/**
 * Uploading a video a piece at a time.
 *
 * A 500 MB file sent as one request fails entirely on any dropped
 * connection, and forced the gateway to accept a body that large from
 * anyone who asked. Each part is its own request, so a drop costs one
 * part, and an upload survives the page being closed: the server is
 * asked which parts it already holds and only the rest are sent.
 */

export interface UploadStarted {
  upload_id: string;
  part_size: number;
  total_parts: number;
}

export interface UploadStatus {
  upload_id: string;
  part_size: number;
  declared_size: number;
  received_parts: number[];
  received_bytes: number;
}

export interface UploadMetadata {
  title: string;
  description: string;
  privacy: "public" | "private";
  category: string;
  thumbnail?: File;
}

/** Where a resumable upload remembers itself between page loads. */
const RESUME_KEY = "video-upload-in-progress";

interface ResumeRecord {
  uploadId: string;
  name: string;
  size: number;
  lastModified: number;
}

/** A file cannot be stored in the browser, so it is recognised by what
 *  can: the three things a File tells us without reading it. */
function fingerprint(file: File): Omit<ResumeRecord, "uploadId"> {
  return { name: file.name, size: file.size, lastModified: file.lastModified };
}

export function rememberUpload(uploadId: string, file: File): void {
  try {
    localStorage.setItem(
      RESUME_KEY,
      JSON.stringify({ uploadId, ...fingerprint(file) }),
    );
  } catch {
    // Private browsing, or storage full. Resuming is a convenience; the
    // upload itself must not depend on it.
  }
}

export function forgetUpload(): void {
  try {
    localStorage.removeItem(RESUME_KEY);
  } catch {
    /* see above */
  }
}

/** The id of an interrupted upload of *this* file, if there is one.
 *
 *  The fingerprint has to match: resuming into a different file would
 *  assemble parts of two videos into one object. */
export function findResumableUpload(file: File): string | null {
  try {
    const raw = localStorage.getItem(RESUME_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as ResumeRecord;
    const now = fingerprint(file);
    const matches =
      saved.name === now.name &&
      saved.size === now.size &&
      saved.lastModified === now.lastModified;
    return matches ? saved.uploadId : null;
  } catch {
    return null;
  }
}

export const startUpload = async (file: File): Promise<UploadStarted> => {
  const res = await clientApi.post<UploadStarted>("/api/files/uploads", {
    filename: file.name,
    content_type: file.type || "video/mp4",
    size: file.size,
  });
  return res.data;
};

export const getUploadStatus = async (uploadId: string): Promise<UploadStatus> => {
  const res = await clientApi.get<UploadStatus>(`/api/files/uploads/${uploadId}`);
  return res.data;
};

export const sendPart = async (
  uploadId: string,
  partNumber: number,
  blob: Blob,
  signal?: AbortSignal,
): Promise<UploadStatus> => {
  const res = await clientApi.put<UploadStatus>(
    `/api/files/uploads/${uploadId}/parts/${partNumber}`,
    blob,
    { headers: { "Content-Type": "application/octet-stream" }, signal },
  );
  return res.data;
};

export const completeUpload = async (
  uploadId: string,
  meta: UploadMetadata,
): Promise<unknown> => {
  // The metadata travels in the body, not the query string: a title or
  // description in the URL would be recorded in the gateway's access log.
  const form = new FormData();
  form.append("name", meta.title);
  form.append("description", meta.description);
  form.append("privacy", meta.privacy);
  form.append("category", meta.category);
  if (meta.thumbnail) form.append("thumbnail", meta.thumbnail);

  const res = await clientApi.post(
    `/api/files/uploads/${uploadId}/complete`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
};

export const abortUpload = async (uploadId: string): Promise<void> => {
  await clientApi.delete(`/api/files/uploads/${uploadId}`);
};

export interface UploadProgress {
  /** 0 to 1, by bytes rather than parts: parts are equal but the last. */
  ratio: number;
  sentBytes: number;
  totalBytes: number;
  resumed: boolean;
}

/**
 * Send a file in parts, skipping anything the server already holds.
 *
 * Retries each part a few times before giving up: a part failing is the
 * ordinary case this whole design exists for, and losing 10 MB to one
 * flaky request would defeat the point.
 */
export async function uploadInParts(
  file: File,
  meta: UploadMetadata,
  onProgress?: (progress: UploadProgress) => void,
  signal?: AbortSignal,
): Promise<unknown> {
  const existing = findResumableUpload(file);
  let uploadId = existing;
  let partSize: number;
  let received = new Set<number>();
  let resumed = false;

  if (uploadId) {
    try {
      const status = await getUploadStatus(uploadId);
      partSize = status.part_size;
      received = new Set(status.received_parts);
      resumed = received.size > 0;
    } catch {
      // Expired, swept, or belongs to another account now. Starting over
      // is correct; silently resuming into nothing would not be.
      forgetUpload();
      uploadId = null;
      partSize = 0;
    }
  }

  if (!uploadId) {
    const started = await startUpload(file);
    uploadId = started.upload_id;
    partSize = started.part_size;
    rememberUpload(uploadId, file);
  }

  const totalParts = Math.max(1, Math.ceil(file.size / partSize!));
  let sentBytes = [...received].reduce(
    (total, part) =>
      total + Math.min(partSize!, file.size - (part - 1) * partSize!),
    0,
  );
  onProgress?.({ ratio: sentBytes / file.size, sentBytes, totalBytes: file.size, resumed });

  for (let part = 1; part <= totalParts; part++) {
    if (received.has(part)) continue;

    const start = (part - 1) * partSize!;
    const blob = file.slice(start, Math.min(start + partSize!, file.size));

    let lastError: unknown;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        await sendPart(uploadId, part, blob, signal);
        lastError = undefined;
        break;
      } catch (err) {
        if (signal?.aborted) throw err;
        lastError = err;
        // Brief, growing pause: an immediate retry tends to meet the
        // same broken connection.
        await new Promise((resolve) => setTimeout(resolve, 500 * (attempt + 1)));
      }
    }
    if (lastError) throw lastError;

    sentBytes += blob.size;
    onProgress?.({
      ratio: sentBytes / file.size,
      sentBytes,
      totalBytes: file.size,
      resumed,
    });
  }

  const result = await completeUpload(uploadId, meta);
  forgetUpload();
  return result;
}

export default {
  startUpload,
  getUploadStatus,
  sendPart,
  completeUpload,
  abortUpload,
  uploadInParts,
  findResumableUpload,
  forgetUpload,
};
