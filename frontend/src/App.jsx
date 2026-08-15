import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'

import Background from './components/Background.jsx'
import Gallery from './components/Gallery.jsx'
import HowItWorks from './components/HowItWorks.jsx'
import MemeReveal from './components/MemeReveal.jsx'
import StageLoader from './components/StageLoader.jsx'
import UploadZone from './components/UploadZone.jsx'
import {
  deleteMeme,
  fetchGallery,
  generateMeme,
  ownedMemeIds,
  rememberDeleteToken,
  requestUploadUrl,
  uploadToS3,
  validateFile,
} from './api.js'

const VIEW = { IDLE: 'idle', WORKING: 'working', DONE: 'done' }

export default function App() {
  const [view, setView] = useState(VIEW.IDLE)
  const [stage, setStage] = useState(0)
  const [preview, setPreview] = useState(null)
  const [meme, setMeme] = useState(null)
  const [error, setError] = useState(null)

  const [memes, setMemes] = useState([])
  const [galleryLoading, setGalleryLoading] = useState(true)
  const [ownedIds, setOwnedIds] = useState(() => ownedMemeIds())

  // Tracked so we can revoke the object URL and cancel the stage timer.
  const previewUrlRef = useRef(null)
  const renderTimerRef = useRef(null)

  const loadGallery = useCallback(async () => {
    try {
      setMemes(await fetchGallery())
    } catch {
      // A gallery that fails to load must not break the page; the upload flow
      // is the important half.
      setMemes([])
    } finally {
      setGalleryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadGallery()
  }, [loadGallery])

  useEffect(
    () => () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
      if (renderTimerRef.current) clearTimeout(renderTimerRef.current)
    },
    [],
  )

  const handleDelete = useCallback(async (target) => {
    // Optimistic: the tile animates out immediately, and comes back if the
    // request fails.
    const previous = memes
    setMemes((current) => current.filter((item) => item.id !== target.id))

    try {
      await deleteMeme(target.id)
      setOwnedIds(ownedMemeIds())

      // If the reveal happens to be showing the meme we just deleted, drop
      // back to the upload zone rather than leaving a dead image on screen.
      setMeme((current) => {
        if (current && current.id === target.id) {
          setView(VIEW.IDLE)
          return null
        }
        return current
      })
    } catch (err) {
      setMemes(previous)
      setError(err?.message || 'Could not delete that meme.')
    }
  }, [memes])

  const reset = useCallback(() => {
    if (renderTimerRef.current) clearTimeout(renderTimerRef.current)
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
      previewUrlRef.current = null
    }
    setPreview(null)
    setMeme(null)
    setError(null)
    setStage(0)
    setView(VIEW.IDLE)
  }, [])

  const handleFile = useCallback(
    async (file) => {
      const validationError = validateFile(file)
      if (validationError) {
        setError(validationError)
        return
      }

      setError(null)
      setMeme(null)
      setStage(0)
      setView(VIEW.WORKING)

      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current)
      const objectUrl = URL.createObjectURL(file)
      previewUrlRef.current = objectUrl
      setPreview(objectUrl)

      try {
        // Stage 0: real upload work.
        const { uploadUrl, key } = await requestUploadUrl(file)
        await uploadToS3(uploadUrl, file)

        // Stage 1: /generate is genuinely in flight from here.
        setStage(1)
        // The server does captioning then rendering inside one call, so we
        // advance to "stamping" once captioning has had time to finish.
        renderTimerRef.current = setTimeout(() => setStage(2), 2600)

        const result = await generateMeme(key)

        // The delete token comes back exactly once - keep it before anything
        // else can throw, or this meme becomes undeletable.
        if (result.deleteToken) {
          rememberDeleteToken(result.id, result.deleteToken)
          setOwnedIds(ownedMemeIds())
        }

        clearTimeout(renderTimerRef.current)
        setStage(2)
        setMeme(result)
        setView(VIEW.DONE)
        loadGallery()
      } catch (err) {
        clearTimeout(renderTimerRef.current)
        setError(err?.message || 'Something went wrong. Please try again.')
        setView(VIEW.IDLE)
      }
    },
    [loadGallery],
  )

  return (
    <div className="relative min-h-screen">
      <Background />

      <main className="mx-auto w-full max-w-5xl px-4 pb-24 pt-14 sm:px-6 sm:pt-20">
        <motion.header
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="text-center"
        >
          <span className="glass inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-xs font-medium text-slate-300">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Powered by Amazon Rekognition + Amazon Bedrock
          </span>

          <h1 className="mt-6 font-display text-5xl leading-none tracking-tight sm:text-7xl">
            <span className="accent-text">MEME ALCHEMIST</span>
          </h1>

          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-slate-400">
            Drop in any photo. The AI works out what it's looking at, writes the joke,
            and hands you back a meme.
          </p>
        </motion.header>

        <section className="mx-auto mt-12 w-full max-w-2xl">
          <AnimatePresence mode="wait">
            {view === VIEW.IDLE && (
              <motion.div key="idle" exit={{ opacity: 0, scale: 0.97 }}>
                <UploadZone onFile={handleFile} disabled={false} />
              </motion.div>
            )}

            {view === VIEW.WORKING && (
              <motion.div key="working" exit={{ opacity: 0, scale: 0.97 }}>
                <StageLoader activeIndex={stage} preview={preview} />
              </motion.div>
            )}

            {view === VIEW.DONE && meme && (
              <motion.div key="done">
                <MemeReveal meme={meme} onReset={reset} />
              </motion.div>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {error && (
              <motion.div
                role="alert"
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mt-5 flex items-start gap-3 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4"
              >
                <span className="text-lg leading-none">⚠️</span>
                <div className="flex-1">
                  <p className="text-sm text-rose-200">{error}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  aria-label="Dismiss error"
                  className="text-rose-300/70 hover:text-rose-200"
                >
                  ✕
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </section>

        {view === VIEW.IDLE && <HowItWorks />}

        <section className="mt-20">
          <div className="mb-6 flex items-baseline justify-between gap-4">
            <h2 className="font-display text-2xl tracking-wide text-white">FRESH FROM THE LAB</h2>
            <span className="text-xs text-slate-500">
              {galleryLoading ? 'loading…' : `${memes.length} meme${memes.length === 1 ? '' : 's'}`}
            </span>
          </div>
          <Gallery
            memes={memes}
            loading={galleryLoading}
            ownedIds={ownedIds}
            onDelete={handleDelete}
          />
        </section>

        <footer className="mt-20 border-t border-white/5 pt-8 text-center text-xs text-slate-600">
          <p>
            Built on AWS — S3 · Lambda · API Gateway · Rekognition · Bedrock (Nova) · DynamoDB · CloudFront
          </p>
        </footer>
      </main>
    </div>
  )
}
