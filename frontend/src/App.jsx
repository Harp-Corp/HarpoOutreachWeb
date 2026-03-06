import { useState, useEffect } from 'react'

const API = '/api'

function App() {
  // ─── Navigation ─────────────────────────────────────────
  const [section, setSection] = useState('search')   // search | campaign | social | settings
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  // Multi-select state for company search
  const [selIndustries, setSelIndustries] = useState([])
  const [selRegions, setSelRegions] = useState([])
  const [selSizes, setSelSizes] = useState([])

  const industries = [
    { value: 'K - Finanzdienstleistungen', label: 'Finanzdienstleistungen' },
    { value: 'Q - Gesundheitswesen', label: 'Gesundheitswesen' },
    { value: 'J - Information und Kommunikation', label: 'ICT' },
    { value: 'D - Energieversorgung', label: 'Energie' },
    { value: 'C - Verarbeitendes Gewerbe', label: 'Fertigung' },
    { value: 'H - Verkehr und Lagerei', label: 'Transport' },
    { value: 'M - Freiberufliche Dienstleistungen', label: 'Professional Services' },
  ]
  const regions = [
    { value: 'DACH', label: 'DACH' },
    { value: 'UK', label: 'UK' },
    { value: 'Nordics', label: 'Nordics' },
    { value: 'Benelux', label: 'Benelux' },
    { value: 'France', label: 'France' },
    { value: 'Baltics', label: 'Baltics' },
    { value: 'Iberia', label: 'Iberia' },
  ]
  const sizes = [
    { value: '0-200 Mitarbeiter', label: '0–200' },
    { value: '201-5.000 Mitarbeiter', label: '201–5.000' },
    { value: '5.001-500.000 Mitarbeiter', label: '5.001+' },
  ]

  const fetchJson = async (url, opts = {}) => {
    const resp = await fetch(url, opts)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${resp.status}`)
    }
    return resp.json()
  }

  useEffect(() => { loadDashboard(); loadAuthStatus() }, [])
  useEffect(() => {
    if (section === 'search' || section === 'campaign') { loadCompanies(); loadLeads() }
    else if (section === 'social') loadPosts()
  }, [section])

  const showSuccess = (msg) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(''), 4000) }
  const loadDashboard = async () => { try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {} }
  const loadCompanies = async () => { try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {} }
  const loadLeads = async () => { try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {} }
  const loadPosts = async () => { try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {} }
  const loadAuthStatus = async () => { try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {} }

  const toggle = (arr, setArr, val) => {
    setArr(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])
  }

  // ─── Company Search (clears previous results) ───────────
  const findCompanies = async () => {
    if (selIndustries.length === 0 || selRegions.length === 0) {
      setError('Bitte mindestens eine Branche und eine Region auswählen.'); return
    }
    setLoading(true); setError('')
    try {
      // Clear previous results
      await fetchJson(`${API}/data/companies`, { method: 'DELETE' })
      await fetchJson(`${API}/data/leads`, { method: 'DELETE' })
      // Search
      const params = new URLSearchParams()
      selIndustries.forEach(v => params.append('industries', v))
      selRegions.forEach(v => params.append('regions', v))
      selSizes.forEach(v => params.append('sizes', v))
      const r = await fetchJson(`${API}/prospecting/find-companies?${params.toString()}`, { method: 'POST' })
      showSuccess(`${r.total || 0} neue Unternehmen gefunden`)
      await loadCompanies()
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const findContacts = async (companyId) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST' })
      showSuccess(`${r.total || 0} Kontakte gefunden`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const findAllContacts = async () => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/find-contacts-all`, { method: 'POST' })
      showSuccess(`${r.total_new || 0} neue Kontakte gefunden`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const verifyEmail = async (leadId) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/verify-email/${leadId}`, { method: 'POST' })
      showSuccess(`E-Mail verifiziert: ${r.data?.email || 'OK'}`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const verifyAllEmails = async () => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/verify-all`, { method: 'POST' })
      let msg = `${r.verified || 0} von ${r.total || 0} E-Mails verifiziert`
      if (r.errors && r.errors.length > 0) msg += ` (${r.errors.length} Fehler)`
      showSuccess(msg)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftEmail = async (leadId) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/email/draft/${leadId}`, { method: 'POST' })
      showSuccess('E-Mail-Entwurf erstellt')
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftAllEmails = async () => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/email/draft-all`, { method: 'POST' })
      showSuccess(`${r.created || 0} Entwürfe erstellt, ${r.failed || 0} fehlgeschlagen`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const approveEmail = async (leadId) => {
    try { await fetchJson(`${API}/email/approve/${leadId}`, { method: 'POST' }); await loadLeads() } catch (e) { setError(e.message) }
  }
  const approveAllEmails = async () => {
    try { const r = await fetchJson(`${API}/email/approve-all`, { method: 'POST' }); showSuccess(`${r.approved || 0} E-Mails genehmigt`); await loadLeads() } catch (e) { setError(e.message) }
  }

  const sendEmail = async (leadId) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/email/send/${leadId}`, { method: 'POST' })
      showSuccess('E-Mail gesendet')
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const sendAllEmails = async () => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/email/send-all`, { method: 'POST' })
      showSuccess(`${r.sent || 0} gesendet, ${r.failed || 0} fehlgeschlagen`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const generatePost = async (topic, platform) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST' })
      showSuccess('Social Post generiert')
      await loadPosts()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const deletePost = async (postId) => {
    try { await fetchJson(`${API}/data/social-posts/${postId}`, { method: 'DELETE' }); await loadPosts() } catch (e) { setError(e.message) }
  }

  const exportCSV = (type) => {
    const url = type === 'companies' ? `${API}/data/companies/export` : `${API}/data/leads/export`
    window.open(url, '_blank')
  }

  // ─── Helpers ────────────────────────────────────────────
  const statusBadge = (status) => {
    const colors = {
      'Identified': 'badge-gray', 'Contacted': 'badge-blue', 'Email Drafted': 'badge-yellow',
      'Email Approved': 'badge-blue', 'Email Sent': 'badge-green', 'Replied': 'badge-green',
      'Follow-Up Drafted': 'badge-yellow', 'Follow-Up Sent': 'badge-green',
      'Do Not Contact': 'badge-red', 'Closed': 'badge-gray',
    }
    return <span className={`badge ${colors[status] || 'badge-gray'}`}>{status}</span>
  }

  const unverifiedLeads = leads.filter(l => !l.email_verified && l.email)
  const companiesWithoutContacts = companies.filter(c => !leads.some(l => l.company === c.name))

  const CheckboxGroup = ({ label, items, selected, onChange }) => (
    <div className="form-group">
      <label>{label}</label>
      <div className="checkbox-group">
        {items.map(item => (
          <label key={item.value} className={`checkbox-item ${selected.includes(item.value) ? 'checked' : ''}`}>
            <input type="checkbox" checked={selected.includes(item.value)} onChange={() => onChange(item.value)} />
            <span>{item.label}</span>
          </label>
        ))}
      </div>
    </div>
  )

  // ─── Search Flow: search bar with steps ─────────────────
  const SearchCompaniesPanel = () => (
    <div className="card">
      <h2>1. Unternehmen suchen</h2>
      <CheckboxGroup label="Branchen" items={industries} selected={selIndustries} onChange={v => toggle(selIndustries, setSelIndustries, v)} />
      <CheckboxGroup label="Regionen" items={regions} selected={selRegions} onChange={v => toggle(selRegions, setSelRegions, v)} />
      <CheckboxGroup label="Größe (optional)" items={sizes} selected={selSizes} onChange={v => toggle(selSizes, setSelSizes, v)} />
      <div style={{display:'flex',gap:'0.5rem',marginTop:'1rem',alignItems:'center'}}>
        <button className="btn btn-primary" disabled={loading || selIndustries.length === 0 || selRegions.length === 0} onClick={findCompanies}>
          Neue Suche starten ({selIndustries.length} × {selRegions.length})
        </button>
        {(selIndustries.length > 0 || selRegions.length > 0 || selSizes.length > 0) && (
          <button className="btn btn-secondary" onClick={() => { setSelIndustries([]); setSelRegions([]); setSelSizes([]) }}>Zurücksetzen</button>
        )}
      </div>
      <p style={{fontSize:'0.75rem',color:'#94a3b8',marginTop:'0.5rem'}}>Vorherige Ergebnisse werden bei neuer Suche gelöscht.</p>
    </div>
  )

  const CompaniesTable = ({ showContactButton }) => (
    <div className="card">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem'}}>
        <h2>Unternehmen ({companies.length})</h2>
        <div style={{display:'flex',gap:'0.5rem'}}>
          {companies.length > 0 && <button className="btn btn-secondary" onClick={() => exportCSV('companies')}>CSV Export</button>}
          {showContactButton && companiesWithoutContacts.length > 0 && (
            <button className="btn btn-primary" disabled={loading} onClick={findAllContacts}>
              Alle Kontakte suchen ({companiesWithoutContacts.length})
            </button>
          )}
        </div>
      </div>
      <table>
        <thead><tr><th>Name</th><th>Branche</th><th>Land</th><th>Mitarbeiter</th>{showContactButton && <th>Aktionen</th>}</tr></thead>
        <tbody>
          {companies.map(c => (
            <tr key={c.id}>
              <td><strong>{c.name}</strong><br/><span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{c.website}</span></td>
              <td>{c.industry}</td>
              <td>{c.country}</td>
              <td>{c.employee_count?.toLocaleString()}</td>
              {showContactButton && (
                <td><button className="btn btn-secondary" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte finden</button></td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {companies.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Unternehmen. Starten Sie eine Suche.</p>}
    </div>
  )

  const LeadsTable = ({ showVerify, showDraft, showEmail }) => (
    <div className="card">
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'1rem'}}>
        <h2>Kontakte ({leads.length})</h2>
        <div style={{display:'flex',gap:'0.5rem'}}>
          {leads.length > 0 && <button className="btn btn-secondary" onClick={() => exportCSV('leads')}>CSV Export</button>}
        </div>
      </div>
      {leads.length > 0 && (
        <div style={{display:'flex',gap:'0.5rem',flexWrap:'wrap',alignItems:'center',marginBottom:'1rem',padding:'0.75rem',background:'#f8fafc',borderRadius:'8px'}}>
          <strong style={{marginRight:'auto',fontSize:'0.8125rem'}}>Batch:</strong>
          {showVerify && unverifiedLeads.length > 0 && (
            <button className="btn btn-secondary" disabled={loading} onClick={verifyAllEmails}>Alle verifizieren ({unverifiedLeads.length})</button>
          )}
          {showDraft && (
            <button className="btn btn-secondary" disabled={loading} onClick={draftAllEmails}>Alle Drafts erstellen</button>
          )}
          {showDraft && (
            <button className="btn btn-secondary" disabled={loading} onClick={approveAllEmails}>Alle genehmigen</button>
          )}
          {showEmail && authStatus?.authenticated && (
            <button className="btn btn-primary" disabled={loading} onClick={sendAllEmails}>Alle senden</button>
          )}
        </div>
      )}
      <table>
        <thead><tr><th>Name</th><th>Unternehmen</th><th>E-Mail</th><th>Status</th><th>Aktionen</th></tr></thead>
        <tbody>
          {leads.map(l => (
            <tr key={l.id}>
              <td><strong>{l.name}</strong><br/><span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{l.title}</span></td>
              <td>{l.company}</td>
              <td>
                {l.email || '—'}
                {l.email_verified && <span style={{color:'#22c55e',marginLeft:'4px'}} title="Verifiziert">✓</span>}
              </td>
              <td>{statusBadge(l.status)}</td>
              <td style={{display:'flex',gap:'0.25rem',flexWrap:'wrap'}}>
                {showVerify && l.email && !l.email_verified && (
                  <button className="btn btn-secondary" disabled={loading} onClick={() => verifyEmail(l.id)}>Verify</button>
                )}
                {showDraft && !l.drafted_email && l.email && (
                  <button className="btn btn-secondary" disabled={loading} onClick={() => draftEmail(l.id)}>Draft</button>
                )}
                {showDraft && l.drafted_email && !l.drafted_email.is_approved && (
                  <button className="btn btn-secondary" onClick={() => approveEmail(l.id)}>Approve</button>
                )}
                {showEmail && l.drafted_email?.is_approved && l.status !== 'Email Sent' && authStatus?.authenticated && (
                  <button className="btn btn-primary" disabled={loading} onClick={() => sendEmail(l.id)}>Senden</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {leads.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Kontakte.</p>}
    </div>
  )

  // ─── Menu items ─────────────────────────────────────────
  const menuItems = [
    { id: 'search', icon: '🔍', label: 'Suche & Adressbuch', desc: 'Unternehmen, Kontakte, Verifikation, Export' },
    { id: 'campaign', icon: '📧', label: 'E-Mail-Kampagne', desc: 'Suche, Kontakte, Verifikation, Drafts, Versand' },
    { id: 'social', icon: '💬', label: 'LinkedIn-Kampagne', desc: 'Social Posts generieren' },
    { id: 'settings', icon: '⚙️', label: 'Einstellungen', desc: 'Auth, API-Keys, Konfiguration' },
  ]

  return (
    <div className="layout">
      {/* ─── Sidebar ─────────────────────────────── */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1>Harpo</h1>
          <span className="sidebar-subtitle">Outreach</span>
        </div>
        <nav className="sidebar-nav">
          {menuItems.map(m => (
            <button
              key={m.id}
              className={`sidebar-item ${section === m.id ? 'active' : ''}`}
              onClick={() => setSection(m.id)}
            >
              <span className="sidebar-icon">{m.icon}</span>
              <div>
                <div className="sidebar-label">{m.label}</div>
                <div className="sidebar-desc">{m.desc}</div>
              </div>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          {stats && (
            <div className="sidebar-stats">
              <div><strong>{stats.total_leads}</strong> Leads</div>
              <div><strong>{stats.emails_sent}</strong> gesendet</div>
              <div><strong>{stats.conversion_rate}%</strong> Rate</div>
            </div>
          )}
          <div className="sidebar-auth">
            {authStatus?.authenticated
              ? <span style={{color:'#22c55e',fontSize:'0.75rem'}}>● {authStatus.email}</span>
              : <a href="/api/auth/google/login" style={{fontSize:'0.75rem',color:'#f59e0b'}}>● Google verbinden</a>
            }
          </div>
        </div>
      </aside>

      {/* ─── Main Content ────────────────────────── */}
      <main className="main-content">
        {error && <div className="error">{error} <button onClick={() => setError('')}>×</button></div>}
        {successMsg && <div className="success">{successMsg}</div>}
        {loading && <div className="loading">Wird verarbeitet...</div>}

        {/* ─── Suche & Adressbuch ──────────────── */}
        {section === 'search' && (
          <div>
            <h1 className="page-title">Suche & Adressbuch</h1>
            <p className="page-desc">Unternehmen suchen → Kontakte finden → Verifizieren → CSV exportieren</p>
            <SearchCompaniesPanel />
            {companies.length > 0 && <CompaniesTable showContactButton={true} />}
            {leads.length > 0 && <LeadsTable showVerify={true} showDraft={false} showEmail={false} />}
          </div>
        )}

        {/* ─── E-Mail-Kampagne ─────────────────── */}
        {section === 'campaign' && (
          <div>
            <h1 className="page-title">E-Mail-Kampagne</h1>
            <p className="page-desc">Unternehmen suchen → Kontakte finden → Verifizieren → Personalisierte E-Mails → Versand</p>
            <SearchCompaniesPanel />
            {companies.length > 0 && <CompaniesTable showContactButton={true} />}
            {leads.length > 0 && <LeadsTable showVerify={true} showDraft={true} showEmail={true} />}
            {!authStatus?.authenticated && leads.length > 0 && (
              <div className="card" style={{background:'#fef3c7',borderLeft:'4px solid #f59e0b'}}>
                <p style={{color:'#92400e',fontSize:'0.875rem'}}>
                  Zum E-Mail-Versand bitte zuerst <a href="/api/auth/google/login">mit Google verbinden</a>.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ─── LinkedIn-Kampagne ───────────────── */}
        {section === 'social' && (
          <div>
            <h1 className="page-title">LinkedIn-Kampagne</h1>
            <p className="page-desc">Social Posts für LinkedIn und Twitter/X generieren</p>
            <div className="card">
              <h2>Social Post generieren</h2>
              <div style={{display:'flex',gap:'0.5rem',alignItems:'end',flexWrap:'wrap'}}>
                <div className="form-group" style={{flex:1,minWidth:'150px'}}>
                  <label>Thema</label>
                  <select id="postTopic">
                    <option value="Regulatory Update">Regulatory Update</option>
                    <option value="Compliance Tip">Compliance Tip</option>
                    <option value="Industry Insight">Industry Insight</option>
                    <option value="Product Feature">Product Feature</option>
                    <option value="Thought Leadership">Thought Leadership</option>
                    <option value="Case Study">Case Study</option>
                  </select>
                </div>
                <div className="form-group" style={{flex:1,minWidth:'150px'}}>
                  <label>Plattform</label>
                  <select id="postPlatform">
                    <option value="LinkedIn">LinkedIn</option>
                    <option value="Twitter/X">Twitter/X</option>
                  </select>
                </div>
                <button className="btn btn-primary" disabled={loading} onClick={() => {
                  generatePost(document.getElementById('postTopic').value, document.getElementById('postPlatform').value)
                }}>Generieren</button>
              </div>
            </div>
            <div className="card">
              <h2>Posts ({posts.length})</h2>
              {posts.map(p => (
                <div key={p.id} style={{borderBottom:'1px solid #e2e8f0',padding:'1rem 0'}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    <span className="badge badge-blue">{p.platform}</span>
                    <div style={{display:'flex',gap:'0.5rem',alignItems:'center'}}>
                      <span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{p.created_date?.split('T')[0]}</span>
                      <button className="btn btn-secondary" style={{padding:'0.2rem 0.5rem',fontSize:'0.7rem'}} onClick={() => {
                        navigator.clipboard.writeText(p.content); showSuccess('Kopiert')
                      }}>Kopieren</button>
                      <button className="btn btn-secondary" style={{padding:'0.2rem 0.5rem',fontSize:'0.7rem',color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>
                    </div>
                  </div>
                  <p style={{marginTop:'0.5rem',whiteSpace:'pre-wrap',fontSize:'0.875rem',lineHeight:'1.6'}}>{p.content}</p>
                </div>
              ))}
              {posts.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Posts.</p>}
            </div>
          </div>
        )}

        {/* ─── Einstellungen ───────────────────── */}
        {section === 'settings' && (
          <div>
            <h1 className="page-title">Einstellungen</h1>
            <div className="card">
              <h2>Google Auth</h2>
              {authStatus?.authenticated
                ? <div><span style={{color:'#22c55e'}}>Verbunden als {authStatus.email}</span>
                    <button className="btn btn-secondary" style={{marginLeft:'0.5rem'}} onClick={async () => {
                      await fetchJson(`${API}/auth/logout`, { method: 'POST' }); loadAuthStatus()
                    }}>Abmelden</button>
                  </div>
                : <div>
                    <a href="/api/auth/google/login" className="btn btn-primary">Mit Google verbinden</a>
                    {authStatus?.token_expired && <span style={{color:'#f59e0b',marginLeft:'0.5rem',fontSize:'0.8rem'}}>Token abgelaufen</span>}
                  </div>
              }
            </div>
            {stats && (
              <div className="card">
                <h2>Dashboard</h2>
                <div className="status-bar">
                  <div className="stat"><div className="stat-value">{stats.total_leads}</div><div className="stat-label">Leads</div></div>
                  <div className="stat"><div className="stat-value">{stats.emails_sent}</div><div className="stat-label">Gesendet</div></div>
                  <div className="stat"><div className="stat-value">{stats.replies_received}</div><div className="stat-label">Antworten</div></div>
                  <div className="stat"><div className="stat-value">{stats.conversion_rate}%</div><div className="stat-label">Rate</div></div>
                </div>
                {Object.keys(stats.leads_by_status || {}).length > 0 && (
                  <div style={{marginTop:'1rem'}}>
                    <h3 style={{fontSize:'0.875rem',fontWeight:600,marginBottom:'0.5rem'}}>Status-Verteilung</h3>
                    {Object.entries(stats.leads_by_status).map(([k, v]) => (
                      <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'0.25rem 0',fontSize:'0.875rem'}}>
                        <span>{k}</span><strong>{v}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
