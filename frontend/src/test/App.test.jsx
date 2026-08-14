import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import App from '../App.jsx'

function makeFile({ type = 'image/jpeg', size = 2048, name = 'cat.jpg' } = {}) {
  const file = new File(['bytes'], name, { type })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

const MEME = {
  id: 'abc-123',
  imageUrl: 'https://cdn.test/memes/abc-123.jpg',
  caption: 'I KNOCKED IT OVER / AND I FEEL NOTHING',
  topText: 'I KNOCKED IT OVER',
  bottomText: 'AND I FEEL NOTHING',
  labels: ['Cat', 'Pet'],
  captionSource: 'bedrock',
  createdAt: '2026-08-14T00:00:00Z',
}

/** Route each call by URL so tests describe behaviour, not call order. */
function mockApi({ gallery = [], presign, upload, generate } = {}) {
  fetch.mockImplementation((url, options) => {
    const href = String(url)

    if (href.includes('/gallery')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => ({ items: gallery }) })
    }
    if (href.includes('/uploads')) {
      return Promise.resolve(
        presign || {
          ok: true,
          status: 200,
          json: async () => ({ id: 'abc-123', key: 'uploads/abc-123.jpg', uploadUrl: 'https://s3.test/put' }),
        },
      )
    }
    if (options?.method === 'PUT') {
      return Promise.resolve(upload || { ok: true, status: 200 })
    }
    if (href.includes('/generate')) {
      return Promise.resolve(generate || { ok: true, status: 200, json: async () => MEME })
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  })
}

async function dropFile(file) {
  const input = screen.getByTestId('file-input')
  await userEvent.upload(input, file)
}

/** Let the initial gallery fetch settle so state updates stay inside act(). */
async function renderApp() {
  render(<App />)
  await waitFor(() => expect(screen.queryByText(/loading…/i)).not.toBeInTheDocument())
}

describe('landing view', () => {
  it('renders the title and upload zone', async () => {
    mockApi()
    await renderApp()

    expect(screen.getByText(/MEME ALCHEMIST/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload a photo/i })).toBeInTheDocument()
  })

  it('shows the three-step explainer', async () => {
    mockApi()
    await renderApp()

    const how = screen.getByLabelText('How it works')
    expect(within(how).getByText(/Drop a photo/i)).toBeInTheDocument()
    expect(within(how).getByText(/AI looks at it/i)).toBeInTheDocument()
    expect(within(how).getByText(/Meme comes out/i)).toBeInTheDocument()
  })

  it('names every AWS service used in the footer', async () => {
    mockApi()
    await renderApp()

    const footer = screen.getByText(/Built on AWS/i)
    for (const service of ['S3', 'Lambda', 'API Gateway', 'Rekognition', 'Bedrock', 'DynamoDB', 'CloudFront']) {
      expect(footer).toHaveTextContent(service)
    }
  })
})

describe('gallery', () => {
  it('renders memes returned by the API', async () => {
    mockApi({ gallery: [MEME, { ...MEME, id: 'def-456' }] })
    await renderApp()

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /view meme/i })).toHaveLength(2)
    })
  })

  it('shows an empty state when there are none', async () => {
    mockApi({ gallery: [] })
    await renderApp()
    expect(await screen.findByText(/No memes yet/i)).toBeInTheDocument()
  })

  it('survives a gallery failure without breaking the page', async () => {
    fetch.mockRejectedValue(new Error('network down'))
    await renderApp()

    expect(await screen.findByText(/No memes yet/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload a photo/i })).toBeInTheDocument()
  })

  it('opens a lightbox when a meme is clicked', async () => {
    mockApi({ gallery: [MEME] })
    await renderApp()

    const tile = await screen.findByRole('button', { name: /view meme/i })
    await userEvent.click(tile)

    expect(await screen.findByRole('dialog', { name: /meme preview/i })).toBeInTheDocument()
  })
})

describe('upload flow', () => {
  it('shows the staged loader while working', async () => {
    let resolveGenerate
    const pending = new Promise((resolve) => {
      resolveGenerate = resolve
    })
    mockApi({ generate: pending })

    await renderApp()
    await dropFile(makeFile())

    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(screen.getByText(/Looking at your photo/i)).toBeInTheDocument()

    resolveGenerate({ ok: true, status: 200, json: async () => MEME })
  })

  it('reveals the finished meme', async () => {
    mockApi()
    await renderApp()
    await dropFile(makeFile())

    const figure = await screen.findByRole('region', { name: /your finished meme/i })
    expect(within(figure).getByAltText(/I KNOCKED IT OVER/i)).toBeInTheDocument()
    expect(within(figure).getByRole('button', { name: /download/i })).toBeInTheDocument()
    expect(within(figure).getByRole('button', { name: /copy a shareable link/i })).toBeInTheDocument()
  })

  it('shows the labels Rekognition detected', async () => {
    mockApi()
    await renderApp()
    await dropFile(makeFile())

    await screen.findByRole('region', { name: /your finished meme/i })
    expect(screen.getByText('Cat')).toBeInTheDocument()
  })

  it('returns to the upload zone via "Make another"', async () => {
    mockApi()
    await renderApp()
    await dropFile(makeFile())

    await userEvent.click(await screen.findByRole('button', { name: /make another/i }))
    expect(screen.getByRole('button', { name: /upload a photo/i })).toBeInTheDocument()
  })

  it('notes when the caption came from the fallback library', async () => {
    mockApi({
      generate: { ok: true, status: 200, json: async () => ({ ...MEME, captionSource: 'fallback' }) },
    })
    await renderApp()
    await dropFile(makeFile())

    expect(await screen.findByText(/built-in joke library/i)).toBeInTheDocument()
  })

  it('does not show that note for a model-written caption', async () => {
    mockApi()
    await renderApp()
    await dropFile(makeFile())

    await screen.findByRole('region', { name: /your finished meme/i })
    expect(screen.queryByText(/built-in joke library/i)).not.toBeInTheDocument()
  })
})

describe('error states', () => {
  it('rejects an oversized file without calling the API', async () => {
    mockApi()
    await renderApp()
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    fetch.mockClear()

    await dropFile(makeFile({ size: 12 * 1024 * 1024 }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/under 8 MB/i)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows a server error and stays usable', async () => {
    mockApi({
      generate: {
        ok: false,
        status: 500,
        json: async () => ({ error: { code: 'INTERNAL_ERROR', message: 'Something went wrong brewing that meme.' } }),
      },
    })
    await renderApp()
    await dropFile(makeFile())

    expect(await screen.findByRole('alert')).toHaveTextContent(/went wrong brewing/i)
    expect(screen.getByRole('button', { name: /upload a photo/i })).toBeInTheDocument()
  })

  it('handles an S3 upload failure', async () => {
    mockApi({ upload: { ok: false, status: 403 } })
    await renderApp()
    await dropFile(makeFile())

    expect(await screen.findByRole('alert')).toHaveTextContent(/did not complete/i)
  })

  it('lets the user dismiss an error', async () => {
    mockApi()
    await renderApp()
    await dropFile(makeFile({ size: 12 * 1024 * 1024 }))

    await userEvent.click(await screen.findByRole('button', { name: /dismiss error/i }))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
})
