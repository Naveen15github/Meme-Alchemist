// API base is injected at build time by scripts/deploy.sh from the Terraform
// output, so the bundle always points at the API Gateway stage it was built for.
const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/$/, '')

export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png']

export class ApiError extends Error {
  constructor(message, code = 'UNKNOWN', status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** Client-side guard so obvious mistakes never cost a round trip. */
export function validateFile(file) {
  if (!file) return 'Please choose an image first.'
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return 'That file type is not supported. Please use a JPEG or PNG.'
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That image is ${(file.size / 1024 / 1024).toFixed(1)} MB. Please use one under 8 MB.`
  }
  if (file.size === 0) return 'That file looks empty.'
  return null
}

async function readError(response, fallbackMessage) {
  try {
    const data = await response.json()
    if (data?.error?.message) {
      return new ApiError(data.error.message, data.error.code, response.status)
    }
  } catch {
    // fall through to the generic message
  }
  return new ApiError(fallbackMessage, 'HTTP_' + response.status, response.status)
}

/** Step 1: ask the API where to put the file. */
export async function requestUploadUrl(file) {
  const response = await fetch(`${API_BASE}/uploads`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ contentType: file.type, size: file.size }),
  })
  if (!response.ok) throw await readError(response, 'Could not start the upload.')
  return response.json()
}

/** Step 2: PUT the bytes straight to S3, bypassing API Gateway size limits. */
export async function uploadToS3(uploadUrl, file) {
  const response = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'content-type': file.type },
    body: file,
  })
  if (!response.ok) {
    throw new ApiError('The upload did not complete. Please try again.', 'UPLOAD_FAILED', response.status)
  }
}

/** Step 3: Rekognition + Bedrock + Pillow, server side. */
export async function generateMeme(key) {
  const response = await fetch(`${API_BASE}/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ key }),
  })
  if (!response.ok) throw await readError(response, 'We could not brew that meme.')
  return response.json()
}

export async function fetchGallery(limit = 24) {
  const response = await fetch(`${API_BASE}/gallery?limit=${limit}`)
  if (!response.ok) throw await readError(response, 'Could not load the gallery.')
  const data = await response.json()
  return data.items || []
}
