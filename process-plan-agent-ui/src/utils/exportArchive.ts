export type ArchiveTextFile = {
  name: string
  content: string
}

export function textFile(value: unknown) {
  if (typeof value === 'string') return value
  return `${JSON.stringify(value, null, 2)}\n`
}

function crc32(bytes: Uint8Array) {
  let crc = 0xffffffff
  for (let i = 0; i < bytes.length; i += 1) {
    crc ^= bytes[i] ?? 0
    for (let j = 0; j < 8; j += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1))
    }
  }
  return (crc ^ 0xffffffff) >>> 0
}

function uint16(value: number) {
  return [value & 0xff, (value >>> 8) & 0xff]
}

function uint32(value: number) {
  return [value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff]
}

export function createZipBlob(files: ArchiveTextFile[]) {
  const encoder = new TextEncoder()
  const chunks: Uint8Array[] = []
  const centralChunks: Uint8Array[] = []
  let offset = 0

  files.forEach((file) => {
    const nameBytes = encoder.encode(file.name)
    const contentBytes = encoder.encode(file.content)
    const crc = crc32(contentBytes)
    const localHeader = new Uint8Array([
      ...uint32(0x04034b50),
      ...uint16(20),
      ...uint16(0x0800),
      ...uint16(0),
      ...uint16(0),
      ...uint16(0),
      ...uint32(crc),
      ...uint32(contentBytes.length),
      ...uint32(contentBytes.length),
      ...uint16(nameBytes.length),
      ...uint16(0),
    ])
    chunks.push(localHeader, nameBytes, contentBytes)

    const centralHeader = new Uint8Array([
      ...uint32(0x02014b50),
      ...uint16(20),
      ...uint16(20),
      ...uint16(0x0800),
      ...uint16(0),
      ...uint16(0),
      ...uint16(0),
      ...uint32(crc),
      ...uint32(contentBytes.length),
      ...uint32(contentBytes.length),
      ...uint16(nameBytes.length),
      ...uint16(0),
      ...uint16(0),
      ...uint16(0),
      ...uint16(0),
      ...uint32(0),
      ...uint32(offset),
    ])
    centralChunks.push(centralHeader, nameBytes)
    offset += localHeader.length + nameBytes.length + contentBytes.length
  })

  const centralSize = centralChunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const endRecord = new Uint8Array([
    ...uint32(0x06054b50),
    ...uint16(0),
    ...uint16(0),
    ...uint16(files.length),
    ...uint16(files.length),
    ...uint32(centralSize),
    ...uint32(offset),
    ...uint16(0),
  ])
  const blobParts = [...chunks, ...centralChunks, endRecord].map((chunk) =>
    chunk.buffer.slice(chunk.byteOffset, chunk.byteOffset + chunk.byteLength) as ArrayBuffer,
  )
  return new Blob(blobParts, { type: 'application/zip' })
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
