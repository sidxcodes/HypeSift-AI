import type { Chunk } from "./types";

/** Mirrors backend `captions.chunk_words` so the live preview matches the export. */
export function chunkWords(words: { w: string; s: number; e: number }[], maxWords = 3, maxGap = 0.55): Chunk[] {
  const maxChars = Math.floor((16 * maxWords) / 2) + 12;
  const chunks: Chunk[] = [];
  let cur: { w: string; s: number; e: number }[] = [];
  const flush = () => {
    if (cur.length) {
      chunks.push({ s: cur[0].s, e: cur[cur.length - 1].e, text: cur.map((x) => x.w).join(" "), words: cur.map((x) => ({ ...x })) });
      cur = [];
    }
  };
  for (const w of words) {
    if (cur.length) {
      const gap = w.s - cur[cur.length - 1].e;
      const chars = cur.reduce((n, x) => n + x.w.length + 1, 0) + w.w.length;
      if (cur.length >= maxWords || chars > maxChars || gap > maxGap || /[.?!]$/.test(cur[cur.length - 1].w)) flush();
    }
    cur.push(w);
  }
  flush();
  for (let i = 0; i + 1 < chunks.length; i++) {
    const gap = chunks[i + 1].s - chunks[i].e;
    if (gap > 0 && gap < 0.35) chunks[i].e = chunks[i + 1].s;
  }
  return chunks;
}

/** After a text edit, spread word timings evenly across the chunk (same as backend). */
export function retime(chunk: Chunk): Chunk {
  const parts = chunk.text.split(/\s+/).filter(Boolean);
  if (parts.join(" ") === chunk.words.map((w) => w.w).join(" ")) return chunk;
  const total = parts.reduce((n, p) => n + p.length, 0) || 1;
  let t = chunk.s;
  const words = parts.map((p) => {
    const d = ((chunk.e - chunk.s) * p.length) / total;
    const w = { w: p, s: +t.toFixed(3), e: +(t + d).toFixed(3) };
    t += d;
    return w;
  });
  return { ...chunk, words };
}
