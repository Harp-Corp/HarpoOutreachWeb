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
  const [successMsg, setSuccessMsg] = useState('')

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

  const showSuccess = (msg) => {
    setSuccessMsg(msg)
    setTimeout(() => setSuccessMsg(''), 4000)
  }

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

  // ─── Company Search ──────────────────────────────────────
  const findCompanies = async (industry, region) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/find-companies?industry=${encodeURIComponent(industry)}&region=${encodeURIComponent(region)}`, { method: 'POST' })
      showSuccess(`${r.total || 0} neue Unternehmen gefunden`)
      await loadCompanies()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  // ─── Contact Search ──────────────────────────────────────
  const findContacts = async (companyId) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST' })
      showSuccess(`${r.total || 0} Kontakte gefunden`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  // ─── Email Verification ──────────────────────────────────
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
      showSuccess(`${r.verified || 0} von ${r.total || 0} E-Mails verifiziert`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  // ─── Email Drafting ──────────────────────────────────────
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
      showSuccess(`${r.created || 0} Entwuerfe erstellt, ${r.failed || 0} fehlgeschlagen`)
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

  const approveAllEmails = async () => {
    try {
      const r = await fetchJson(`${API}/email/approve-all`, { method: 'POST' })
      showSuccess(`${r.approved || 0} E-Mails genehmigt`)
      await loadLeads()
    } catch (e) { setError(e.message) }
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
      showSuccess(`${r.sent || 0} gesendet, ${r.failed || 0} fehlgeschlagen, ${r.remaining || 0} verbleibend`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  // ─── Social Posts ────────────────────────────────────────
  const generatePost = async (topic, platform) => {
    setLoading(true); setError('')
    try {
      const r = await fetchJson(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST' })
      showSuccess('Social Post generiert')
      await loadPosts()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const deletePost = async (postId) => {
    try {
      await fetchJson(`${API}/data/social-posts/${postId}`, { method: 'DELETE' })
      await loadPosts()
    } catch (e) { setError(e.message) }
  }

  // ─── Helpers ─────────────────────────────────────────────
  const statusBadge = (status) => {
    const colors = {
      'Identified': 'badge-gray', 'Contacted': 'badge-blue', 'Email Drafted': 'badge-yellow',
      'Email Approved': 'badge-blue', 'Email Sent': 'badge-green', 'Replied': 'badge-green',
      'Follow-Up Drafted': 'badge-yellow', 'Follow-Up Sent': 'badge-green',
      'Do Not Contact': 'badge-red', 'Closed': 'badge-gray',
    }
    return <span className={`badge ${colors[status] || 'badge-gray'}`}>{status}</span>
  }

  const leadsWithEmail = leads.filter(l => l.email)
  const leadsWithDraft = leads.filter(l => l.drafted_email)
  const unverifiedLeads = leads.filter(l => !l.email_verified && l.email)

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
      {successMsg && <div className="success">{successMsg}</div>}
      {loading && <div className="loading">Wird verarbeitet...</div>}

      {/* ─── Dashboard ──────────────────────────────── */}
      {tab === 'dashboard' && (
        <div>
          {stats && (
            <div className="status-bar">
              <div className="stat card"><div className="stat-value">{stats.total_leads}</div><div className="stat-label">Leads</div></div>
              <div className="stat card"><div className="stat-value">{stats.emails_sent}</div><div className="stat-label">Emails gesendet</div></div>
              <div className="stat card"><div className="stat-value">{stats.replies_received}</div><div className="stat-label">Antworten</div></div>
              <div className="stat card"><div className="stat-value">{stats.conversion_rate}%</div><div className="stat-label">Conversion Rate</div></div>
            </div>
          )}
          {stats && Object.keys(stats.leads_by_status || {}).length > 0 && (
            <div className="card">
              <h2>Status-Verteilung</h2>
              {Object.entries(stats.leads_by_status).map(([k, v]) => (
                <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'0.25rem 0'}}>
                  <span>{k}</span><strong>{v}</strong>
                </div>
              ))}
            </div>
          )}
          <div style={{marginTop:'0.5rem',fontSize:'0.75rem',color:'#94a3b8'}}>
            Auth: {authStatus?.authenticated ? `Verbunden: ${authStatus.email}` : 'Nicht verbunden'}
          </div>
        </div>
      )}

      {/* ─── Companies ──────────────────────────────── */}
      {tab === 'companies' && (
        <div>
          <div className="card" style={{display:'flex',gap:'0.5rem',alignItems:'end',flexWrap:'wrap'}}>
            <div className="form-group" style={{flex:1,minWidth:'150px'}}>
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
            <div className="form-group" style={{flex:1,minWidth:'150px'}}>
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
            <button className="btn btn-primary" disabled={loading} onClick={() => {
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
                    <td><button className="btn btn-secondary" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte finden</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {companies.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Unternehmen. Starten Sie eine Suche.</p>}
          </div>
        </div>
      )}

      {/* ─── Leads ──────────────────────────────────── */}
      {tab === 'leads' && (
        <div>
          {leads.length > 0 && (
            <div className="card" style={{display:'flex',gap:'0.5rem',flexWrap:'wrap',alignItems:'center'}}>
              <strong style={{marginRight:'auto'}}>Batch-Aktionen:</strong>
              {unverifiedLeads.length > 0 && (
                <button className="btn btn-secondary" disabled={loading} onClick={verifyAllEmails}>
                  Alle verifizieren ({unverifiedLeads.length})
                </button>
              )}
              <button className="btn btn-secondary" disabled={loading} onClick={draftAllEmails}>
                Alle Drafts erstellen
              </button>
              <button className="btn btn-secondary" disabled={loading} onClick={approveAllEmails}>
                Alle genehmigen
              </button>
              {authStatus?.authenticated && (
                <button className="btn btn-primary" disabled={loading} onClick={sendAllEmails}>
                  Alle senden
                </button>
              )}
            </div>
          )}
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
                    <td>
                      {l.email || '—'}
                      {l.email_verified && <span style={{color:'#22c55e',marginLeft:'4px'}} title="Verifiziert">✓</span>}
                    </td>
                    <td>{statusBadge(l.status)}</td>
                    <td style={{display:'flex',gap:'0.25rem',flexWrap:'wrap'}}>
                      {l.email && !l.email_verified && (
                        <button className="btn btn-secondary" disabled={loading} onClick={() => verifyEmail(l.id)} title="E-Mail verifizieren">Verify</button>
                      )}
                      {!l.drafted_email && l.email && (
                        <button className="btn btn-secondary" disabled={loading} onClick={() => draftEmail(l.id)}>Draft</button>
                      )}
                      {l.drafted_email && !l.drafted_email.is_approved && (
                        <button className="btn btn-secondary" onClick={() => approveEmail(l.id)}>Approve</button>
                      )}
                      {l.drafted_email?.is_approved && l.status !== 'Email Sent' && authStatus?.authenticated && (
                        <button className="btn btn-primary" disabled={loading} onClick={() => sendEmail(l.id)}>Senden</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {leads.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Kontakte. Suche zuerst Unternehmen und dann Kontakte.</p>}
          </div>
        </div>
      )}

      {/* ─── Social Posts ───────────────────────────── */}
      {tab === 'social' && (
        <div>
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
                const topic = document.getElementById('postTopic').value
                const platform = document.getElementById('postPlatform').value
                generatePost(topic, platform)
              }}>Generieren</button>
            </div>
          </div>
          <div className="card">
            <h2>Posts ({posts.length})</h2>
            {posts.map(p => (
              <div key={p.id} style={{borderBottom:'1px solid #334155',padding:'1rem 0'}}>
                <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                  <span className="badge badge-blue">{p.platform}</span>
                  <div style={{display:'flex',gap:'0.5rem',alignItems:'center'}}>
                    <span style={{fontSize:'0.75rem',color:'#94a3b8'}}>{p.created_date?.split('T')[0]}</span>
                    <button className="btn btn-secondary" style={{padding:'0.2rem 0.5rem',fontSize:'0.7rem'}} onClick={() => {
                      navigator.clipboard.writeText(p.content)
                      showSuccess('In Zwischenablage kopiert')
                    }}>Kopieren</button>
                    <button className="btn btn-secondary" style={{padding:'0.2rem 0.5rem',fontSize:'0.7rem',color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>
                  </div>
                </div>
                <p style={{marginTop:'0.5rem',whiteSpace:'pre-wrap',fontSize:'0.875rem',lineHeight:'1.6'}}>{p.content}</p>
              </div>
            ))}
            {posts.length === 0 && <p style={{padding:'2rem',textAlign:'center',color:'#94a3b8'}}>Noch keine Posts. Generiere einen oben.</p>}
          </div>
        </div>
      )}

      {/* ─── Settings ───────────────────────────────── */}
      {tab === 'settings' && (
        <div className="card">
          <h2>Einstellungen</h2>
          <div style={{marginTop:'1rem'}}>
            <div className="form-group">
              <label>Google Auth</label>
              {authStatus?.authenticated
                ? <div><span style={{color:'#22c55e'}}>Verbunden als {authStatus.email}</span>
                    <button className="btn btn-secondary" style={{marginLeft:'0.5rem'}} onClick={async () => {
                      await fetchJson(`${API}/auth/logout`, { method: 'POST' })
                      loadAuthStatus()
                    }}>Abmelden</button>
                  </div>
                : <div>
                    <a href="/api/auth/google/login" className="btn btn-primary">Mit Google verbinden</a>
                    {authStatus?.token_expired && <span style={{color:'#f59e0b',marginLeft:'0.5rem',fontSize:'0.8rem'}}>Token abgelaufen</span>}
                  </div>
              }
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
