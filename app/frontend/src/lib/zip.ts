// Reads one file of a zip archive in the browser (stored or deflated, as zipfile writes them), without a library:
// enough to look into an exported database (database.json) before uploading it.

const END_OF_DIRECTORY = 0x06054b50;
const DIRECTORY_ENTRY = 0x02014b50;
const LOCAL_HEADER = 0x04034b50;

/** The bytes of the file `name` of the zip `file`; null if it is no zip or has no such file. */
export async function readZipEntry(file: Blob, name: string): Promise<Uint8Array | null> {
  // The end of the central directory is in the last 64 KiB (22 bytes plus a comment of at most 65535).
  const tailStart = Math.max(0, file.size - 65557);
  const tail = new DataView(await file.slice(tailStart).arrayBuffer());
  let end = -1;
  for (let offset = tail.byteLength - 22; offset >= 0; offset--) {
    if (tail.getUint32(offset, true) === END_OF_DIRECTORY) {
      end = offset;
      break;
    }
  }
  if (end < 0) return null;
  const directorySize = tail.getUint32(end + 12, true);
  const directoryOffset = tail.getUint32(end + 16, true);
  const directory = new DataView(await file.slice(directoryOffset, directoryOffset + directorySize).arrayBuffer());
  const decoder = new TextDecoder();
  for (let offset = 0; offset + 46 <= directory.byteLength; ) {
    if (directory.getUint32(offset, true) !== DIRECTORY_ENTRY) return null;
    const method = directory.getUint16(offset + 10, true);
    const compressedSize = directory.getUint32(offset + 20, true);
    const nameLength = directory.getUint16(offset + 28, true);
    const extraLength = directory.getUint16(offset + 30, true);
    const commentLength = directory.getUint16(offset + 32, true);
    const localOffset = directory.getUint32(offset + 42, true);
    const entryName = decoder.decode(new Uint8Array(directory.buffer, directory.byteOffset + offset + 46, nameLength));
    if (entryName === name) return readLocal(file, localOffset, compressedSize, method);
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return null;
}

async function readLocal(file: Blob, offset: number, size: number, method: number): Promise<Uint8Array | null> {
  const header = new DataView(await file.slice(offset, offset + 30).arrayBuffer());
  if (header.getUint32(0, true) !== LOCAL_HEADER) return null;
  const start = offset + 30 + header.getUint16(26, true) + header.getUint16(28, true);
  const data = file.slice(start, start + size);
  if (method === 0) return new Uint8Array(await data.arrayBuffer());
  if (method !== 8) return null;
  const inflated = data.stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(inflated).arrayBuffer());
}
