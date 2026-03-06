import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function App() {
  const [section, setSection] = useState('search')
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [addressBook, setAddressBook] = useState([])
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  // Campaign source toggle
  const [campaignSource, setCampaignSource] = useState('search') // 'search' | 'addressbook'
  const [abFilter, setAbFilter] = useState('all') // 'all' | 'active' | 'blocked'

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
    if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `HTTP ${resp.status}`) }
    return resp.json()
  }
  const showSuccess = (msg) => { setSuccessMsg(msg); setTimeout(() => setSuccessMsg(''), 4000) }

  const loadDashboard = useCallback(async () => { try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {} }, [])
  const loadCompanies = useCallback(async () => { try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {} }, [])
  const loadLeads = useCallback(async () => { try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {} }, [])
  const loadPosts = useCallback(async () => { try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {} }, [])
  const loadAddressBook = useCallback(async () => { try { const r = await fetchJson(`${API}/data/address-book`); setAddressBook(r.data || []) } catch {} }, [])
  const loadAuthStatus = useCallback(async () => { try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {} }, [])

  useEffect(() => { loadDashboard(); loadAuthStatus() }, [loadDashboard, loadAuthStatus])
  useEffect(() => {
    setError(''); setSuccessMsg('')
    if (section === 'search') { loadCompanies(); loadLeads() }
    else if (section === 'addressbook') { loadAddressBook() }
    else if (section === 'campaign') { loadCompanies(); loadLeads(); loadAddressBook() }
    else if (section === 'social') { loadPosts() }
    else if (section === 'settings') { loadDashboard(); loadAddressBook() }
  }, [section, loadCompanies, loadLeads, loadPosts, loadAddressBook, loadDashboard])

  const toggle = (arr, setArr, val) => setArr(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])

  // ─── Actions ────────────────────────────────────────────
  const findCompanies = async () => {
    if (!selIndustries.length || !selRegions.length) { setError('Bitte mindestens eine Branche und eine Region auswählen.'); return }
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
      showSuccess(`${r.total || 0} Unternehmen gefunden`)
      await loadCompanies()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const findContacts = async (companyId) => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST' }); showSuccess(`${r.total || 0} Kontakte`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const findAllContacts = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/prospecting/find-contacts-all`, { method: 'POST' }); showSuccess(`${r.total_new || 0} neue Kontakte`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const verifyEmail = async (leadId) => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/prospecting/verify-email/${leadId}`, { method: 'POST' }); showSuccess(`Verifiziert: ${r.data?.email || 'OK'}`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const verifyAllEmails = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/prospecting/verify-all`, { method: 'POST' }); showSuccess(`${r.verified || 0}/${r.total || 0} verifiziert`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const addToAddressBook = async (leadId) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/data/address-book/from-lead/${leadId}`, { method: 'POST' }); showSuccess('Ins Adressbuch übernommen'); await loadAddressBook() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const addAllVerifiedToAddressBook = async () => {
    setLoading(true); setError('')
    const verified = leads.filter(l => l.email_verified)
    let added = 0
    for (const l of verified) {
      try { await fetchJson(`${API}/data/address-book/from-lead/${l.id}`, { method: 'POST' }); added++ } catch {}
    }
    showSuccess(`${added} Kontakte ins Adressbuch übernommen`)
    await loadAddressBook()
    setLoading(false)
  }
  const removeFromAddressBook = async (entryId) => {
    try { await fetchJson(`${API}/data/address-book/${entryId}`, { method: 'DELETE' }); await loadAddressBook() }
    catch (e) { setError(e.message) }
  }
  const setContactStatus = async (entryId, newStatus) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/data/address-book/${entryId}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contact_status: newStatus }) })
      showSuccess(newStatus === 'blocked' ? 'Kontakt gesperrt' : 'Kontakt freigeschaltet')
      await loadAddressBook()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }
  const permanentlyDeleteContact = async (entryId) => {
    if (!confirm('Kontakt endgültig löschen?')) return
    setLoading(true); setError('')
    try { await fetchJson(`${API}/data/address-book/${entryId}/permanent`, { method: 'DELETE' }); showSuccess('Kontakt gelöscht'); await loadAddressBook() }
    catch (e) { setError(e.message) }
    setLoading(false)
  }
  const addManualContact = async (formData) => {
    setLoading(true); setError('')
    try {
      await fetchJson(`${API}/data/address-book`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) })
      showSuccess('Kontakt hinzugefügt'); setShowAddForm(false); await loadAddressBook()
    } catch (e) { setError(e.message) }
    setLoading(false)
  }

  const draftEmail = async (leadId) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/email/draft/${leadId}`, { method: 'POST' }); showSuccess('Entwurf erstellt'); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const draftAllEmails = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/email/draft-all`, { method: 'POST' }); showSuccess(`${r.created || 0} Entwürfe`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const approveEmail = async (leadId) => {
    try { await fetchJson(`${API}/email/approve/${leadId}`, { method: 'POST' }); await loadLeads() } catch (e) { setError(e.message) }
  }
  const approveAllEmails = async () => {
    try { const r = await fetchJson(`${API}/email/approve-all`, { method: 'POST' }); showSuccess(`${r.approved || 0} genehmigt`); await loadLeads() } catch (e) { setError(e.message) }
  }
  const sendEmail = async (leadId) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/email/send/${leadId}`, { method: 'POST' }); showSuccess('Gesendet'); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const sendAllEmails = async () => {
    setLoading(true); setError('')
    try { const r = await fetchJson(`${API}/email/send-all`, { method: 'POST' }); showSuccess(`${r.sent || 0} gesendet`); await loadLeads() }
    catch (e) { setError(e.message) } setLoading(false)
  }

  // Campaign: create leads from address book contacts
  const importAddressBookToCampaign = async () => {
    setLoading(true); setError('')
    let created = 0
    const activeContacts = addressBook.filter(c => (c.contact_status || 'active') === 'active')
    for (const contact of activeContacts) {
      try {
        await fetchJson(`${API}/data/leads`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: contact.name, title: contact.title, company: contact.company, email: contact.email, email_verified: contact.email_verified, linkedin_url: contact.linkedin_url, source: 'Adressbuch', status: 'Identified' })
        })
        created++
      } catch {}
    }
    showSuccess(`${created} Kontakte aus Adressbuch importiert`)
    await loadLeads()
    setLoading(false)
  }

  const generatePost = async (topic, platform) => {
    setLoading(true); setError('')
    try { await fetchJson(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST' }); showSuccess('Post generiert'); await loadPosts() }
    catch (e) { setError(e.message) } setLoading(false)
  }
  const deletePost = async (postId) => {
    try { await fetchJson(`${API}/data/social-posts/${postId}`, { method: 'DELETE' }); await loadPosts() } catch (e) { setError(e.message) }
  }
  const exportCSV = (type) => window.open(`${API}/data/${type}/export`, '_blank')

  const statusBadge = (status) => {
    const c = { 'Identified':'badge-gray','Email Verified':'badge-green','Contacted':'badge-blue','Email Drafted':'badge-yellow','Email Approved':'badge-blue','Email Sent':'badge-green','Replied':'badge-green','Follow-Up Drafted':'badge-yellow','Follow-Up Sent':'badge-green','Do Not Contact':'badge-red','Closed':'badge-gray' }
    return <span className={`badge ${c[status]||'badge-gray'}`}>{status}</span>
  }
  const unverifiedLeads = leads.filter(l => !l.email_verified && l.email)
  const verifiedLeads = leads.filter(l => l.email_verified)
  const abEmails = new Set(addressBook.map(a => a.email?.toLowerCase()))

  const CheckboxGroup = ({ label, items, selected, onToggle }) => (
    <div className="form-group">
      <label>{label}</label>
      <div className="checkbox-group">
        {items.map(item => (
          <label key={item.value} className={`chip ${selected.includes(item.value) ? 'active' : ''}`}>
            <input type="checkbox" checked={selected.includes(item.value)} onChange={() => onToggle(item.value)} />{item.label}
          </label>
        ))}
      </div>
    </div>
  )

  const menuItems = [
    { id: 'search', icon: '🔍', label: 'Suche' },
    { id: 'addressbook', icon: '📖', label: 'Adressbuch' },
    { id: 'campaign', icon: '📧', label: 'Kampagne' },
    { id: 'social', icon: '💬', label: 'LinkedIn' },
    { id: 'settings', icon: '⚙️', label: 'Einstellungen' },
  ]

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header"><div className="logo">Harpo</div><div className="logo-sub">Outreach</div></div>
        <nav className="sidebar-nav">
          {menuItems.map(m => (
            <button key={m.id} type="button" className={`nav-item ${section === m.id ? 'active' : ''}`} onClick={() => setSection(m.id)}>
              <span className="nav-icon">{m.icon}</span><span className="nav-label">{m.label}</span>
              {m.id === 'addressbook' && addressBook.length > 0 && <span className="nav-count">{addressBook.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-footer">
          {stats && <div className="mini-stats"><span><strong>{stats.total_leads}</strong> Leads</span><span><strong>{stats.address_book_count || 0}</strong> Adressbuch</span></div>}
          <div className="auth-indicator">
            {authStatus?.authenticated ? <span className="auth-ok">● {authStatus.email}</span> : <a href="/api/auth/google/login" className="auth-warn">● Google verbinden</a>}
          </div>
        </div>
      </aside>

      <main className="main">
        {error && <div className="msg msg-error">{error} <button onClick={() => setError('')}>×</button></div>}
        {successMsg && <div className="msg msg-success">{successMsg}</div>}
        {loading && <div className="msg msg-loading">Wird verarbeitet...</div>}

        {/* ═══ SUCHE ═══════════════════════════════════ */}
        {section === 'search' && (
          <div key="search">
            <h1 className="page-title">Suche</h1>
            <p className="page-desc">Unternehmen suchen → Kontakte finden → Verifizieren → Ins Adressbuch übernehmen</p>
            <div className="card">
              <CheckboxGroup label="Branchen" items={industries} selected={selIndustries} onToggle={v => toggle(selIndustries, setSelIndustries, v)} />
              <CheckboxGroup label="Regionen" items={regions} selected={selRegions} onToggle={v => toggle(selRegions, setSelRegions, v)} />
              <CheckboxGroup label="Größe (optional)" items={sizesOpts} selected={selSizes} onToggle={v => toggle(selSizes, setSelSizes, v)} />
              <div className="search-actions">
                <button className="btn btn-primary" disabled={loading || !selIndustries.length || !selRegions.length} onClick={findCompanies}>Neue Suche ({selIndustries.length}×{selRegions.length})</button>
                {(selIndustries.length > 0 || selRegions.length > 0 || selSizes.length > 0) && <button className="btn btn-ghost" onClick={() => { setSelIndustries([]); setSelRegions([]); setSelSizes([]) }}>Reset</button>}
              </div>
            </div>
            {(companies.length > 0 || leads.length > 0) && (
              <div className="two-col">
                <div className="col-left">
                  <div className="card">
                    <div className="card-header"><h2>Unternehmen ({companies.length})</h2>
                      <div className="card-actions">
                        {companies.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('companies')}>CSV</button>}
                        {companies.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={findAllContacts}>Alle Kontakte</button>}
                      </div>
                    </div>
                    <div className="list">{companies.map(c => (
                      <div key={c.id} className="list-item">
                        <div className="list-main"><strong>{c.name}</strong><span className="sub">{c.industry} · {c.country} · {c.employee_count?.toLocaleString()} MA</span></div>
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte</button>
                      </div>
                    ))}{companies.length === 0 && <p className="empty">Keine Unternehmen.</p>}</div>
                  </div>
                </div>
                <div className="col-right">
                  <div className="card">
                    <div className="card-header"><h2>Kontakte ({leads.length})</h2>
                      <div className="card-actions">
                        {leads.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('leads')}>CSV</button>}
                        {unverifiedLeads.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={verifyAllEmails}>Alle verifizieren ({unverifiedLeads.length})</button>}
                        {verifiedLeads.length > 0 && <button className="btn btn-primary btn-sm" disabled={loading} onClick={addAllVerifiedToAddressBook}>Alle ins Adressbuch</button>}
                      </div>
                    </div>
                    <div className="list">{leads.map(l => (
                      <div key={l.id} className="list-item">
                        <div className="list-main">
                          <strong>{l.name}</strong>
                          <span className="sub">{l.title} · {l.company}</span>
                          <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}</span>
                        </div>
                        <div className="list-actions">
                          {statusBadge(l.status)}
                          {l.email && !l.email_verified && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verify</button>}
                          {l.email_verified && !abEmails.has(l.email?.toLowerCase()) && <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => addToAddressBook(l.id)} title="Ins Adressbuch">📖+</button>}
                          {l.email_verified && abEmails.has(l.email?.toLowerCase()) && <span className="badge badge-green">Im AB</span>}
                        </div>
                      </div>
                    ))}{leads.length === 0 && <p className="empty">Keine Kontakte.</p>}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ ADRESSBUCH ══════════════════════════════ */}
        {section === 'addressbook' && (
          <div key="addressbook">
            <h1 className="page-title">Adressbuch</h1>
            <p className="page-desc">Verifizierte und manuell eingetragene Kontakte — Basis für Kampagnen</p>
            <div className="card">
              <div className="card-header">
                <h2>Kontakte ({addressBook.length})</h2>
                <div className="card-actions">
                  {addressBook.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('address-book')}>CSV</button>}
                  <button className="btn btn-primary" onClick={() => setShowAddForm(!showAddForm)}>{showAddForm ? 'Abbrechen' : '+ Kontakt'}</button>
                </div>
              </div>
              {/* Filter bar */}
              {addressBook.length > 0 && (
                <div className="filter-bar">
                  <button className={`btn btn-sm ${abFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('all')}>Alle ({addressBook.length})</button>
                  <button className={`btn btn-sm ${abFilter === 'active' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('active')}>Nutzbar ({addressBook.filter(a => (a.contact_status || 'active') === 'active').length})</button>
                  <button className={`btn btn-sm ${abFilter === 'blocked' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('blocked')}>Gesperrt ({addressBook.filter(a => a.contact_status === 'blocked').length})</button>
                </div>
              )}
              {showAddForm && (
                <form className="add-form" onSubmit={e => { e.preventDefault(); const fd = new FormData(e.target); addManualContact({ name: fd.get('name'), title: fd.get('title'), company: fd.get('company'), email: fd.get('email'), linkedin_url: fd.get('linkedin_url') || '', phone: fd.get('phone') || '' }) }}>
                  <div className="form-row">
                    <input name="name" placeholder="Name" required />
                    <input name="title" placeholder="Titel/Position" />
                    <input name="company" placeholder="Unternehmen" required />
                  </div>
                  <div className="form-row">
                    <input name="email" type="email" placeholder="E-Mail" required />
                    <input name="linkedin_url" placeholder="LinkedIn URL" />
                    <input name="phone" placeholder="Telefon" />
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={loading}>Hinzufügen</button>
                </form>
              )}
              <div className="list">
                {addressBook
                  .filter(a => abFilter === 'all' || (abFilter === 'active' ? (a.contact_status || 'active') === 'active' : a.contact_status === 'blocked'))
                  .map(a => {
                  const isBlocked = a.contact_status === 'blocked'
                  return (
                    <div key={a.id} className={`list-item ${isBlocked ? 'list-item-blocked' : ''}`}>
                      <div className="list-main">
                        <strong>{a.name}</strong>
                        <span className="sub">{a.title} · {a.company}</span>
                        <span className="sub">{a.email}{a.email_verified && <span className="verified">✓</span>}</span>
                      </div>
                      <div className="list-actions">
                        <span className={`badge ${a.source === 'verified' ? 'badge-green' : 'badge-blue'}`}>{a.source === 'verified' ? 'Verifiziert' : 'Manuell'}</span>
                        {isBlocked
                          ? <span className="badge badge-red">Gesperrt</span>
                          : <span className="badge badge-green">Nutzbar</span>
                        }
                        {isBlocked
                          ? <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => setContactStatus(a.id, 'active')} title="Für Kontaktaufnahme freischalten">Freischalten</button>
                          : <button className="btn btn-ghost btn-sm" style={{color:'#f59e0b'}} disabled={loading} onClick={() => setContactStatus(a.id, 'blocked')} title="Für Kontaktaufnahme sperren (Opt-out)">Sperren</button>
                        }
                        <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} disabled={loading} onClick={() => permanentlyDeleteContact(a.id)} title="Endgültig löschen">Löschen</button>
                      </div>
                    </div>
                  )
                })}
                {addressBook.length === 0 && <p className="empty">Adressbuch ist leer. Kontakte über Suche verifizieren und übernehmen, oder manuell eintragen.</p>}
                {addressBook.length > 0 && addressBook.filter(a => abFilter === 'all' || (abFilter === 'active' ? (a.contact_status || 'active') === 'active' : a.contact_status === 'blocked')).length === 0 && <p className="empty">Keine Kontakte mit diesem Filter.</p>}
              </div>
            </div>
          </div>
        )}

        {/* ═══ KAMPAGNE ════════════════════════════════ */}
        {section === 'campaign' && (
          <div key="campaign">
            <h1 className="page-title">E-Mail-Kampagne</h1>
            <p className="page-desc">Kontakte aus Adressbuch oder neuer Suche → Drafts → Genehmigen → Versand</p>

            {/* Source toggle */}
            <div className="card">
              <h2>Kontaktquelle</h2>
              <div className="source-toggle">
                <button className={`btn ${campaignSource === 'addressbook' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setCampaignSource('addressbook')}>
                  📖 Adressbuch ({addressBook.length})
                </button>
                <button className={`btn ${campaignSource === 'search' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setCampaignSource('search')}>
                  🔍 Neue Suche
                </button>
              </div>
              {campaignSource === 'addressbook' && addressBook.length > 0 && (
                <div style={{marginTop:'0.75rem'}}>
                  <button className="btn btn-primary" disabled={loading} onClick={importAddressBookToCampaign}>
                    {addressBook.filter(c => (c.contact_status || 'active') === 'active').length} nutzbare Kontakte als Leads importieren
                  </button>
                  <span className="hint" style={{marginLeft:'0.5rem'}}>Gesperrte Kontakte werden übersprungen.</span>
                </div>
              )}
              {campaignSource === 'addressbook' && addressBook.length === 0 && (
                <p className="hint" style={{marginTop:'0.5rem'}}>Adressbuch ist leer. Erst über Suche Kontakte verifizieren und übernehmen.</p>
              )}
            </div>

            {/* Search form (only if source=search) */}
            {campaignSource === 'search' && (
              <div className="card">
                <CheckboxGroup label="Branchen" items={industries} selected={selIndustries} onToggle={v => toggle(selIndustries, setSelIndustries, v)} />
                <CheckboxGroup label="Regionen" items={regions} selected={selRegions} onToggle={v => toggle(selRegions, setSelRegions, v)} />
                <CheckboxGroup label="Größe (optional)" items={sizesOpts} selected={selSizes} onToggle={v => toggle(selSizes, setSelSizes, v)} />
                <div className="search-actions">
                  <button className="btn btn-primary" disabled={loading || !selIndustries.length || !selRegions.length} onClick={findCompanies}>Neue Suche ({selIndustries.length}×{selRegions.length})</button>
                </div>
              </div>
            )}

            {/* Two-column results */}
            {(companies.length > 0 || leads.length > 0) && (
              <div className="two-col">
                {campaignSource === 'search' && companies.length > 0 && (
                  <div className="col-left">
                    <div className="card">
                      <div className="card-header"><h2>Unternehmen ({companies.length})</h2>
                        <button className="btn btn-secondary" disabled={loading} onClick={findAllContacts}>Alle Kontakte</button>
                      </div>
                      <div className="list">{companies.map(c => (
                        <div key={c.id} className="list-item">
                          <div className="list-main"><strong>{c.name}</strong><span className="sub">{c.country} · {c.employee_count?.toLocaleString()} MA</span></div>
                          <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => findContacts(c.id)}>Kontakte</button>
                        </div>
                      ))}</div>
                    </div>
                  </div>
                )}
                <div className={campaignSource === 'search' && companies.length > 0 ? 'col-right' : ''} style={campaignSource === 'addressbook' ? {width:'100%'} : {}}>
                  <div className="card">
                    <div className="card-header"><h2>Pipeline ({leads.length})</h2>
                      <div className="card-actions">{leads.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('leads')}>CSV</button>}</div>
                    </div>
                    {leads.length > 0 && (
                      <div className="batch-bar">
                        {unverifiedLeads.length > 0 && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={verifyAllEmails}>Verifizieren ({unverifiedLeads.length})</button>}
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={draftAllEmails}>Alle Drafts</button>
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={approveAllEmails}>Alle Approve</button>
                        {authStatus?.authenticated && <button className="btn btn-primary btn-sm" disabled={loading} onClick={sendAllEmails}>Alle Senden</button>}
                      </div>
                    )}
                    <div className="list">{leads.map(l => (
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
                    ))}{leads.length === 0 && <p className="empty">Noch keine Kontakte in der Pipeline.</p>}</div>
                  </div>
                  {!authStatus?.authenticated && leads.length > 0 && (
                    <div className="card card-warn"><a href="/api/auth/google/login">Mit Google verbinden</a> um E-Mails zu senden.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══ LINKEDIN ════════════════════════════════ */}
        {section === 'social' && (
          <div key="social">
            <h1 className="page-title">LinkedIn / Social</h1>
            <div className="card">
              <h2>Post generieren</h2>
              <div style={{display:'flex',gap:'0.5rem',alignItems:'end',flexWrap:'wrap'}}>
                <div className="form-group" style={{flex:1,minWidth:'150px'}}><label>Thema</label>
                  <select id="postTopic"><option value="Regulatory Update">Regulatory Update</option><option value="Compliance Tip">Compliance Tip</option><option value="Industry Insight">Industry Insight</option><option value="Product Feature">Product Feature</option><option value="Thought Leadership">Thought Leadership</option><option value="Case Study">Case Study</option></select>
                </div>
                <div className="form-group" style={{flex:1,minWidth:'150px'}}><label>Plattform</label>
                  <select id="postPlatform"><option value="LinkedIn">LinkedIn</option><option value="Twitter/X">Twitter/X</option></select>
                </div>
                <button className="btn btn-primary" disabled={loading} onClick={() => generatePost(document.getElementById('postTopic').value, document.getElementById('postPlatform').value)}>Generieren</button>
              </div>
            </div>
            <div className="card"><h2>Posts ({posts.length})</h2>
              {posts.map(p => (
                <div key={p.id} className="post-item">
                  <div className="post-header"><span className="badge badge-blue">{p.platform}</span>
                    <div className="post-actions"><span className="sub">{p.created_date?.split('T')[0]}</span>
                      <button className="btn btn-ghost btn-sm" onClick={() => { navigator.clipboard.writeText(p.content); showSuccess('Kopiert') }}>Kopieren</button>
                      <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>
                    </div>
                  </div>
                  <p className="post-content">{p.content}</p>
                </div>
              ))}{posts.length === 0 && <p className="empty">Noch keine Posts.</p>}
            </div>
          </div>
        )}

        {/* ═══ SETTINGS ════════════════════════════════ */}
        {section === 'settings' && (
          <div key="settings">
            <h1 className="page-title">Einstellungen</h1>
            <div className="card"><h2>Google Auth</h2>
              {authStatus?.authenticated
                ? <div style={{display:'flex',alignItems:'center',gap:'0.75rem'}}><span style={{color:'#22c55e'}}>Verbunden als {authStatus.email}</span>
                    <button className="btn btn-secondary btn-sm" onClick={async () => { await fetchJson(`${API}/auth/logout`, { method: 'POST' }); loadAuthStatus() }}>Abmelden</button></div>
                : <div><a href="/api/auth/google/login" className="btn btn-primary">Mit Google verbinden</a>{authStatus?.token_expired && <span style={{color:'#f59e0b',marginLeft:'0.5rem',fontSize:'0.8rem'}}>Token abgelaufen</span>}</div>}
            </div>
            {stats && (
              <div className="card"><h2>Dashboard</h2>
                <div className="stats-grid">
                  <div className="stat-card"><div className="stat-val">{stats.total_leads}</div><div className="stat-lbl">Leads</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.emails_sent}</div><div className="stat-lbl">Gesendet</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.address_book_count || 0}</div><div className="stat-lbl">Adressbuch</div></div>
                  <div className="stat-card"><div className="stat-val">{stats.conversion_rate}%</div><div className="stat-lbl">Rate</div></div>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

export default App
