import { useEffect, useId, useMemo, useState, type DragEvent } from 'react'
import { Button } from './ui'

export const MAX_PHOTOS = 4

/** Case image with a fallback when the file is unavailable (e.g. fixture mode). */
function CasePhoto({ url, name }: { url: string; name: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <div className="photo__placeholder">{name}</div>
  return (
    <img
      className="photo__img"
      src={url}
      alt={`Photo of the part: ${name}`}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

const fileName = (path: string) => path.split('/').pop() ?? path

/** Photos of an iteration; `captions` (same order) carry the detector's labels when it ran. */
export function PhotoGrid({ urls, captions }: { urls: string[]; captions?: (string | undefined)[] }) {
  if (urls.length === 0) return <p className="muted">No photos for this iteration.</p>
  return (
    <div className="photos">
      {urls.map((url, i) => (
        <figure className="photo" key={url}>
          <a href={url} target="_blank" rel="noreferrer">
            <CasePhoto url={url} name={fileName(url)} />
          </a>
          <figcaption>
            {fileName(url)}
            {captions?.[i] && <span className="photo__caption-model">{captions[i]}</span>}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}

/** Local previews of the chosen files; object URLs are released when they change. */
function usePreviews(files: File[]) {
  const previews = useMemo(() => files.map((f) => ({ file: f, url: URL.createObjectURL(f) })), [files])
  useEffect(() => () => previews.forEach((p) => URL.revokeObjectURL(p.url)), [previews])
  return previews
}

export function PhotoUploader({
  onSubmit,
  busy,
  reprint,
}: {
  onSubmit: (files: File[], note: string) => void
  busy: boolean
  reprint: boolean
}) {
  const inputId = useId()
  const noteId = useId()
  const [files, setFiles] = useState<File[]>([])
  const [note, setNote] = useState('')
  const [over, setOver] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const previews = usePreviews(files)

  const add = (incoming: FileList | null) => {
    if (!incoming) return
    const images = [...incoming].filter((f) => f.type.startsWith('image/'))
    const next = [...files, ...images]
    if (next.length > MAX_PHOTOS) setError(`At most ${MAX_PHOTOS} photos: kept the first ${MAX_PHOTOS}.`)
    else if (images.length < incoming.length) setError('Images only (JPG, PNG, WebP).')
    else setError(null)
    setFiles(next.slice(0, MAX_PHOTOS))
  }

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setOver(false)
    add(e.dataTransfer.files)
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        if (files.length) onSubmit(files, note)
      }}
    >
      <label
        htmlFor={inputId}
        className={over ? 'dropzone dropzone--over' : 'dropzone'}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
      >
        <strong>{reprint ? 'Photos of the reprint' : 'Photos of the part'}: drop here or browse</strong>
        <span className="muted">
          1–{MAX_PHOTOS} photos: front, side at 45°, top and a close-up of the defect. Diffuse light, neutral
          background.
        </span>
        <input
          id={inputId}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          onChange={(e) => {
            add(e.target.files)
            e.target.value = ''
          }}
        />
      </label>
      {error && (
        <p className="muted" role="status">
          {error}
        </p>
      )}
      {previews.length > 0 && (
        <div className="photos">
          {previews.map(({ file, url }) => (
            <figure className="photo" key={url}>
              <img className="photo__img" src={url} alt={`Preview: ${file.name}`} />
              <figcaption>{file.name}</figcaption>
              <Button
                size="sm"
                variant="ghost"
                className="photo__remove"
                onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
              >
                Remove
              </Button>
            </figure>
          ))}
        </div>
      )}
      <div className="field">
        <label htmlFor={noteId}>Note for the diagnosis (optional)</label>
        <textarea
          id={noteId}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="E.g. the middle bridges sag, strings between the pillars…"
        />
      </div>
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={busy} disabled={files.length === 0}>
          Upload {files.length > 0 ? `${files.length} ${files.length === 1 ? 'photo' : 'photos'}` : 'the photos'}
        </Button>
      </div>
    </form>
  )
}
