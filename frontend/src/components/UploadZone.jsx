import { useCallback, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ACCEPTED_TYPES } from '../api.js'

export default function UploadZone({ onFile, disabled }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const handleFiles = useCallback(
    (files) => {
      const file = files?.[0]
      if (file) onFile(file)
    },
    [onFile],
  )

  const onDrop = useCallback(
    (event) => {
      event.preventDefault()
      setDragging(false)
      if (!disabled) handleFiles(event.dataTransfer?.files)
    },
    [disabled, handleFiles],
  )

  const openPicker = () => {
    if (!disabled) inputRef.current?.click()
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="relative w-full"
    >
      {/* Glow that intensifies on hover and while dragging. */}
      <div
        className={`absolute -inset-px rounded-3xl bg-gradient-to-r from-fuchsia-500 via-violet-500 to-amber-400
                    opacity-0 blur-lg transition-opacity duration-300
                    ${dragging ? 'opacity-70' : 'group-hover:opacity-40'}`}
        aria-hidden="true"
      />

      <div
        role="button"
        tabIndex={0}
        aria-label="Upload a photo to turn into a meme"
        aria-disabled={disabled}
        data-dragging={dragging ? 'true' : 'false'}
        onClick={openPicker}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            openPicker()
          }
        }}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`group relative flex min-h-[19rem] cursor-pointer flex-col items-center justify-center
                    gap-4 rounded-3xl border-2 border-dashed p-10 text-center transition-all duration-300
                    ${dragging
                      ? 'scale-[1.015] border-fuchsia-400 bg-fuchsia-500/10'
                      : 'border-white/15 bg-white/[0.03] hover:border-fuchsia-400/50 hover:bg-white/[0.05]'}
                    ${disabled ? 'pointer-events-none opacity-50' : ''}`}
      >
        <motion.div
          animate={dragging ? { scale: 1.14, rotate: -6 } : { scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 320, damping: 18 }}
          className="text-6xl drop-shadow-[0_0_28px_rgba(217,70,239,0.45)]"
        >
          🧪
        </motion.div>

        <div>
          <p className="text-lg font-semibold text-white">
            {dragging ? 'Drop it in the cauldron' : 'Drag a photo here'}
          </p>
          <p className="mt-1 text-sm text-slate-400">
            or <span className="font-medium text-fuchsia-300 underline underline-offset-4">browse your files</span>
          </p>
        </div>

        <p className="text-xs text-slate-500">JPEG or PNG · up to 8 MB</p>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          className="hidden"
          data-testid="file-input"
          onChange={(event) => {
            handleFiles(event.target.files)
            event.target.value = '' // let the same file be picked twice
          }}
        />
      </div>
    </motion.div>
  )
}
