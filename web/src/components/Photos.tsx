import { useEffect, useId, useMemo, useState, type DragEvent } from 'react'
import { Button } from './ui'

export const MAX_PHOTOS = 4

/** Immagine del caso con ripiego se il file non è disponibile (es. modalità fixture). */
function CasePhoto({ url, name }: { url: string; name: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <div className="photo__placeholder">{name}</div>
  return (
    <img
      className="photo__img"
      src={url}
      alt={`Foto del pezzo: ${name}`}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  )
}

const fileName = (path: string) => path.split('/').pop() ?? path

export function PhotoGrid({ urls }: { urls: string[] }) {
  if (urls.length === 0) return <p className="muted">Nessuna foto per questa iterazione.</p>
  return (
    <div className="photos">
      {urls.map((url) => (
        <figure className="photo" key={url}>
          <a href={url} target="_blank" rel="noreferrer">
            <CasePhoto url={url} name={fileName(url)} />
          </a>
          <figcaption>{fileName(url)}</figcaption>
        </figure>
      ))}
    </div>
  )
}

/** Anteprime locali dei file scelti; gli object URL vengono rilasciati quando cambiano. */
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
    if (next.length > MAX_PHOTOS) setError(`Al massimo ${MAX_PHOTOS} foto: tenute le prime ${MAX_PHOTOS}.`)
    else if (images.length < incoming.length) setError('Solo immagini (JPG, PNG, WebP).')
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
        <strong>{reprint ? 'Foto della ristampa' : 'Foto del pezzo'}: trascina qui o scegli</strong>
        <span className="muted">
          1–{MAX_PHOTOS} foto: frontale, laterale a 45°, dall'alto e un primo piano del difetto. Luce diffusa, sfondo
          neutro.
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
              <img className="photo__img" src={url} alt={`Anteprima: ${file.name}`} />
              <figcaption>{file.name}</figcaption>
              <Button
                size="sm"
                variant="ghost"
                className="photo__remove"
                onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
              >
                Rimuovi
              </Button>
            </figure>
          ))}
        </div>
      )}
      <div className="field">
        <label htmlFor={noteId}>Nota per la diagnosi (facoltativa)</label>
        <textarea
          id={noteId}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Es. i ponti centrali cedono, fili tra i pilastri…"
        />
      </div>
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={busy} disabled={files.length === 0}>
          Carica {files.length > 0 ? `${files.length} foto` : 'le foto'}
        </Button>
      </div>
    </form>
  )
}
