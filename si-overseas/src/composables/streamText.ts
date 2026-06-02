export interface StreamTextOptions {
  chunkDelayMs?: number;
  onChunk?: (partial: string) => void;
}

export function splitTextChunks(text: string): string[] {
  const words = text.split(/(\s+)/);
  const chunks: string[] = [];
  let buffer = '';

  for (const word of words) {
    buffer += word;
    if (buffer.length >= 12 || /\n$/.test(word)) {
      chunks.push(buffer);
      buffer = '';
    }
  }

  if (buffer) chunks.push(buffer);
  return chunks.length ? chunks : [text];
}

export async function streamText(
  text: string,
  onUpdate: (partial: string) => void,
  options: StreamTextOptions = {},
): Promise<void> {
  const delayMs = options.chunkDelayMs ?? 22;
  const chunks = splitTextChunks(text);
  let partial = '';

  for (const chunk of chunks) {
    partial += chunk;
    onUpdate(partial);
    options.onChunk?.(partial);
    await new Promise<void>(resolve => {
      window.setTimeout(resolve, delayMs);
    });
  }
}
