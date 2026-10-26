import type { ImagePayload } from "./types";

const SUPPORTED_IMAGE_TYPES = new Set(["image/png", "image/jpeg"]);

export function isSupportedImageFile(file: File) {
  return SUPPORTED_IMAGE_TYPES.has(file.type);
}
export async function fileToImagePayload(file: File): Promise<ImagePayload> {
  if (!isSupportedImageFile(file)) {
    throw new Error(`Unsupported image type: ${file.type || "unknown"}`);
  }

  if(file.size>5*1024*1024)throw new Error('单张图片请控制在 5 MiB 以内。');
  const dataUrl = await readFileAsDataUrl(file);
  const dimensions = await readImageDimensions(dataUrl);

  return {
    mimeType: file.type as ImagePayload["mimeType"],
    dataUrl,
    width: dimensions.width,
    height: dimensions.height,
    byteSize: file.size,
    name: file.name || "clipboard-image",
  };
}

export function describeImagePayload(image: ImagePayload) {
  const dimensions = image.width && image.height ? `${image.width}x${image.height}` : "unknown size";
  return dimensions;
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Could not read image as data URL."));
      }
    });
    reader.addEventListener("error", () => {
      reject(new Error("Could not read image file."));
    });
    reader.readAsDataURL(file);
  });
}

function readImageDimensions(dataUrl: string) {
  return new Promise<{ width: number; height: number }>((resolve, reject) => {
    const image = new Image();
    image.addEventListener("load", () => {
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    });
    image.addEventListener("error", () => {
      reject(new Error("Could not inspect image dimensions."));
    });
    image.src = dataUrl;
  });
}
