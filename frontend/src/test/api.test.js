import { describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  deleteMeme,
  fetchGallery,
  forgetDeleteToken,
  generateMeme,
  getDeleteToken,
  ownedMemeIds,
  rememberDeleteToken,
  requestUploadUrl,
  uploadToS3,
  validateFile,
} from '../api.js'

function makeFile({ type = 'image/jpeg', size = 1024, name = 'photo.jpg' } = {}) {
  const file = new File(['x'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return { ok, status, json: async () => body }
}

describe('validateFile', () => {
  it('accepts a normal jpeg', () => {
    expect(validateFile(makeFile())).toBeNull()
  })

  it('accepts png', () => {
    expect(validateFile(makeFile({ type: 'image/png' }))).toBeNull()
  })

  it('rejects a missing file', () => {
    expect(validateFile(null)).toMatch(/choose an image/i)
  })

  it('rejects an unsupported type', () => {
    expect(validateFile(makeFile({ type: 'image/gif' }))).toMatch(/not supported/i)
  })

  it('rejects files over 8 MB', () => {
    expect(validateFile(makeFile({ size: 9 * 1024 * 1024 }))).toMatch(/under 8 MB/i)
  })

  it('accepts a file at exactly the limit', () => {
    expect(validateFile(makeFile({ size: 8 * 1024 * 1024 }))).toBeNull()
  })

  it('rejects an empty file', () => {
    expect(validateFile(makeFile({ size: 0 }))).toMatch(/empty/i)
  })
})

describe('requestUploadUrl', () => {
  it('returns the presigned payload', async () => {
    fetch.mockResolvedValue(jsonResponse({ uploadUrl: 'https://s3/put', key: 'uploads/a.jpg', id: 'a' }))
    await expect(requestUploadUrl(makeFile())).resolves.toMatchObject({ key: 'uploads/a.jpg' })
  })

  it('surfaces the server error message', async () => {
    fetch.mockResolvedValue(
      jsonResponse({ error: { code: 'UNSUPPORTED_TYPE', message: 'Please upload a JPEG or PNG image.' } },
        { ok: false, status: 415 }),
    )
    await expect(requestUploadUrl(makeFile())).rejects.toThrow(/JPEG or PNG/)
  })

  it('falls back to a generic message when the body is not JSON', async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error('nope') } })
    await expect(requestUploadUrl(makeFile())).rejects.toBeInstanceOf(ApiError)
  })
})

describe('uploadToS3', () => {
  it('PUTs the file with its content type', async () => {
    fetch.mockResolvedValue({ ok: true, status: 200 })
    await uploadToS3('https://s3/put', makeFile())

    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('https://s3/put')
    expect(options.method).toBe('PUT')
    expect(options.headers['content-type']).toBe('image/jpeg')
  })

  it('throws when S3 rejects the upload', async () => {
    fetch.mockResolvedValue({ ok: false, status: 403 })
    await expect(uploadToS3('https://s3/put', makeFile())).rejects.toThrow(/did not complete/i)
  })
})

describe('generateMeme', () => {
  it('returns the meme payload', async () => {
    fetch.mockResolvedValue(jsonResponse({ id: 'abc', imageUrl: '/memes/abc.jpg', caption: 'A / B' }))
    await expect(generateMeme('uploads/abc.jpg')).resolves.toMatchObject({ id: 'abc' })
  })

  it('sends the key in the body', async () => {
    fetch.mockResolvedValue(jsonResponse({ id: 'abc' }))
    await generateMeme('uploads/abc.jpg')
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ key: 'uploads/abc.jpg' })
  })

  it('propagates a friendly error', async () => {
    fetch.mockResolvedValue(
      jsonResponse({ error: { code: 'FILE_TOO_LARGE', message: 'Too big.' } }, { ok: false, status: 413 }),
    )
    await expect(generateMeme('uploads/abc.jpg')).rejects.toThrow('Too big.')
  })
})

describe('fetchGallery', () => {
  it('returns items', async () => {
    fetch.mockResolvedValue(jsonResponse({ items: [{ id: '1' }], count: 1 }))
    await expect(fetchGallery()).resolves.toHaveLength(1)
  })

  it('returns an empty array when items is absent', async () => {
    fetch.mockResolvedValue(jsonResponse({}))
    await expect(fetchGallery()).resolves.toEqual([])
  })

  it('throws on a failed request', async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) })
    await expect(fetchGallery()).rejects.toBeInstanceOf(ApiError)
  })
})

describe('delete tokens', () => {
  it('remembers and returns a token', () => {
    rememberDeleteToken('abc', 'tok-1')
    expect(getDeleteToken('abc')).toBe('tok-1')
  })

  it('returns null for an unknown meme', () => {
    expect(getDeleteToken('nope')).toBeNull()
  })

  it('ignores empty ids or tokens', () => {
    rememberDeleteToken('', 'tok')
    rememberDeleteToken('id', '')
    expect(ownedMemeIds().size).toBe(0)
  })

  it('tracks every owned id', () => {
    rememberDeleteToken('a', 't1')
    rememberDeleteToken('b', 't2')
    expect(ownedMemeIds()).toEqual(new Set(['a', 'b']))
  })

  it('forgets a token', () => {
    rememberDeleteToken('a', 't1')
    forgetDeleteToken('a')
    expect(getDeleteToken('a')).toBeNull()
  })

  it('survives corrupted storage', () => {
    localStorage.setItem('meme-alchemist:delete-tokens', 'not json{')
    expect(ownedMemeIds().size).toBe(0)
    expect(getDeleteToken('a')).toBeNull()
  })
})

describe('deleteMeme', () => {
  it('sends the token in the header', async () => {
    rememberDeleteToken('abc', 'tok-1')
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 'abc', deleted: true }) })

    await deleteMeme('abc')

    const [url, options] = fetch.mock.calls[0]
    expect(url).toMatch(/\/memes\/abc$/)
    expect(options.method).toBe('DELETE')
    expect(options.headers['x-delete-token']).toBe('tok-1')
  })

  it('forgets the token after a successful delete', async () => {
    rememberDeleteToken('abc', 'tok-1')
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: 'abc', deleted: true }) })

    await deleteMeme('abc')
    expect(getDeleteToken('abc')).toBeNull()
  })

  it('refuses without a token, without calling the API', async () => {
    await expect(deleteMeme('abc')).rejects.toThrow(/only delete memes you created/i)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('treats 404 as success so the UI converges', async () => {
    rememberDeleteToken('abc', 'tok-1')
    fetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) })

    await expect(deleteMeme('abc')).resolves.toMatchObject({ deleted: true })
    expect(getDeleteToken('abc')).toBeNull()
  })

  it('keeps the token when the server rejects it', async () => {
    rememberDeleteToken('abc', 'tok-1')
    fetch.mockResolvedValue({
      ok: false, status: 403,
      json: async () => ({ error: { code: 'FORBIDDEN', message: 'Not yours.' } }),
    })

    await expect(deleteMeme('abc')).rejects.toThrow('Not yours.')
    expect(getDeleteToken('abc')).toBe('tok-1')
  })
})
