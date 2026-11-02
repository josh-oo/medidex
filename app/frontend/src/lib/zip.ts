// Reads one file of a zip archive in the browser (stored or deflated, as zipfile writes them), without a library:
// enough to look into an exported database (database.json) before uploading it. Archives over 4 GiB (ZIP64, as
// zipfile writes them for a large database) are read too.

const END_OF_DIRECTORY = 0x06054b50;
const ZIP64_END_OF_DIRECTORY = 0x06064b50;
const ZIP64_LOCATOR = 0x07064b50;
const DIRECTORY_ENTRY = 0x02014b50;
const LOCAL_HEADER = 0x04034b50;
const ZIP64_EXTRA = 0x0001;
// A 32-bit field of this value says that the value is in the ZIP64 record (or extra field) instead.
const ZIP64_MARK = 0xffffffff;

/** The bytes of the file `name` of the zip `file`; null if it is no zip or has no such file. */
export async function readZipEntry(file: Blob, name: string): Promise<Uint8Array | null> {
  // The end of the central directory is in the last 64 KiB (22 bytes plus a comment of at most 65535), the ZIP64
  // locator in the 20 bytes before it.
  const tailStart = Math.max(0, file.size - 65557 - 20);
  const tail = new DataView(await file.slice(tailStart).arrayBuffer());
  let end = -1;
  for (let offset = tail.byteLength - 22; offset >= 0; offset--) {
    if (tail.getUint32(offset, true) === END_OF_DIRECTORY) {
      end = offset;
      break;
    }
  }
  if (end < 0) return null;
  let directorySize = tail.getUint32(end + 12, true);
  let directoryOffset = tail.getUint32(end + 16, true);
  if (directorySize === ZIP64_MARK || directoryOffset === ZIP64_MARK) {
    const zip64 = await readZip64End(file, tail, end);
    if (zip64 === null) return null;
    ({ directorySize, directoryOffset } = zip64);
  }
  const directory = new DataView(await file.slice(directoryOffset, directoryOffset + directorySize).arrayBuffer());
  const decoder = new TextDecoder();
  for (let offset = 0; offset + 46 <= directory.byteLength; ) {
    if (directory.getUint32(offset, true) !== DIRECTORY_ENTRY) return null;
    const method = directory.getUint16(offset + 10, true);
    let compressedSize = directory.getUint32(offset + 20, true);
    const uncompressedSize = directory.getUint32(offset + 24, true);
    const nameLength = directory.getUint16(offset + 28, true);
    const extraLength = directory.getUint16(offset + 30, true);
    const commentLength = directory.getUint16(offset + 32, true);
    let localOffset = directory.getUint32(offset + 42, true);
    const entryName = decoder.decode(new Uint8Array(directory.buffer, directory.byteOffset + offset + 46, nameLength));
    if (entryName === name) {
      // The ZIP64 extra field holds, in this order, the values whose fields are marked: the uncompressed size, the
      // compressed size and the offset of the local header.
      const extra = findExtra(directory, offset + 46 + nameLength, extraLength, ZIP64_EXTRA);
      if (extra !== null) {
        let position = extra;
        if (uncompressedSize === ZIP64_MARK) position += 8;
        if (compressedSize === ZIP64_MARK) {
          compressedSize = Number(directory.getBigUint64(position, true));
          position += 8;
        }
        if (localOffset === ZIP64_MARK) localOffset = Number(directory.getBigUint64(position, true));
      }
      return readLocal(file, localOffset, compressedSize, method);
    }
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return null;
}

/** The size and offset of the central directory from the ZIP64 end of central directory record. */
async function readZip64End(file: Blob, tail: DataView, end: number): Promise<{ directorySize: number; directoryOffset: number } | null> {
  const locator = end - 20;
  if (locator < 0 || tail.getUint32(locator, true) !== ZIP64_LOCATOR) return null;
  const recordOffset = Number(tail.getBigUint64(locator + 8, true));
  const record = new DataView(await file.slice(recordOffset, recordOffset + 56).arrayBuffer());
  if (record.byteLength < 56 || record.getUint32(0, true) !== ZIP64_END_OF_DIRECTORY) return null;
  return { directorySize: Number(record.getBigUint64(40, true)), directoryOffset: Number(record.getBigUint64(48, true)) };
}

/** Where the data of the extra field `id` starts in the extra fields of an entry, null if it has none. */
function findExtra(view: DataView, start: number, length: number, id: number): number | null {
  for (let offset = start; offset + 4 <= start + length; ) {
    const size = view.getUint16(offset + 2, true);
    if (view.getUint16(offset, true) === id) return offset + 4;
    offset += 4 + size;
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
