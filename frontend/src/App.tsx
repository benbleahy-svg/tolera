import { useEffect, useState } from 'react'
import './App.css'

interface Readiness {
  status: string
  db: string
  select_1?: number
  alembic_rev?: string | null
}

// M0.1 placeholder shell: proves the request travels React -> FastAPI -> Postgres.
// The real app shell, navigation, and i18n catalogs arrive in M0.4.
function App() {
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/readyz')
      .then((response) => {
        // fetch only rejects on network errors; a 503/4xx still resolves, so
        // guard before parsing or the error envelope renders as undefined fields.
        if (!response.ok) {
          throw new Error(`readyz ${response.status}`)
        }
        return response.json() as Promise<Readiness>
      })
      .then(setReadiness)
      .catch(() => setError('Backend nicht erreichbar'))
  }, [])

  return (
    <main className="shell">
      <h1>Tolera</h1>
      <p className="subtitle">Grundgerüst · M0.1</p>

      {error && <p className="status status--error">{error}</p>}
      {!error && !readiness && <p className="status">Verbinde mit dem Backend …</p>}
      {readiness && (
        <dl className="status">
          <dt>Status</dt>
          <dd>{readiness.status}</dd>
          <dt>Datenbank</dt>
          <dd>{readiness.db}</dd>
          <dt>Migration</dt>
          <dd>{readiness.alembic_rev ?? '—'}</dd>
        </dl>
      )}
    </main>
  )
}

export default App
