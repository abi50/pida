import { useState, useEffect, useRef } from 'react'
import './App.css'

type Tab = 'timeline' | 'alerts' | 'settings'

interface TimelineEvent {
  id: string
  source: string
  category: string
  action: string
  subject: string
  target: string
  detail: Record<string, unknown>
  severity: string
  timestamp: string
}

interface AlertItem {
  id: string
  severity: string
  message: string
  source: string
  detail: Record<string, unknown>
  acknowledged: boolean
  snoozed_until: string | null
  created_at: string
}

const API = '/api'

function severityColor(sev: string): string {
  switch (sev) {
    case 'CRITICAL': return '#dc2626'
    case 'HIGH': return '#ea580c'
    case 'MEDIUM': return '#ca8a04'
    case 'LOW': return '#2563eb'
    default: return '#6b7280'
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString()
}

function TimelinePage() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)

  const fetchEvents = async () => {
    const res = await fetch(`${API}/timeline?limit=100`)
    const data = await res.json()
    setEvents(data.events)
    setLoading(false)
  }

  useEffect(() => { fetchEvents() }, [])

  if (loading) return <p className="loading">Loading timeline...</p>

  return (
    <div className="page">
      <div className="page-header">
        <h2>Timeline</h2>
        <button className="btn" onClick={fetchEvents}>Refresh</button>
      </div>
      {events.length === 0 ? (
        <p className="empty">No events yet. Activity will appear here.</p>
      ) : (
        <div className="timeline">
          {events.map(ev => (
            <div key={ev.id} className="card">
              <div className="card-header">
                <span className="badge" style={{ background: severityColor(ev.severity) }}>
                  {ev.severity}
                </span>
                <span className="action">{ev.action.replace(/_/g, ' ')}</span>
                <span className="time">{formatTime(ev.timestamp)}</span>
              </div>
              <div className="card-body">
                {ev.target && <div className="target">Target: <code>{ev.target}</code></div>}
                {ev.subject && <div className="subject">Subject: {ev.subject}</div>}
                <div className="meta">Source: {ev.source} | Category: {ev.category}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [loading, setLoading] = useState(true)

  const fetchAlerts = async () => {
    const res = await fetch(`${API}/alerts?limit=100`)
    const data = await res.json()
    setAlerts(data.alerts)
    setLoading(false)
  }

  useEffect(() => { fetchAlerts() }, [])

  const ack = async (id: string) => {
    await fetch(`${API}/alerts/${id}/acknowledge`, { method: 'POST' })
    fetchAlerts()
  }

  const snooze = async (id: string) => {
    await fetch(`${API}/alerts/${id}/snooze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hours: 1 }),
    })
    fetchAlerts()
  }

  if (loading) return <p className="loading">Loading alerts...</p>

  return (
    <div className="page">
      <div className="page-header">
        <h2>Alerts</h2>
        <button className="btn" onClick={fetchAlerts}>Refresh</button>
      </div>
      {alerts.length === 0 ? (
        <p className="empty">No alerts. All clear!</p>
      ) : (
        <div className="timeline">
          {alerts.map(a => (
            <div key={a.id} className={`card ${a.acknowledged ? 'acked' : ''}`}>
              <div className="card-header">
                <span className="badge" style={{ background: severityColor(a.severity) }}>
                  {a.severity}
                </span>
                <span className="action">{a.message}</span>
                <span className="time">{formatTime(a.created_at)}</span>
              </div>
              <div className="card-body">
                <div className="meta">Source: {a.source}</div>
                <div className="card-actions">
                  {!a.acknowledged && (
                    <button className="btn btn-sm" onClick={() => ack(a.id)}>Acknowledge</button>
                  )}
                  <button className="btn btn-sm btn-outline" onClick={() => snooze(a.id)}>
                    Snooze 1hr
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SettingsPage() {
  const [folders, setFolders] = useState('')
  const [windows, setWindows] = useState('')
  const [saved, setSaved] = useState('')

  useEffect(() => {
    fetch(`${API}/config/folders`).then(r => r.json()).then(d => {
      setFolders(JSON.stringify(d.folders, null, 2))
    })
    fetch(`${API}/config/away-windows`).then(r => r.json()).then(d => {
      setWindows(JSON.stringify(d.windows, null, 2))
    })
  }, [])

  const saveFolders = async () => {
    try {
      const parsed = JSON.parse(folders)
      await fetch(`${API}/config/folders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      })
      setSaved('Folders saved!')
      setTimeout(() => setSaved(''), 2000)
    } catch { setSaved('Invalid JSON') }
  }

  const saveWindows = async () => {
    try {
      const parsed = JSON.parse(windows)
      await fetch(`${API}/config/away-windows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      })
      setSaved('Away windows saved!')
      setTimeout(() => setSaved(''), 2000)
    } catch { setSaved('Invalid JSON') }
  }

  return (
    <div className="page">
      <h2>Settings</h2>
      {saved && <div className="toast">{saved}</div>}

      <div className="settings-section">
        <h3>Monitored Folders</h3>
        <textarea value={folders} onChange={e => setFolders(e.target.value)} rows={8} />
        <button className="btn" onClick={saveFolders}>Save Folders</button>
      </div>

      <div className="settings-section">
        <h3>Away Windows</h3>
        <textarea value={windows} onChange={e => setWindows(e.target.value)} rows={8} />
        <button className="btn" onClick={saveWindows}>Save Windows</button>
      </div>
    </div>
  )
}

function App() {
  const [tab, setTab] = useState<Tab>('timeline')
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/events`)
    wsRef.current = ws
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    return () => ws.close()
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1>PIDA</h1>
        <span className="subtitle">Personal Intrusion Detection Agent</span>
        <span className={`ws-status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? 'Live' : 'Offline'}
        </span>
      </header>
      <nav className="nav">
        <button className={tab === 'timeline' ? 'active' : ''} onClick={() => setTab('timeline')}>
          Timeline
        </button>
        <button className={tab === 'alerts' ? 'active' : ''} onClick={() => setTab('alerts')}>
          Alerts
        </button>
        <button className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}>
          Settings
        </button>
      </nav>
      <main>
        {tab === 'timeline' && <TimelinePage />}
        {tab === 'alerts' && <AlertsPage />}
        {tab === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}

export default App
