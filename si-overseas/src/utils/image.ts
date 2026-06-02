/**
 * Client-side image compression using Canvas API.
 * Compresses to JPEG with configured max dimension and quality.
 */

export interface CompressOptions {
  maxSide?: number;
  quality?: number;
}

export async function compressImage(
  file: File,
  options: CompressOptions = {},
): Promise<File> {
  const { maxSide = 1600, quality = 0.8 } = options;

  // Skip compression for non-image files
  if (!file.type.startsWith('image/')) return file;

  // Skip compression for already-small images
  if (file.size < 100 * 1024) return file;

  try {
    const bitmap = await createImageBitmap(file);

    let { width, height } = bitmap;
    if (width > maxSide || height > maxSide) {
      const scale = Math.min(maxSide / width, maxSide / height);
      width = Math.round(width * scale);
      height = Math.round(height * scale);
    }

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext('2d');
    if (!ctx) return file;

    ctx.drawImage(bitmap, 0, 0, width, height);
    bitmap.close();

    const blob = await new Promise<Blob | null>(resolve =>
      canvas.toBlob(resolve, 'image/jpeg', quality),
    );

    if (!blob) return file;

    // Preserve original filename but change extension to .jpg
    const name = file.name.replace(/\.[^.]+$/, '') + '.jpg';
    return new File([blob], name, { type: 'image/jpeg' });
  } catch {
    // Fallback to original file on any error
    return file;
  }
}
