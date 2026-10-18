import { useId, useState, type DragEvent } from 'react'
import { useNavigate } from 'react-router'
import { useCreateCase } from '../api/hooks'
import { Button, ErrorNotice } from './ui'

/** New case from the printed 3MF project: it holds the model and the actual slicer settings. */
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
      setError('A BambuStudio or OrcaSlicer .3mf project is required (File → Save project).')
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
        <strong>{file ? file.name : 'Printed 3MF project'}</strong>
        <span className="muted">
          {file ? `${(file.size / 1024).toFixed(0)} kB · click to change` : 'Drop it here or browse'}
        </span>
        <input id={inputId} type="file" accept=".3mf" onChange={(e) => pick(e.target.files?.[0])} />
      </label>
      {error && (
        <p className="notice notice--warn" role="alert">
          {error}
        </p>
      )}
      <div className="field">
        <label htmlFor={nameId}>Case name</label>
        <input
          id={nameId}
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="E.g. motor bracket v2"
        />
      </div>
      <ErrorNotice error={create.error} title="Case not created" />
      <div className="btn-row">
        <Button type="submit" variant="primary" busy={create.isPending} disabled={!file}>
          {create.isPending ? 'Reference slice…' : 'Create the case'}
        </Button>
      </div>
    </form>
  )
}
