/** Record a canvas to a .webm file while `play` runs. Works in current Chrome, Edge and Firefox (MediaRecorder + captureStream). */
export const canRecord = () => typeof MediaRecorder !== "undefined" && typeof HTMLCanvasElement.prototype.captureStream === "function";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function recordCanvas(canvas: HTMLCanvasElement, play: () => Promise<void>, filename: string, holdMs = 1200): Promise<Blob> {
  const mimeType = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((m) => MediaRecorder.isTypeSupported(m));
  const recorder = new MediaRecorder(canvas.captureStream(30), { mimeType, videoBitsPerSecond: 2_500_000 });
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  const stopped = new Promise<void>((resolve) => { recorder.onstop = () => resolve(); });
  recorder.start();
  try {
    await play();
    await sleep(holdMs);                    // hold the final frame so the video does not end abruptly
  } finally {
    recorder.stop();
  }
  await stopped;
  const blob = new Blob(chunks, { type: "video/webm" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
  return blob;
}
