import { useState, useEffect } from 'react'

const API = '/api'

function App() {
  const [tab, setTab] = useState('dashboard')
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetchJson = async (url, opts = {}) => {
    const resp = await fetch(url, opts)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    return resp.json()
  }

  useEffect(() => {
    loadDashboard()
    loadAuthStatus()
  }, [])

  useEffect(() => {
    if (tab === 'companies') loadCompanies()
    else if (tab === 'leads') loadLeads()
    else if (tab === 'social') loadPosts()
    else if (tab === 'dashboard') loadDashboard()
  }, [tab])

  const loadDashboard = async () => {
    try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {}
  }
  const loadCompanies = async () => {
    try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {}
  }
  const loadLeads = async () => {
    try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {}
  }
  const loadPosts = async () => {
    try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {}
  }
  const loadAuthStatus = async () => {
    try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {}
  }

  const findCompanies = async (industry, region) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/find-companies?industry=${encodeURIComponent(industry)}&region=${encodeURIComponent(region)}`, { method: 'POST' })
      await loadCompanies()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const findContacts = async (companyId) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST' })
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftEmail = async (leadId) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/email/draft/${leadId}`, { method: 'POST' })
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const approveEmail = async (leadId) => {
    try {
      await fetchJson(`${API}/email/approve/${leadId}`, { method: 'POST' })
      await loadLeads()
    } catch (e) { setError(e.message) }
  }

  const sendEmail = async (leadId) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/email/send/${leadId}`, { method: 'POST' })
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const statusBadge = (status) => {
    const colors = {
      'Identified': 'badge-gray', 'Contacted': 'badge-blue', 'Email Drafted': 'badge-yellow',
      'Email Approved': 'badge-blue', 'Email Sent': 'badge-green', 'Replied': 'badge-green',
    }
    return <span className={`badge ${colors[status] || 'badge-gray'}`}>{status}</span>
  }

  return (
    <div className="app">
      <h1>HarpoOutreach Web</h1>
      <h2>B2B Compliance Outreach Platform</h2>

      <nav>
        {['dashboard', 'companies', 'leads', 'social', 'settings'].map(t => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t === 'dashboard' ? 'Dashboard' : t === 'companies' ? 'Unternehmen' : t === 'leads' ? 'Kontakte' : t === 'social' ? 'Social Posts' : 'Einstellungen'}
          </button>
        ))}
      </nav>

      {error && <div className="error">{error} <button onClick={() => setError('')}>×</button></div>}
      {loading && <div className="loading">⏳ Wird geladen...</div>}

      {tab === 'dashboard' && stats && (
        <div>
          <div className="status-bar">
            <div className="stat card"><div className="stat-value">{stats.total_leads}</div><div className="stat-label">Leads</div></div>
            <div className="stat card"><div className="stat-value">{stats.emails_sent}</div><div className="stat-label">Emails gesendet</div></div>
            <div className="stat card"><div className="stat-value">{stats.replies_received}</div><div className="stat-label">Antworten</div></div>
            <div className="stat card"><div className="stat-value">{stats.conversion_rate}%</div><div className="stat-label">Conversion Rate</div></div>
          </div>
          <div className="card">
            <h2>Status-Verteilung</h2>
            {Object.entries(stats.leads_by_status || {}).map(([k, v]) => (
              <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'0.25rem 0'}}>
                <span>{k}</span><strong>{v}</strong>
              </div>
            ))}
          </div>
          <div style={{marginTop:'0.5rem',fontSize:'0.75rem',color:'#94a3b8'}}>
            Auth: {authStatus?.authenticated ? `✅ ${authStatus.email}` : '❌ Nicht verbunden'}
          </div>
        </div>
      )}

      {tab === 'companies' && (
        <div>
          <div className="card" style={{display:'flex',gap:'0.5rem',alignItems:'end'}}>
            <div className="form-group" style={{flex:1}}>
              <label>Branche</label>
              <select id="industry">
                <option value="K - Finanzdienstleistungen">Finanzdienstleistungen</option>
                <option value="Q - Gesundheitswesen">Gesundheitswesen</option>
                <option value="J - Information und Kommunikation">ICT</option>
                <option value="D - Energieversorgung">Energie</option>
                <option value="C - Verarbeitendes Gewerbe">Fertigung</option>
                <option value="H - Verkehr und Lagerei">Transport</option>
                <option value="M - Freiberufliche Dienstleistungen">Professional Services</option>
              </select>
            </div>
            <div className="form-group" style={{flex:1}}>
              <label>Region</label>
              <select id="region">
                <option value="DACH">DACH</option>
                <option value="UK">UK</option>
                <option value="Nordics">Nordics</option>
                <option value="Benelux">Benelux</option>
                <option value="France">France</option>
                <option value="Baltics">Baltics</option>
                <option value="Iberia">Iberia</option>
              </select>
            </div>
            <button className="btn btn-primary" onClick={() => {
              const ind = document.getElementById('industry').value
              const reg = document.getElementById('region').value
              findCompanies(ind, reg)
            }}>Suchen</button>
          </div>
          <div className="card">
            <table>
              <thead><tr><th>Name</th><th>Branche</th><th>Land</th><th>Mitarbeiter</th><th>Aktionen</th></tr></thead>
              <tbody>
                {companies.map(c => (
                  <tr key={c.id}>
                    <td><strong>{c.name}</strong><br/><span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{c.website}</span></td>
                    <td>{c.industry}</td>
                    <td>{c.country}</td>
                    <td>{c.employee_count?.toLocaleString()}</td>
                    <td><button className="btn btn-secondary" onClick={() => findContacts(c.id)}>Kontakte finden</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {companies.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Unternehmen. Starten Sie eine Suche.</p>}
          </div>
        </div>
      )}

      {tab === 'leads' && (
        <div className="card">
          <div style={{display:'flex',justifyContent:'space-between',marginBottom:'1rem'}}>
            <h2>Kontakte ({leads.length})</h2>
          </div>
          <table>
            <thead><tr><th>Name</th><th>Unternehmen</th><th>E-Mail</th><th>Status</th><th>Aktionen</th></tr></thead>
            <tbody>
              {leads.map(l => (
                <tr key={l.id}>
                  <td><strong>{l.name}</strong><br/><span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{l.title}</span></td>
                  <td>{l.company}</td>
                  <td>{l.email || '—'} {l.email_verified && '✅'}</td>
                  <td>{statusBadge(l.status)}</td>
                  <td style={{display:'flex',gap:'0.25rem',flexWrap:'wrap'}}>
                    {!l.drafted_email && l.email && <button className="btn btn-secondary" onClick={() => draftEmail(l.id)}>Draft</button>}
                    {l.drafted_email && !l.drafted_email.is_approved && <button className="btn btn-secondary" onClick={() => approveEmail(l.id)}>Approve</button>}
                    {l.drafted_email?.is_approved && l.status !== 'Email Sent' && <button className="btn btn-primary" onClick={() => sendEmail(l.id)}>Senden</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {leads.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Kontakte.</p>}
        </div>
      )}

      {tab === 'social' && (
        <div className="card">
          <h2>Social Posts</h2>
          {posts.map(p => (
            <div key={p.id} style={{borderBottom:'1px solid #f1f5f9',padding:'1rem 0'}}>
              <div style={{display:'flex',justifyContent:'space-between'}}>
                <span className="badge badge-blue">{p.platform}</span>
                <span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{p.created_date?.split('T')[0]}</span>
              </div>
              <p style={{marginTop:'0.5rem',whiteSpace:'pre-wrap',fontSize:'0.875rem'}}>{p.content?.substring(0, 300)}{p.content?.length > 300 ? '...' : ''}</p>
            </div>
          ))}
          {posts.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Social Posts.</p>}
        </div>
      )}

      {tab === 'settings' && (
        <div className="card">
          <h2>Einstellungen</h2>
          <p style={{color:'#94a3b8',fontSize:'0.875rem'}}>Konfiguration ueber API: PUT /api/data/settings</p>
          <div style={{marginTop:'1rem'}}>
            <div className="form-group"><label>Google Auth</label>
              {authStatus?.authenticated
                ? <p>✅ Verbunden als {authStatus.email}</p>
                : <a href="/api/auth/google/login" className="btn btn-primary">Mit Google verbinden</a>
              }
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
