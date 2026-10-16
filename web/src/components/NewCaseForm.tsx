import { useId, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router'
import { useCreateCase } from '../api/hooks'
import { Button, ErrorNotice } from './ui'

/** Nuovo caso dal progetto 3MF stampato: contiene modello e impostazioni effettive dello slicer. */
export function NewCaseForm() {
  const inputId = useId()
  const nameId = useId()
  const navigate = useNavigate()
  const create = useCreateCase()
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [over, setOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const pick = (f: File | undefined) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.3mf')) {
      setError('Serve un progetto .3mf di BambuStudio o OrcaSlicer (File → Salva progetto).')
      return
    }
    setError(null)
    setFile(f)
    if (!name) setName(f.name.replace(/\.3mf$/i, ''))
  }

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    setOver(false)
    pick(e.dataTransfer.files[0])
  }

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault()
        if (!file) return
        create.mutate({ project: file, name }, { onSuccess: (data) => navigate(`/cases/${data.id}`) })
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
        <strong>{file ? file.name : 'Progetto 3MF stampato'}</strong>
        <span className="muted">
          {file ? `${(file.size / 1024).toFixed(0)} kB · clic per cambiare` : 'Trascina qui o scegli il file'}
        </span>
        <input id={inputId} type="file" accept=".3mf" onChange={(e) => pick(e.target.files?.[0])} />
      </label>
      {error && (
        <p className="notice notice--warn" role="alert">
          {error}
        </p>
      )}
      <div className="field">
        <label htmlFor={nameId}>Nome del caso</label>
        <input
          id={nameId}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Es. staffa motore v2"
        />
      </div>
      <ErrorNotice error={create.error} title="Caso non creato" />
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={create.isPending} disabled={!file}>
          {create.isPending ? 'Slicing di riferimento…' : 'Crea il caso'}
        </Button>
      </div>
    </form>
  )
}
