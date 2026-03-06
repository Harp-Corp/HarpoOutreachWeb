import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function App() {
  const [section, setSection] = useState('search')
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

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
    { value: 'DACH', label: 'DACH' }, { value: 'UK', label: 'UK' },
    { value: 'Nordics', label: 'Nordics' }, { value: 'Benelux', label: 'Benelux' },
    { value: 'France', label: 'France' }, { value: 'Baltics', label: 'Baltics' },
    { value: 'Iberia', label: 'Iberia' },
  ]
  const sizesOpts = [
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

  const showSuccess = (msg) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(''), 4000) }

  const loadDashboard = useCallback(async () => {
    try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {}
  }, [])
  const loadCompanies = useCallback(async () => {
    try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {}
  }, [])
  const loadLeads = useCallback(async () => {
    try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {}
  }, [])
  const loadPosts = useCallback(async () => {
    try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {}
  }, [])
  const loadAuthStatus = useCallback(async () => {
    try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {}
  }, [])

  useEffect(() => { loadDashboard(); loadAuthStatus() }, [loadDashboard, loadAuthStatus])

  // Reload data when section changes
  useEffect(() => {
    setError('')
    setSuccessMsg('')
    if (section === 'search' || section === 'campaign') {
      loadCompanies(); loadLeads()
    } else if (section === 'social') {
      loadPosts()
    } else if (section === 'settings') {
      loadDashboard()
    }
  }, [section, loadCompanies, loadLeads, loadPosts, loadDashboard])

  const toggle = (arr, setArr, val) => {
    setArr(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])
  }

  // ─── Actions ────────────────────────────────────────────
  const findCompanies = async () => {
    if (selIndustries.length === 0 || selRegions.length === 0) {
      setError('Bitte mindestens eine Branche und eine Region auswählen.'); return
    }
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/data/companies`, { method: 'DELETE' })
      await fetchJson(`${API}/data/leads`, { method: 'DELETE' })
      setCompanies([]); setLeads([])
      const params = new URLSearchParams()
      selIndustries.forEach(v => params.append('industries', v))
      selRegions.forEach(v => params.append('regions', v))
      selSizes.forEach(v => params.append('sizes', v))
      const r = await fetchJson(`${API}/prospecting/find-companies?${params.toString()}`, { method: 'POST' })
      showSuccess(`${r.total || 0} neue Unternehmen gefunden`)
      await loadCompanies()
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
      let msg = `${r.verified || 0} von ${r.total || 0} verifiziert`
      if (r.errors?.length > 0) msg += ` (${r.errors.length} Fehler)`
      showSuccess(msg)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftEmail = async (leadId) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/email/draft/${leadId}`, { method: 'POST' }); showSuccess('Entwurf erstellt'); await loadLeads() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftAllEmails = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/email/draft-all`, { method: 'POST' }); showSuccess(`${r.created || 0} Entwürfe, ${r.failed || 0} Fehler`); await loadLeads() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }

  const approveEmail = async (leadId) => {
    try { await fetchJson(`${API}/email/approve/${leadId}`, { method: 'POST' }); await loadLeads() }
    catch (e) { setError(e.message) }
  }
  const approveAllEmails = async () => {
    try { const r = await fetchJson(`${API}/email/approve-all`, { method: 'POST' }); showSuccess(`${r.approved || 0} genehmigt`); await loadLeads() }
    catch (e) { setError(e.message) }
  }
  const sendEmail = async (leadId) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/email/send/${leadId}`, { method: 'POST' }); showSuccess('Gesendet'); await loadLeads() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }
  const sendAllEmails = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/email/send-all`, { method: 'POST' }); showSuccess(`${r.sent || 0} gesendet, ${r.failed || 0} fehlgeschlagen`); await loadLeads() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }

  const generatePost = async (topic, platform) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST' }); showSuccess('Post generiert'); await loadPosts() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }

  const deletePost = async (postId) => {
    try { await fetchJson(`${API}/data/social-posts/${postId}`, { method: 'DELETE' }); await loadPosts() }
    catch (e) { setError(e.message) }
  }

  const exportCSV = (type) => {
    window.open(`${API}/data/${type}/export`, '_blank')
  }

  const statusBadge = (status) => {
    const colors = { 'Identified': 'badge-gray', 'Contacted': 'badge-blue', 'Email Drafted': 'badge-yellow', 'Email Approved': 'badge-blue', 'Email Sent': 'badge-green', 'Replied': 'badge-green', 'Follow-Up Drafted': 'badge-yellow', 'Follow-Up Sent': 'badge-green', 'Do Not Contact': 'badge-red', 'Closed': 'badge-gray' }
    return <span className={`badge ${colors[status] || 'badge-gray'}`}>{status}</span>
  }

  const unverifiedLeads = leads.filter(l => !l.email_verified && l.email)

  const CheckboxGroup = ({ label, items, selected, onToggle }) => (
    <div className="form-group">
      <label>{label}</label>
      <div className="checkbox-group">
        {items.map(item => (
          <label key={item.value} className={`chip ${selected.includes(item.value) ? 'active' : ''}`}>
            <input type="checkbox" checked={selected.includes(item.value)} onChange={() => onToggle(item.value)} />
            {item.label}
          </label>
        ))}
      </div>
    </div>
  )

  // ─── Sidebar menu ─────────────────────────────────────
  const menuItems = [
    { id: 'search', icon: '🔍', label: 'Suche & Adressbuch' },
    { id: 'campaign', icon: '📧', label: 'E-Mail-Kampagne' },
    { id: 'social', icon: '💬', label: 'LinkedIn / Social' },
    { id: 'settings', icon: '⚙️', label: 'Einstellungen' },
  ]

  const handleMenuClick = (id) => {
    setSection(id)
  }

  // ─── Render ───────────────────────────────────────────
  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">Harpo</div>
          <div className="logo-sub">Outreach</div>
        </div>
        <nav className="sidebar-nav">
          {menuItems.map(m => (
            <button
              key={m.id}
              className={`nav-item ${section === m.id ? 'active' : ''}`}
              onClick={() => handleMenuClick(m.id)}
              type="button"
            >
              <span className="nav-icon">{m.icon}</span>
              <span className="nav-label">{m.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          {stats && (
            <div className="mini-stats">
              <span><strong>{stats.total_leads}</strong> Leads</span>
              <span><strong>{stats.emails_sent}</strong> Sent</span>
            </div>
          )}
          <div className="auth-indicator">
            {authStatus?.authenticated
              ? <span className="auth-ok">● {authStatus.email}</span>
              : <a href="/api/auth/google/login" className="auth-warn">● Google verbinden</a>
            }
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {error && <div className="msg msg-error">{error} <button onClick={() => setError('')}>×</button></div>}
        {successMsg && <div className="msg msg-success">{successMsg}</div>}
        {loading && <div className="msg msg-loading">Wird verarbeitet...</div>}

        {/* ═══ SEARCH & ADRESSBUCH ═══════════════════ */}
        {section === 'search' && (
          <div key="search">
            <h1 className="page-title">Suche & Adressbuch</h1>
            <p className="page-desc">Unternehmen suchen → Kontakte finden → Verifizieren → CSV exportieren</p>

            {/* Search form */}
            <div className="card">
              <CheckboxGroup label="Branchen" items={industries} selected={selIndustries} onToggle={v => toggle(selIndustries, setSelIndustries, v)} />
              <CheckboxGroup label="Regionen" items={regions} selected={selRegions} onToggle={v => toggle(selRegions, setSelRegions, v)} />
              <CheckboxGroup label="Größe (optional)" items={sizesOpts} selected={selSizes} onToggle={v => toggle(selSizes, setSelSizes, v)} />
              <div className="search-actions">
                <button className="btn btn-primary" disabled={loading || !selIndustries.length || !selRegions.length} onClick={findCompanies}>
                  Neue Suche ({selIndustries.length}×{selRegions.length})
                </button>
                {(selIndustries.length > 0 || selRegions.length > 0 || selSizes.length > 0) && (
                  <button className="btn btn-ghost" onClick={() => { setSelIndustries([]); setSelRegions([]); setSelSizes([]) }}>Reset</button>
                )}
                <span className="hint">Alte Ergebnisse werden bei neuer Suche gelöscht.</span>
              </div>
            </div>

            {/* Two-column: Companies left, Contacts right */}
            {(companies.length > 0 || leads.length > 0) && (
              <div className="two-col">
                <div className="col-left">
                  <div className="card">
                    <div className="card-header">
                      <h2>Unternehmen ({companies.length})</h2>
                      <div className="card-actions">
                        {companies.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('companies')}>CSV</button>}
                        {companies.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={findAllContacts}>Alle Kontakte suchen</button>}
                      </div>
                    </div>
                    <div className="list">
                      {companies.map(c => (
                        <div key={c.id} className="list-item">
                          <div className="list-main">
                            <strong>{c.name}</strong>
                            <span className="sub">{c.industry} · {c.country} · {c.employee_count?.toLocaleString()} MA</span>
                          </div>
                          <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte</button>
                        </div>
                      ))}
                      {companies.length === 0 && <p className="empty">Keine Unternehmen.</p>}
                    </div>
                  </div>
                </div>
                <div className="col-right">
                  <div className="card">
                    <div className="card-header">
                      <h2>Kontakte ({leads.length})</h2>
                      <div className="card-actions">
                        {leads.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('leads')}>CSV</button>}
                        {unverifiedLeads.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={verifyAllEmails}>Alle verifizieren ({unverifiedLeads.length})</button>}
                      </div>
                    </div>
                    <div className="list">
                      {leads.map(l => (
                        <div key={l.id} className="list-item">
                          <div className="list-main">
                            <strong>{l.name}</strong>
                            <span className="sub">{l.title} · {l.company}</span>
                            <span className="sub">
                              {l.email || '—'}
                              {l.email_verified && <span className="verified">✓</span>}
                            </span>
                          </div>
                          <div className="list-actions">
                            {statusBadge(l.status)}
                            {l.email && !l.email_verified && (
                              <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verify</button>
                            )}
                          </div>
                        </div>
                      ))}
                      {leads.length === 0 && <p className="empty">Keine Kontakte. Erst Unternehmen suchen, dann Kontakte finden.</p>}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ E-MAIL-KAMPAGNE ═══════════════════════ */}
        {section === 'campaign' && (
          <div key="campaign">
            <h1 className="page-title">E-Mail-Kampagne</h1>
            <p className="page-desc">Unternehmen → Kontakte → Verifizieren → Drafts → Genehmigen → Versand</p>

            {/* Search form */}
            <div className="card">
              <CheckboxGroup label="Branchen" items={industries} selected={selIndustries} onToggle={v => toggle(selIndustries, setSelIndustries, v)} />
              <CheckboxGroup label="Regionen" items={regions} selected={selRegions} onToggle={v => toggle(selRegions, setSelRegions, v)} />
              <CheckboxGroup label="Größe (optional)" items={sizesOpts} selected={selSizes} onToggle={v => toggle(selSizes, setSelSizes, v)} />
              <div className="search-actions">
                <button className="btn btn-primary" disabled={loading || !selIndustries.length || !selRegions.length} onClick={findCompanies}>
                  Neue Suche ({selIndustries.length}×{selRegions.length})
                </button>
                {(selIndustries.length > 0 || selRegions.length > 0 || selSizes.length > 0) && (
                  <button className="btn btn-ghost" onClick={() => { setSelIndustries([]); setSelRegions([]); setSelSizes([]) }}>Reset</button>
                )}
              </div>
            </div>

            {/* Two-column: Companies left, Leads+Pipeline right */}
            {(companies.length > 0 || leads.length > 0) && (
              <div className="two-col">
                <div className="col-left">
                  <div className="card">
                    <div className="card-header">
                      <h2>Unternehmen ({companies.length})</h2>
                      <button className="btn btn-secondary" disabled={loading} onClick={findAllContacts}>Alle Kontakte</button>
                    </div>
                    <div className="list">
                      {companies.map(c => (
                        <div key={c.id} className="list-item">
                          <div className="list-main">
                            <strong>{c.name}</strong>
                            <span className="sub">{c.country} · {c.employee_count?.toLocaleString()} MA</span>
                          </div>
                          <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte</button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="col-right">
                  <div className="card">
                    <div className="card-header">
                      <h2>Pipeline ({leads.length})</h2>
                      <div className="card-actions">
                        {leads.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('leads')}>CSV</button>}
                      </div>
                    </div>
                    {/* Batch actions bar */}
                    {leads.length > 0 && (
                      <div className="batch-bar">
                        {unverifiedLeads.length > 0 && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={verifyAllEmails}>Verifizieren ({unverifiedLeads.length})</button>}
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={draftAllEmails}>Alle Drafts</button>
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={approveAllEmails}>Alle Approve</button>
                        {authStatus?.authenticated && <button className="btn btn-primary btn-sm" disabled={loading} onClick={sendAllEmails}>Alle Senden</button>}
                      </div>
                    )}
                    <div className="list">
                      {leads.map(l => (
                        <div key={l.id} className="list-item">
                          <div className="list-main">
                            <strong>{l.name}</strong>
                            <span className="sub">{l.title} · {l.company}</span>
                            <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}</span>
                          </div>
                          <div className="list-actions">
                            {statusBadge(l.status)}
                            {l.email && !l.email_verified && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verify</button>}
                            {!l.drafted_email && l.email && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => draftEmail(l.id)}>Draft</button>}
                            {l.drafted_email && !l.drafted_email.is_approved && <button className="btn btn-ghost btn-sm" onClick={() => approveEmail(l.id)}>OK</button>}
                            {l.drafted_email?.is_approved && l.status !== 'Email Sent' && authStatus?.authenticated && <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => sendEmail(l.id)}>Send</button>}
                          </div>
                        </div>
                      ))}
                      {leads.length === 0 && <p className="empty">Noch keine Kontakte.</p>}
                    </div>
                  </div>
                  {!authStatus?.authenticated && leads.length > 0 && (
                    <div className="card card-warn">
                      <a href="/api/auth/google/login">Mit Google verbinden</a> um E-Mails zu senden.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ LINKEDIN / SOCIAL ═══════════════════════ */}
        {section === 'social' && (
          <div key="social">
            <h1 className="page-title">LinkedIn / Social</h1>
            <p className="page-desc">Posts für LinkedIn und Twitter/X generieren und verwalten</p>

            <div className="card">
              <h2>Post generieren</h2>
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
                <div key={p.id} className="post-item">
                  <div className="post-header">
                    <span className="badge badge-blue">{p.platform}</span>
                    <div className="post-actions">
                      <span className="sub">{p.created_date?.split('T')[0]}</span>
                      <button className="btn btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(p.content); showSuccess('Kopiert') }}>Kopieren</button>
                      <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>
                    </div>
                  </div>
                  <p className="post-content">{p.content}</p>
                </div>
              ))}
              {posts.length === 0 && <p className="empty">Noch keine Posts.</p>}
            </div>
          </div>
        )}

        {/* ═══ SETTINGS ════════════════════════════════ */}
        {section === 'settings' && (
          <div key="settings">
            <h1 className="page-title">Einstellungen</h1>

            <div className="card">
              <h2>Google Auth</h2>
              {authStatus?.authenticated
                ? <div style={{display:'flex',alignItems:'center',gap:'0.75rem'}}>
                    <span style={{color:'#22c55e'}}>Verbunden als {authStatus.email}</span>
                    <button className="btn btn-secondary btn-sm" onClick={async () => { await fetchJson(`${API}/auth/logout`, { method: 'POST' }); loadAuthStatus() }}>Abmelden</button>
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
                <div className="stats-grid">
                  <div className="stat-card"><div className="stat-val">{stats.total_leads}</div><div className="stat-lbl">Leads</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.emails_sent}</div><div className="stat-lbl">Gesendet</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.replies_received}</div><div className="stat-lbl">Antworten</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.conversion_rate}%</div><div className="stat-lbl">Rate</div></div>
                </div>
                {Object.keys(stats.leads_by_status || {}).length > 0 && (
                  <div style={{marginTop:'1.5rem'}}>
                    <h3 style={{fontSize:'0.8125rem',fontWeight:600,marginBottom:'0.5rem',color:'#64748b'}}>Status</h3>
                    {Object.entries(stats.leads_by_status).map(([k, v]) => (
                      <div key={k} style={{display:'flex',justifyContent:'space-between',padding:'0.25rem 0',fontSize:'0.8125rem'}}>
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
