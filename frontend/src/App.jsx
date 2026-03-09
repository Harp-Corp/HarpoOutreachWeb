import { useState, useEffect, useCallback, useRef } from 'react'
import harpoLogo from './assets/logo.webp'

const API = '/api'

function App() {
  const [section, setSection] = useState('overview')
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [addressBook, setAddressBook] = useState([])
  const [sentEmails, setSentEmails] = useState([])
  const [analyticsSummary, setAnalyticsSummary] = useState(null)
  const [analyticsFunnel, setAnalyticsFunnel] = useState(null)
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [abFilter, setAbFilter] = useState('all')
  const [abGroupByCompany, setAbGroupByCompany] = useState(true)
  const [abSearchQuery, setAbSearchQuery] = useState('')
  const [abSearchResult, setAbSearchResult] = useState(null) // { company, contacts }
  const [abSearching, setAbSearching] = useState(false)
  const [analyticsExpanded, setAnalyticsExpanded] = useState({})
  const [checkingReplies, setCheckingReplies] = useState(false)
  const [linkedinSettings, setLinkedinSettings] = useState({ org_id: '', has_token: false })
  const [replyCheckResult, setReplyCheckResult] = useState(null)
  const [loadingProgress, setLoadingProgress] = useState(null) // { current, total } for batch ops
  const [searchLeadsFilter, setSearchLeadsFilter] = useState('with_email') // 'all' | 'verified' | 'unverified'
  const [searchLeadsQuery, setSearchLeadsQuery] = useState('') // text filter for leads
  const [leadsGroupByCompany, setLeadsGroupByCompany] = useState(true) // group contacts by company
  const [leadsDisplayLimit, setLeadsDisplayLimit] = useState(50) // pagination: show N leads at a time

  // Campaign wizard state
  const [campStep, setCampStep] = useState(1) // 1=select, 2=draft+edit, 3=approve, 4=send
  const [campSelected, setCampSelected] = useState(new Set()) // selected address book entry IDs
  const [campLeads, setCampLeads] = useState([]) // leads created for this campaign
  const [campActiveLeadId, setCampActiveLeadId] = useState(null) // selected lead for email preview
  const [campDraftSubject, setCampDraftSubject] = useState('')
  const [campDraftBody, setCampDraftBody] = useState('')
  const [campSendSelected, setCampSendSelected] = useState(new Set()) // step 4: which to send
  const [campDrafting, setCampDrafting] = useState(false) // drafting in progress

  // Campaign Sequences state
  const [seqCampaigns, setSeqCampaigns] = useState([])
  const [seqTemplates, setSeqTemplates] = useState([])
  const [seqView, setSeqView] = useState('wizard') // 'wizard' | 'sequences'

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

  const fetchJson = async (url, opts = {}, retries = 0) => {
    const maxRetries = retries || (opts.method && opts.method !== 'GET' ? 1 : 2)
    let lastError
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const resp = await fetch(url, opts)
        if (resp.status >= 500 && attempt < maxRetries) {
          // Server error — retry after short delay
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
          continue
        }
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}))
          const detail = err.detail || ''
          if (resp.status === 400 && detail.includes('API Key')) throw new Error('Perplexity API-Key nicht konfiguriert. Bitte in den Einstellungen hinterlegen.')
          if (resp.status === 401 || detail.toLowerCase().includes('quota')) throw new Error('API-Quota erschöpft oder ungültiger Key. Bitte Guthaben prüfen.')
          if (resp.status === 404) throw new Error('Nicht gefunden. Eintrag wurde möglicherweise bereits gelöscht.')
          if (resp.status >= 500) throw new Error(`Server-Fehler (${resp.status}). Bitte in 30s erneut versuchen.`)
          throw new Error(detail || `Fehler ${resp.status}`)
        }
        return resp.json()
      } catch (e) {
        lastError = e
        if (e.name === 'TypeError' && attempt < maxRetries) {
          // Network error (e.g. cold-start timeout) — retry
          await new Promise(r => setTimeout(r, 1500 * (attempt + 1)))
          continue
        }
        if (attempt >= maxRetries) throw e
      }
    }
    throw lastError
  }
  const showSuccess = (msg, sticky = false) => {
    setSuccessMsg(msg)
    if (!sticky) setTimeout(() => setSuccessMsg(''), 5000)
  }

  const startLoading = (msg) => { setLoading(true); setLoadingMsg(msg || 'Wird verarbeitet...'); setLoadingProgress(null) }
  const stopLoading = () => { setLoading(false); setLoadingMsg(''); setLoadingProgress(null) }

  const loadDashboard = useCallback(async () => { try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {} }, [])
  const loadCompanies = useCallback(async () => { try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {} }, [])
  const loadLeads = useCallback(async () => { try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {} }, [])
  const loadPosts = useCallback(async () => { try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {} }, [])
  const loadAddressBook = useCallback(async () => { try { const r = await fetchJson(`${API}/data/address-book`); setAddressBook(r.data || []) } catch {} }, [])
  const loadSentEmails = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/sent-emails`); setSentEmails(r.data || []) } catch {} }, [])
  const loadAnalyticsSummary = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/summary`); setAnalyticsSummary(r.data || null) } catch {} }, [])
  const loadAnalyticsFunnel = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/funnel`); setAnalyticsFunnel(r.data || null) } catch {} }, [])
  const loadAuthStatus = useCallback(async () => { try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {} }, [])
  const loadLinkedinSettings = useCallback(async () => {
    try {
      const r = await fetchJson(`${API}/data/settings`)
      const s = r.data || {}
      setLinkedinSettings({ org_id: s.linkedin_org_id || '', has_token: !!(s.linkedin_access_token && s.linkedin_access_token !== '') })
    } catch {}
  }, [])
  const loadSeqCampaigns = useCallback(async () => { try { const r = await fetchJson(`${API}/campaigns/status`); setSeqCampaigns(r.data || []) } catch {} }, [])
  const loadSeqTemplates = useCallback(async () => { try { const r = await fetchJson(`${API}/campaigns/templates`); setSeqTemplates(r.data || []) } catch {} }, [])

  useEffect(() => { loadDashboard(); loadAuthStatus(); loadLinkedinSettings() }, [loadDashboard, loadAuthStatus, loadLinkedinSettings])
  useEffect(() => {
    setError(''); setSuccessMsg('')
    if (section === 'overview') { loadDashboard(); loadLeads(); loadAddressBook(); loadCompanies(); loadAnalyticsSummary() }
    else if (section === 'search') { loadCompanies(); loadLeads() }
    else if (section === 'addressbook') { loadAddressBook(); loadLeads(); loadSentEmails() }
    else if (section === 'campaign') { loadAddressBook(); loadLeads(); loadSeqCampaigns(); loadSeqTemplates() }
    else if (section === 'social') { loadPosts() }
    else if (section === 'analytics') { loadSentEmails(); loadAnalyticsSummary(); loadAnalyticsFunnel() }
    else if (section === 'settings') { loadDashboard(); loadAddressBook() }
  }, [section, loadCompanies, loadLeads, loadPosts, loadAddressBook, loadDashboard])

  // Reset campaign wizard when entering campaign section
  useEffect(() => {
    if (section === 'campaign') {
      setCampStep(1); setCampSelected(new Set()); setCampLeads([])
      setCampActiveLeadId(null); setCampDraftSubject(''); setCampDraftBody('')
      setCampSendSelected(new Set()); setCampDrafting(false)
    }
  }, [section])

  const toggle = (arr, setArr, val) => setArr(prev => prev.includes(val) ? prev.filter(v => v !== val) : [...prev, val])

  // ─── Risk Level Badge ──────────────────────────────────
  const riskBadge = (level) => {
    const map = {
      'low': { cls: 'badge-green', label: 'Niedrig' },
      'medium': { cls: 'badge-yellow', label: 'Mittel' },
      'high': { cls: 'badge-red', label: 'Hoch' },
      'invalid': { cls: 'badge-red', label: 'Ungültig' },
      'unknown': { cls: 'badge-gray', label: '—' },
    }
    const m = map[level] || map['unknown']
    return <span className={`badge ${m.cls}`} title={`E-Mail-Risiko: ${level}`}>{m.label}</span>
  }

  // ─── Analytics Actions ─────────────────────────────────
  const checkReplies = async () => {
    setCheckingReplies(true); setReplyCheckResult(null); setError('')
    try {
      const r = await fetchJson(`${API}/analytics/check-replies`, { method: 'POST' })
      setReplyCheckResult(r)
      showSuccess(`Prüfung abgeschlossen: ${r.replies || 0} Antworten, ${r.unsubscribes || 0} Abmeldungen, ${r.bounces || 0} Bounces`)
      await loadSentEmails()
      await loadAnalyticsSummary()
      await loadAnalyticsFunnel()
    } catch (e) { setError(e.message) }
    setCheckingReplies(false)
  }
  const toggleAnalyticsRow = (id) => setAnalyticsExpanded(prev => ({ ...prev, [id]: !prev[id] }))

  // ─── Actions ────────────────────────────────────────────
  const findCompanies = async () => {
    if (!selIndustries.length || !selRegions.length) { setError('Bitte mindestens eine Branche und eine Region auswählen.'); return }
    startLoading('Unternehmen werden gesucht — kann bis zu 2 Minuten dauern...'); setError('')
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000) // 5 min timeout
      const params = new URLSearchParams()
      selIndustries.forEach(v => params.append('industries', v))
      selRegions.forEach(v => params.append('regions', v))
      selSizes.forEach(v => params.append('sizes', v))
      const resp = await fetch(`${API}/prospecting/find-companies?${params.toString()}`, { method: 'POST', signal: controller.signal })
      clearTimeout(timeout)
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || `Server-Fehler (${resp.status})`)
      }
      const r = await resp.json()
      showSuccess(`${r.total || 0} neue Unternehmen gefunden (${companies.length + (r.total || 0)} gesamt)`, true)
      await loadCompanies()
    } catch (e) {
      if (e.name === 'AbortError') setError('Suche hat zu lange gedauert. Bitte mit weniger Branchen/Regionen erneut versuchen.')
      else setError(e.message)
    }
    stopLoading()
  }
  const clearSearchResults = async () => {
    if (!confirm('Alle Unternehmen und Kontakte aus der aktuellen Suche löschen?')) return
    startLoading('Suchergebnisse werden gelöscht...'); setError('')
    try {
      await fetchJson(`${API}/data/companies`, { method: 'DELETE' })
      await fetchJson(`${API}/data/leads`, { method: 'DELETE' })
      setCompanies([]); setLeads([])
      showSuccess('Suchergebnisse gelöscht')
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const findContacts = async (companyId) => {
    startLoading('Kontakte werden gesucht...'); setError('')
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 3 * 60 * 1000) // 3 min timeout
      const resp = await fetch(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST', signal: controller.signal })
      clearTimeout(timeout)
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `Server-Fehler (${resp.status})`) }
      const r = await resp.json()
      showSuccess(`${r.total || 0} Kontakte`); await loadLeads()
    } catch (e) {
      if (e.name === 'AbortError') setError('Kontaktsuche hat zu lange gedauert. Bitte erneut versuchen.')
      else setError(e.message)
    }
    stopLoading()
  }
  const findAllContacts = async () => {
    if (!companies.length) return
    startLoading(`Kontakte für ${companies.length} Unternehmen werden gesucht...`); setError('')
    let totalNew = 0
    let errors = 0
    for (let i = 0; i < companies.length; i++) {
      setLoadingProgress({ current: i + 1, total: companies.length })
      setLoadingMsg(`Kontakte suchen: ${companies[i].name} (${i + 1}/${companies.length})...`)
      try {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), 3 * 60 * 1000)
        const resp = await fetch(`${API}/prospecting/find-contacts/${companies[i].id}`, { method: 'POST', signal: controller.signal })
        clearTimeout(timeout)
        if (!resp.ok) throw new Error('fail')
        const r = await resp.json()
        totalNew += (r.total || 0)
      } catch { errors++ }
    }
    showSuccess(`${totalNew} neue Kontakte gefunden${errors ? ` (${errors} Fehler)` : ''}`, true)
    await loadLeads()
    stopLoading()
  }
  const verifyEmail = async (leadId) => {
    startLoading('E-Mail wird verifiziert...'); setError('')
    try { const r = await fetchJson(`${API}/prospecting/verify-email/${leadId}`, { method: 'POST' }); showSuccess(`Verifiziert: ${r.data?.email || 'OK'}`); await loadLeads() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const verifyAllEmails = async () => {
    startLoading('E-Mails werden verifiziert...'); setError('')
    // Start polling for progress
    const pollId = setInterval(async () => {
      try {
        const p = await fetchJson(`${API}/prospecting/verify-progress`)
        if (p.running) setLoadingProgress({ current: p.current, total: p.total })
      } catch (_) { /* ignore poll errors */ }
    }, 2000)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 10 * 60 * 1000) // 10 min timeout
      const resp = await fetch(`${API}/prospecting/verify-all`, { method: 'POST', signal: controller.signal })
      clearTimeout(timeout)
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `Server-Fehler (${resp.status})`) }
      const r = await resp.json()
      showSuccess(`${r.verified || 0}/${r.total || 0} verifiziert`)
      await loadLeads()
    } catch (e) {
      if (e.name === 'AbortError') setError('Verifizierung hat zu lange gedauert. Bitte einzelne Kontakte verifizieren.')
      else setError(e.message)
    }
    clearInterval(pollId)
    stopLoading()
  }
  // New: Technical SMTP verification
  const verifyEmailTechnical = async (leadId) => {
    startLoading('Technische E-Mail-Verifizierung (SMTP/MX)...'); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/verify-email-technical/${leadId}`, { method: 'POST' })
      const d = r.data || {}
      showSuccess(`${d.email}: Risiko ${d.risk_level} (${d.verification_method})`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const addToAddressBook = async (leadId) => {
    setError('')
    // Optimistic: immediately show as "in address book"
    const lead = leads.find(l => l.id === leadId)
    if (lead?.email) setAddressBook(prev => [...prev, { id: 'temp-' + leadId, email: lead.email, name: lead.name, company: lead.company, title: lead.title, contact_status: 'active', source: 'verified', email_verified: true }])
    showSuccess('Ins Adressbuch übernommen')
    try { await fetchJson(`${API}/data/address-book/from-lead/${leadId}`, { method: 'POST' }); await loadAddressBook() }
    catch (e) { setError(e.message); await loadAddressBook() }
  }
  const addAllVerifiedToAddressBook = async () => {
    const verified = leads.filter(l => l.email_verified && !abEmails.has(l.email?.toLowerCase()))
    if (!verified.length) { setError('Keine neuen verifizierten Kontakte zum Übernehmen.'); return }
    startLoading(`${verified.length} verifizierte Kontakte werden ins Adressbuch übernommen...`); setError('')
    try {
      const r = await fetchJson(`${API}/data/address-book/from-leads-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: verified.map(l => l.id) })
      })
      showSuccess(`${r.added || 0} Kontakte ins Adressbuch übernommen${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      await loadAddressBook()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const removeFromAddressBook = async (entryId) => {
    try { await fetchJson(`${API}/data/address-book/${entryId}`, { method: 'DELETE' }); await loadAddressBook() }
    catch (e) { setError(e.message) }
  }
  const setContactStatus = async (entryId, newStatus) => {
    setError('')
    // Optimistic update
    setAddressBook(prev => prev.map(a => a.id === entryId ? { ...a, contact_status: newStatus } : a))
    showSuccess(newStatus === 'blocked' ? 'Kontakt gesperrt' : 'Kontakt freigeschaltet')
    try {
      await fetchJson(`${API}/data/address-book/${entryId}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contact_status: newStatus }) })
      await loadAddressBook()
    } catch (e) { setError(e.message); await loadAddressBook() }
  }
  const permanentlyDeleteContact = async (entryId) => {
    if (!confirm('Kontakt endgültig löschen?')) return
    startLoading('Kontakt wird gelöscht...'); setError('')
    try { await fetchJson(`${API}/data/address-book/${entryId}/permanent`, { method: 'DELETE' }); showSuccess('Kontakt gelöscht'); await loadAddressBook() }
    catch (e) { setError(e.message) }
    stopLoading()
  }
  const addManualContact = async (formData) => {
    startLoading('Kontakt wird hinzugefügt...'); setError('')
    try {
      await fetchJson(`${API}/data/address-book`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(formData) })
      showSuccess('Kontakt hinzugefügt'); setShowAddForm(false); await loadAddressBook()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const importCSV = async (file) => {
    startLoading('CSV wird importiert...'); setError('')
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch(`${API}/data/address-book/import-csv`, { method: 'POST', body: formData })
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `Fehler ${resp.status}`) }
      const r = await resp.json()
      showSuccess(`${r.imported || 0} Kontakte importiert${r.skipped ? `, ${r.skipped} übersprungen (Duplikate)` : ''}`)
      await loadAddressBook()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // ── Targeted company search (address book page) ──
  const searchCompany = async () => {
    if (!abSearchQuery.trim()) return
    setAbSearching(true); setAbSearchResult(null); setError('')
    startLoading(`Suche nach "${abSearchQuery.trim()}" — Unternehmen, Kontakte und Verifizierung...`)
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000) // 5 min timeout
      const resp = await fetch(`${API}/prospecting/search-company`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: abSearchQuery.trim() }),
        signal: controller.signal
      })
      clearTimeout(timeout)
      const r = await resp.json()
      if (r.success) {
        setAbSearchResult({ company: r.company, contacts: r.contacts || [], warning: r.warning || null })
        const msg = r.warning || `${r.total_contacts} Kontakte gefunden, ${r.verified_contacts} verifiziert`
        if (r.warning) { setError(r.warning) } else { showSuccess(msg) }
      } else {
        setError(r.message || r.detail || 'Unternehmen nicht gefunden.')
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        setError('Zeitüberschreitung — die Suche hat zu lange gedauert. Bitte erneut versuchen.')
      } else {
        setError(`Verbindungsfehler: ${e.message}. Bitte erneut versuchen.`)
      }
    }
    setAbSearching(false)
    stopLoading()
  }

  const addSearchContactToAB = async (leadId) => {
    startLoading('Wird ins Adressbuch übernommen...'); setError('')
    try {
      await fetchJson(`${API}/data/address-book/from-lead/${leadId}`, { method: 'POST' })
      showSuccess('Ins Adressbuch übernommen')
      await loadAddressBook()
      // Update search results to reflect change
      if (abSearchResult) {
        const updatedContacts = abSearchResult.contacts.map(c =>
          c.id === leadId ? { ...c, _inAddressBook: true } : c
        )
        setAbSearchResult({ ...abSearchResult, contacts: updatedContacts })
      }
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const addAllVerifiedSearchContactsToAB = async () => {
    if (!abSearchResult?.contacts) return
    const verified = abSearchResult.contacts.filter(c => c.email_verified && !abEmails.has(c.email?.toLowerCase()))
    if (!verified.length) return
    startLoading(`${verified.length} verifizierte Kontakte werden ins Adressbuch übernommen...`); setError('')
    try {
      const r = await fetchJson(`${API}/data/address-book/from-leads-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: verified.map(c => c.id) })
      })
      showSuccess(`${r.added || 0} Kontakte ins Adressbuch übernommen${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      await loadAddressBook()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const generatePost = async (topic, platform) => {
    startLoading('Post wird generiert...'); setError('')
    try { await fetchJson(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST' }); showSuccess('Post generiert'); await loadPosts() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const deletePost = async (postId) => {
    try { await fetchJson(`${API}/data/social-posts/${postId}`, { method: 'DELETE' }); await loadPosts() } catch (e) { setError(e.message) }
  }
  const copyPost = async (postId, content) => {
    navigator.clipboard.writeText(content)
    try { await fetchJson(`${API}/data/social-posts/${postId}/mark-copied`, { method: 'POST' }); await loadPosts() } catch {}
    showSuccess('Kopiert')
  }
  const publishToLinkedIn = async (postId) => {
    if (!confirm('Post jetzt auf LinkedIn als Harpocrates veröffentlichen?')) return
    startLoading('Wird auf LinkedIn veröffentlicht...')
    try {
      const r = await fetchJson(`${API}/data/social-posts/${postId}/publish-linkedin`, { method: 'POST' })
      showSuccess('Auf LinkedIn veröffentlicht!')
      await loadPosts()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const saveLinkedinSettings = async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    const payload = {}
    const token = fd.get('linkedin_access_token')
    const orgId = fd.get('linkedin_org_id')
    if (token && token.trim()) payload.linkedin_access_token = token.trim()
    if (orgId !== undefined) payload.linkedin_org_id = (orgId || '').trim()
    if (Object.keys(payload).length === 0) return
    startLoading('LinkedIn-Einstellungen werden gespeichert...')
    try {
      await fetchJson(`${API}/data/settings`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      showSuccess('LinkedIn-Einstellungen gespeichert')
      await loadLinkedinSettings()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const exportCSV = (type) => window.open(`${API}/data/${type}/export`, '_blank')

  const renderPostContent = (text) => {
    if (!text) return ''
    const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // Render markdown bold **text** and *text*
    let rendered = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    rendered = rendered.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>')
    const withLinks = rendered.replace(
      /(https?:\/\/[^\s)<>]+)/g,
      '<a href="$1" target="_blank" rel="noopener noreferrer" class="post-link">$1</a>'
    )
    return withLinks.replace(/\n/g, '<br/>')
  }

  const statusBadge = (status) => {
    const c = { 'Identified':'badge-gray','Email Verified':'badge-green','Email Drafted':'badge-yellow','Email Approved':'badge-blue','Email Sent':'badge-green','Replied':'badge-green','Follow-Up Drafted':'badge-yellow','Follow-Up Sent':'badge-green','Do Not Contact':'badge-red','Closed':'badge-gray' }
    return <span className={`badge ${c[status]||'badge-gray'}`}>{status}</span>
  }
  const unverifiedLeads = leads.filter(l => !l.email_verified && l.email)
  const verifiedLeads = leads.filter(l => l.email_verified)
  const abEmails = new Set(addressBook.map(a => a.email?.toLowerCase()))

  // Filtered leads for search page
  const leadsWithEmail = leads.filter(l => l.email)
  const leadsNoEmail = leads.filter(l => !l.email)
  const filteredLeads = leads.filter(l => {
    if (searchLeadsFilter === 'with_email' && !l.email) return false
    if (searchLeadsFilter === 'verified' && !l.email_verified) return false
    if (searchLeadsFilter === 'unverified' && (l.email_verified || !l.email)) return false
    if (searchLeadsFilter === 'no_email' && l.email) return false
    if (searchLeadsQuery) {
      const q = searchLeadsQuery.toLowerCase()
      return (l.name?.toLowerCase().includes(q) || l.company?.toLowerCase().includes(q) || l.email?.toLowerCase().includes(q) || l.title?.toLowerCase().includes(q))
    }
    return true
  })

  // Group leads by company for display
  const leadsGrouped = filteredLeads.reduce((acc, l) => {
    const key = l.company || 'Unbekannt'
    if (!acc[key]) acc[key] = []
    acc[key].push(l)
    return acc
  }, {})

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

  // ─── Campaign Wizard Functions ───────────────────────────
  const activeContacts = addressBook.filter(a => (a.contact_status || 'active') === 'active' && a.email)

  const toggleCampSelect = (id) => {
    setCampSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const toggleCampSelectAll = () => {
    if (campSelected.size === activeContacts.length) {
      setCampSelected(new Set())
    } else {
      setCampSelected(new Set(activeContacts.map(a => a.id)))
    }
  }

  // Step 1 → Step 2: import selected contacts as leads, then batch-draft
  const campGoToStep2 = async () => {
    if (campSelected.size === 0) { setError('Bitte mindestens einen Kontakt auswählen.'); return }
    startLoading('Kontakte werden importiert...'); setError('')

    // Import selected address book contacts as leads (skip duplicates)
    const selectedContacts = activeContacts.filter(a => campSelected.has(a.id))
    const newLeadIds = []

    // First: check existing leads to avoid duplicates
    const existingLeads = leads.length > 0 ? leads : (await fetchJson(`${API}/data/leads`).then(r => r.data || []).catch(() => []))
    const existingEmails = new Set(existingLeads.map(l => l.email?.toLowerCase()).filter(Boolean))

    for (const contact of selectedContacts) {
      // If lead with same email already exists, reuse it
      const existingLead = existingLeads.find(l => l.email?.toLowerCase() === contact.email?.toLowerCase())
      if (existingLead) {
        newLeadIds.push(existingLead.id)
        continue
      }
      try {
        const r = await fetchJson(`${API}/data/leads`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: contact.name, title: contact.title, company: contact.company, email: contact.email, email_verified: contact.email_verified, linkedin_url: contact.linkedin_url, source: 'Kampagne', status: 'Identified' })
        })
        if (r.data?.id) newLeadIds.push(r.data.id)
      } catch {}
    }

    if (newLeadIds.length === 0) {
      setError('Keine Kontakte konnten importiert werden.')
      stopLoading()
      return
    }

    // Now batch-draft emails for all new leads
    setLoadingMsg(`${newLeadIds.length} E-Mail-Entwürfe werden erstellt (personalisiert per KI)...`)
    setCampDrafting(true)

    try {
      const r = await fetchJson(`${API}/email/draft-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: newLeadIds })
      })
      showSuccess(`${r.created || 0} Entwürfe erstellt${r.failed ? `, ${r.failed} fehlgeschlagen` : ''}`)
    } catch (e) {
      setError(`Fehler beim Erstellen der Entwürfe: ${e.message}`)
    }

    setCampDrafting(false)

    // Reload leads and filter for our campaign leads
    const leadsResp = await fetchJson(`${API}/data/leads`)
    const allLeads = leadsResp.data || []
    const campaignLeads = allLeads.filter(l => newLeadIds.includes(l.id))
    setCampLeads(campaignLeads)

    if (campaignLeads.length > 0) {
      setCampActiveLeadId(campaignLeads[0].id)
      const draft = campaignLeads[0].drafted_email
      setCampDraftSubject(draft?.subject || '')
      setCampDraftBody(draft?.body || '')
    }

    stopLoading()
    setCampStep(2)
  }

  // Select a lead in step 2 left panel
  const campSelectLead = (lead) => {
    setCampActiveLeadId(lead.id)
    const draft = lead.drafted_email
    setCampDraftSubject(draft?.subject || '')
    setCampDraftBody(draft?.body || '')
  }

  // Save edits for current lead's draft
  const campSaveDraft = async () => {
    if (!campActiveLeadId) return
    startLoading('Entwurf wird gespeichert...'); setError('')
    try {
      await fetchJson(`${API}/email/update-draft/${campActiveLeadId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: campDraftSubject, body: campDraftBody })
      })
      showSuccess('Entwurf gespeichert')
      // Reload campaign leads
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      const updatedCampLeads = allLeads.filter(l => campLeads.some(cl => cl.id === l.id))
      setCampLeads(updatedCampLeads)
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // Regenerate draft for a single lead
  const campRegenerateDraft = async (leadId) => {
    startLoading('Entwurf wird neu generiert...'); setError('')
    try {
      // Delete old draft first
      await fetchJson(`${API}/email/draft/${leadId}`, { method: 'DELETE' }).catch(() => {})
      await fetchJson(`${API}/email/draft/${leadId}`, { method: 'POST' })
      showSuccess('Neuer Entwurf erstellt')
      // Reload
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      const updatedCampLeads = allLeads.filter(l => campLeads.some(cl => cl.id === l.id))
      setCampLeads(updatedCampLeads)
      const updated = updatedCampLeads.find(l => l.id === leadId)
      if (updated) {
        setCampDraftSubject(updated.drafted_email?.subject || '')
        setCampDraftBody(updated.drafted_email?.body || '')
      }
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // Step 2 → Step 3: go to approval
  const campGoToStep3 = () => {
    const withDrafts = campLeads.filter(l => l.drafted_email)
    if (withDrafts.length === 0) { setError('Noch keine Entwürfe vorhanden.'); return }
    setCampStep(3)
  }

  // Approve/unapprove single lead
  const campApprove = async (leadId) => {
    // Optimistic: immediately mark as approved
    setCampLeads(prev => prev.map(l => l.id === leadId ? { ...l, drafted_email: { ...l.drafted_email, is_approved: true } } : l))
    try {
      await fetchJson(`${API}/email/approve/${leadId}`, { method: 'POST' })
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      setCampLeads(allLeads.filter(l => campLeads.some(cl => cl.id === l.id)))
    } catch (e) { setError(e.message) }
  }
  const campUnapprove = async (leadId) => {
    try {
      await fetchJson(`${API}/email/unapprove/${leadId}`, { method: 'POST' })
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      setCampLeads(allLeads.filter(l => campLeads.some(cl => cl.id === l.id)))
    } catch (e) { setError(e.message) }
  }

  // Approve all
  const campApproveAll = async () => {
    const ids = campLeads.filter(l => l.drafted_email && !l.drafted_email.is_approved).map(l => l.id)
    if (ids.length === 0) return
    startLoading('Alle Entwürfe werden freigegeben...'); setError('')
    try {
      await fetchJson(`${API}/email/approve-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: ids })
      })
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      setCampLeads(allLeads.filter(l => campLeads.some(cl => cl.id === l.id)))
      showSuccess('Alle Entwürfe freigegeben')
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // Step 3 → Step 4: prepare send list
  const campGoToStep4 = () => {
    const approved = campLeads.filter(l => l.drafted_email?.is_approved && !l.date_email_sent)
    if (approved.length === 0) { setError('Keine freigegebenen E-Mails zum Versenden.'); return }
    setCampSendSelected(new Set(approved.map(l => l.id)))
    setCampStep(4)
  }

  // Toggle send selection
  const toggleSendSelect = (id) => {
    setCampSendSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  const toggleSendSelectAll = () => {
    const approved = campLeads.filter(l => l.drafted_email?.is_approved && !l.date_email_sent)
    if (campSendSelected.size === approved.length) {
      setCampSendSelected(new Set())
    } else {
      setCampSendSelected(new Set(approved.map(l => l.id)))
    }
  }

  // Send selected emails
  const campSendEmails = async () => {
    if (campSendSelected.size === 0) { setError('Keine E-Mails ausgewählt.'); return }
    if (!authStatus?.authenticated) { setError('Bitte zuerst mit Google verbinden.'); return }

    const count = campSendSelected.size
    if (!confirm(`${count} E-Mail${count > 1 ? 's' : ''} jetzt senden?\n\nHinweis: Zwischen den E-Mails wird 30–90 Sekunden gewartet (Google API Rate Limit).`)) return

    startLoading(`${count} E-Mails werden gesendet (30–90s Pause zwischen Sendungen)...`); setError('')
    try {
      const r = await fetchJson(`${API}/email/send-batch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: Array.from(campSendSelected) })
      })
      if (r.sent > 0) {
        showSuccess(`${r.sent} gesendet${r.failed ? `, ${r.failed} fehlgeschlagen` : ''}${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      } else if (r.failed > 0) {
        setError(`Versand fehlgeschlagen: ${r.failed} Fehler${r.errors ? ' \u2014 ' + r.errors.join('; ') : ''}. ${r.skipped ? r.skipped + ' übersprungen.' : ''}`)
      } else if (r.skipped > 0) {
        setError(`Keine E-Mails versendet (${r.skipped} übersprungen). Möglicherweise wurden die E-Mails nicht freigegeben oder bereits versendet.`)
      } else {
        setError('Keine E-Mails versendet. Bitte den Kampagnen-Status prüfen.')
      }
      if (r.errors && r.errors.length > 0 && r.sent > 0) {
        setError(`Teilweise Fehler: ${r.errors.join('; ')}`)
      }
      // Reload
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      setCampLeads(allLeads.filter(l => campLeads.some(cl => cl.id === l.id)))
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // ─── Campaign Sequence Functions ──────────────────────────
  const seqDraftNext = async (leadId) => {
    startLoading('Nächster Sequenz-Schritt wird erstellt...'); setError('')
    try {
      const r = await fetchJson(`${API}/campaigns/draft-next/${leadId}`, { method: 'POST' })
      showSuccess(`Schritt ${r.step} (${r.type}) erstellt`)
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const seqApproveStep = async (leadId, stepNum) => {
    try {
      await fetchJson(`${API}/campaigns/approve-step/${leadId}/${stepNum}`, { method: 'POST' })
      showSuccess('Schritt freigegeben')
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
  }
  const seqPause = async (leadId) => {
    try { await fetchJson(`${API}/campaigns/pause/${leadId}`, { method: 'POST' }); await loadSeqCampaigns() } catch (e) { setError(e.message) }
  }
  const seqResume = async (leadId) => {
    try { await fetchJson(`${API}/campaigns/resume/${leadId}`, { method: 'POST' }); await loadSeqCampaigns() } catch (e) { setError(e.message) }
  }
  const seqStartCampaign = async (leadIds) => {
    startLoading('Kampagnen-Sequenz wird gestartet...'); setError('')
    try {
      const r = await fetchJson(`${API}/campaigns/start`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_ids: leadIds })
      })
      showSuccess(`${r.started} Sequenzen gestartet${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const seqDraftAllNext = async () => {
    startLoading('Alle nächsten Schritte werden erstellt...'); setError('')
    try {
      const r = await fetchJson(`${API}/campaigns/draft-all-next`, { method: 'POST' })
      showSuccess(`${r.drafted} Entwürfe erstellt${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const menuItems = [
    { id: 'overview', icon: '📋', label: 'Übersicht' },
    { id: 'search', icon: '🔍', label: 'Suche' },
    { id: 'addressbook', icon: '📖', label: 'Adressbuch' },
    { id: 'campaign', icon: '📧', label: 'Kampagne' },
    { id: 'analytics', icon: '📊', label: 'Analytics' },
    { id: 'social', icon: '💬', label: 'LinkedIn' },
    { id: 'settings', icon: '⚙️', label: 'Einstellungen' },
  ]

  // Step indicator for campaign wizard
  const WizardSteps = () => {
    const steps = [
      { num: 1, label: 'Kontakte' },
      { num: 2, label: 'Entwürfe' },
      { num: 3, label: 'Freigabe' },
      { num: 4, label: 'Versand' },
    ]
    return (
      <div className="wizard-steps">
        {steps.map((s, i) => (
          <div key={s.num} className={`wizard-step ${campStep === s.num ? 'active' : ''} ${campStep > s.num ? 'done' : ''}`} onClick={() => { if (campStep > s.num) setCampStep(s.num) }} style={campStep > s.num ? {cursor:'pointer'} : {}}>
            <div className="wizard-num">{campStep > s.num ? '✓' : s.num}</div>
            <span className="wizard-label">{s.label}</span>
            {i < steps.length - 1 && <div className="wizard-line" />}
          </div>
        ))}
      </div>
    )
  }

  // Sequence step type label
  const stepTypeLabel = (type) => {
    const map = { 'initial': 'Initial', 'follow_up_1': 'Follow-Up 1', 'follow_up_2': 'Follow-Up 2', 'follow_up_3': 'Follow-Up 3', 'breakup': 'Breakup' }
    return map[type] || type
  }
  const stepStatusBadge = (status) => {
    const map = { 'pending': 'badge-gray', 'drafted': 'badge-yellow', 'approved': 'badge-blue', 'sent': 'badge-green', 'skipped': 'badge-gray' }
    const labels = { 'pending': 'Ausstehend', 'drafted': 'Entwurf', 'approved': 'Freigegeben', 'sent': 'Gesendet', 'skipped': 'Übersprungen' }
    return <span className={`badge ${map[status] || 'badge-gray'}`}>{labels[status] || status}</span>
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header"><img src={harpoLogo} alt="Harpocrates" className="sidebar-logo" /></div>
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
        {successMsg && <div className="msg msg-success">{successMsg} <button onClick={() => setSuccessMsg('')} style={{background:'none',border:'none',color:'#166534',cursor:'pointer',fontSize:'1.1rem',marginLeft:'auto'}}>×</button></div>}
        {loading && <div className="msg msg-loading">
          <span className="spinner" />
          <div style={{flex:1}}>
            <div>{loadingMsg || 'Wird verarbeitet...'}</div>
            {loadingProgress && (
              <div className="progress-bar-container">
                <div className="progress-bar-fill" style={{width: `${Math.round((loadingProgress.current / loadingProgress.total) * 100)}%`}} />
              </div>
            )}
          </div>
        </div>}

        {/* === UEBERSICHT ========================================= */}
        {section === 'overview' && (
          <div key="overview">
            <h1 className="page-title">Übersicht</h1>
            <p className="page-desc">Aktueller Status und nächste Schritte</p>

            {authStatus && !authStatus.authenticated && (
              <div className="card" style={{background:'#fffbeb',border:'1px solid #fde68a',marginBottom:'1rem'}}>
                <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:'0.75rem',flexWrap:'wrap'}}>
                  <div><strong>⚠ Google nicht verbunden</strong><p className="sub" style={{margin:'0.25rem 0 0'}}>E-Mail-Versand erfordert Google-Anbindung.</p></div>
                  <a href="/api/auth/google/login" className="btn btn-primary">Google verbinden</a>
                </div>
              </div>
            )}

            {stats && (
              <div className="stats-grid" style={{marginBottom:'1.25rem'}}>
                <div className="stat-card"><div className="stat-val">{companies.length}</div><div className="stat-lbl">Unternehmen</div></div>
                <div className="stat-card"><div className="stat-val">{leads.length}</div><div className="stat-lbl">Kontakte</div></div>
                <div className="stat-card"><div className="stat-val">{leads.filter(l => l.email_verified).length}</div><div className="stat-lbl">Verifiziert</div></div>
                <div className="stat-card"><div className="stat-val">{addressBook.length}</div><div className="stat-lbl">Adressbuch</div></div>
                <div className="stat-card"><div className="stat-val">{stats.emails_sent || 0}</div><div className="stat-lbl">Gesendet</div></div>
                <div className="stat-card" style={analyticsSummary?.total_replied > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{analyticsSummary?.total_replied || 0}</div><div className="stat-lbl">Antworten</div></div>
              </div>
            )}

            <div className="card">
              <h2>Nächste Schritte</h2>
              <div className="overview-actions">
                {companies.length === 0 && (
                  <div className="overview-action-item" onClick={() => setSection('search')}>
                    <div className="overview-action-icon">🔍</div>
                    <div className="overview-action-content"><strong>Unternehmen suchen</strong><span className="sub">Starte mit der Suche nach relevanten Unternehmen</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                {companies.length > 0 && leads.length === 0 && (
                  <div className="overview-action-item" onClick={() => setSection('search')}>
                    <div className="overview-action-icon">👥</div>
                    <div className="overview-action-content"><strong>Kontakte finden</strong><span className="sub">{companies.length} Unternehmen gefunden — jetzt Ansprechpartner suchen</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                {leads.filter(l => !l.email_verified && l.email).length > 0 && (
                  <div className="overview-action-item" onClick={() => setSection('search')}>
                    <div className="overview-action-icon">✉️</div>
                    <div className="overview-action-content"><strong>{leads.filter(l => !l.email_verified && l.email).length} Kontakte verifizieren</strong><span className="sub">E-Mail-Adressen prüfen für die Übernahme ins Adressbuch</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                {leads.filter(l => l.email_verified && !abEmails.has(l.email?.toLowerCase())).length > 0 && (
                  <div className="overview-action-item" onClick={() => setSection('search')}>
                    <div className="overview-action-icon">📖</div>
                    <div className="overview-action-content"><strong>{leads.filter(l => l.email_verified && !abEmails.has(l.email?.toLowerCase())).length} ins Adressbuch übernehmen</strong><span className="sub">Verifizierte Kontakte bereit zur Übernahme</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                {addressBook.filter(a => (a.contact_status || 'active') === 'active' && a.email).length > 0 && (
                  <div className="overview-action-item" onClick={() => setSection('campaign')}>
                    <div className="overview-action-icon">📧</div>
                    <div className="overview-action-content"><strong>Kampagne starten</strong><span className="sub">{addressBook.filter(a => (a.contact_status || 'active') === 'active' && a.email).length} nutzbare Kontakte</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                {stats?.emails_sent > 0 && (
                  <div className="overview-action-item" onClick={() => setSection('analytics')}>
                    <div className="overview-action-icon">📊</div>
                    <div className="overview-action-content"><strong>Antworten prüfen</strong><span className="sub">{stats.emails_sent} E-Mails versendet</span></div>
                    <span className="overview-action-arrow">→</span>
                  </div>
                )}
                <div className="overview-action-item" onClick={() => setSection('social')}>
                  <div className="overview-action-icon">💬</div>
                  <div className="overview-action-content"><strong>LinkedIn-Post erstellen</strong><span className="sub">Thought Leadership und Regulatory Updates</span></div>
                  <span className="overview-action-arrow">→</span>
                </div>
              </div>
            </div>

            {(leads.length > 0 || addressBook.length > 0) && (
              <div className="card">
                <h2>Pipeline</h2>
                <div className="overview-pipeline">
                  {[
                    { label: 'Identifiziert', count: leads.length, color: '#6b7280' },
                    { label: 'Verifiziert', count: leads.filter(l => l.email_verified).length, color: '#3b82f6' },
                    { label: 'Im Adressbuch', count: addressBook.length, color: '#8b5cf6' },
                    { label: 'Gesendet', count: stats?.emails_sent || 0, color: '#f59e0b' },
                    { label: 'Antworten', count: analyticsSummary?.total_replied || 0, color: '#22c55e' },
                  ].map(stage => {
                    const max = Math.max(leads.length, 1)
                    const pct = Math.round((stage.count / max) * 100)
                    return (
                      <div key={stage.label} style={{display:'flex',alignItems:'center',gap:'0.75rem'}}>
                        <div style={{width:'100px',fontSize:'0.8rem',color:'#6b7280',textAlign:'right'}}>{stage.label}</div>
                        <div style={{flex:1,background:'#f3f4f6',borderRadius:'0.25rem',height:'24px',overflow:'hidden'}}>
                          <div style={{width:`${pct}%`,height:'100%',background:stage.color,borderRadius:'0.25rem',transition:'width 0.5s',minWidth:stage.count > 0 ? '2px' : 0}} />
                        </div>
                        <div style={{width:'40px',fontSize:'0.8rem',fontWeight:600}}>{stage.count}</div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}

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
                <button className="btn btn-primary" disabled={loading || !selIndustries.length || !selRegions.length} onClick={findCompanies}>{selIndustries.length > 0 && selRegions.length > 0 ? `${selIndustries.length} Branche${selIndustries.length > 1 ? 'n' : ''}, ${selRegions.length} Region${selRegions.length > 1 ? 'en' : ''} durchsuchen` : 'Suche starten'}</button>
                {(selIndustries.length > 0 || selRegions.length > 0 || selSizes.length > 0) && <button className="btn btn-ghost" onClick={() => { setSelIndustries([]); setSelRegions([]); setSelSizes([]) }}>Filter zurücksetzen</button>}
                {(companies.length > 0 || leads.length > 0) && <button className="btn btn-ghost" style={{color:'#ef4444'}} onClick={clearSearchResults}>Alle Ergebnisse löschen</button>}
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
                        {verifiedLeads.filter(l => !abEmails.has(l.email?.toLowerCase())).length > 0 && <button className="btn btn-primary btn-sm" disabled={loading} onClick={addAllVerifiedToAddressBook}>Alle ins Adressbuch ({verifiedLeads.filter(l => !abEmails.has(l.email?.toLowerCase())).length})</button>}
                      </div>
                    </div>
                    {/* Filter-Bar für Kontakte */}
                    {leads.length > 0 && (
                      <div className="leads-filter-bar">
                        <input
                          type="text"
                          placeholder="Kontakte durchsuchen..."
                          value={searchLeadsQuery}
                          onChange={e => setSearchLeadsQuery(e.target.value)}
                          className="leads-search-input"
                        />
                        <div className="filter-bar" style={{border:'none',padding:0,margin:0}}>
                          <button className={`btn btn-sm ${searchLeadsFilter === 'with_email' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSearchLeadsFilter('with_email')}>Mit E-Mail ({leadsWithEmail.length})</button>
                          <button className={`btn btn-sm ${searchLeadsFilter === 'verified' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSearchLeadsFilter('verified')}>✓ ({verifiedLeads.length})</button>
                          <button className={`btn btn-sm ${searchLeadsFilter === 'unverified' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSearchLeadsFilter('unverified')}>Offen ({unverifiedLeads.length})</button>
                          <button className={`btn btn-sm ${searchLeadsFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSearchLeadsFilter('all')}>Alle ({leads.length})</button>
                          {leadsNoEmail.length > 0 && <button className={`btn btn-sm ${searchLeadsFilter === 'no_email' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSearchLeadsFilter('no_email')}>Ohne E-Mail ({leadsNoEmail.length})</button>}
                          <button className={`btn btn-sm ${leadsGroupByCompany ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => setLeadsGroupByCompany(!leadsGroupByCompany)} title="Nach Firma gruppieren">🏢</button>
                        </div>
                      </div>
                    )}
                    <div className="list">
                      {leadsGroupByCompany && leads.length > 0 ? (
                        Object.entries(leadsGrouped).sort(([,a],[,b]) => b.length - a.length).map(([company, companyLeads]) => (
                          <div key={company} className="leads-company-group">
                            <div className="leads-company-header">
                              <strong>{company}</strong>
                              <span className="sub">{companyLeads.length} Kontakte · {companyLeads.filter(l => l.email_verified).length} verifiziert</span>
                            </div>
                            {companyLeads.map(l => (
                              <div key={l.id} className="list-item" style={{paddingLeft:'0.5rem'}}>
                                <div className="list-main">
                                  <strong>{l.name}</strong>
                                  <span className="sub">{l.title}</span>
                                  <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}
                                    {l.email_risk_level && l.email_risk_level !== 'unknown' && <>{' '}{riskBadge(l.email_risk_level)}</>}
                                    {l.email_smtp_verified && <span className="verified" title="SMTP-verifiziert">⚡</span>}
                                    {l.email_is_catch_all && <span className="badge badge-yellow" style={{fontSize:'0.6rem',padding:'1px 4px'}} title="Catch-All-Domain">CA</span>}
                                    {l.linkedin_url && <>{' '}<a href={l.linkedin_url} target="_blank" rel="noopener noreferrer" className="post-link" style={{fontSize:'0.6rem'}}>in</a></>}
                                  </span>
                                  {l.verification_notes && <span className="sub verify-notes" title={l.verification_notes}>📝 {l.verification_notes.split(' | ')[0]}</span>}
                                </div>
                                <div className="list-actions">
                                  {l.email && !l.email_verified && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verifizieren</button>}
                                  {l.email && l.email_verified && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)} title="Erneut verifizieren">↻</button>}
                                  {l.email && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => verifyEmailTechnical(l.id)} title="Technische SMTP/MX-Prüfung">SMTP</button>}
                                  {l.email_verified && !abEmails.has(l.email?.toLowerCase()) && <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => addToAddressBook(l.id)} title="Ins Adressbuch">📖+</button>}
                                  {l.email_verified && abEmails.has(l.email?.toLowerCase()) && <span className="badge badge-green">Im AB</span>}
                                </div>
                              </div>
                            ))}
                          </div>
                        ))
                      ) : (
                        <>
                          {filteredLeads.slice(0, leadsDisplayLimit).map(l => (
                            <div key={l.id} className="list-item">
                              <div className="list-main">
                                <strong>{l.name}</strong>
                                <span className="sub">{l.title} · {l.company}</span>
                                <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}
                                  {l.email_risk_level && l.email_risk_level !== 'unknown' && <>{' '}{riskBadge(l.email_risk_level)}</>}
                                  {l.email_smtp_verified && <span className="verified" title="SMTP-verifiziert">⚡</span>}
                                  {l.email_is_catch_all && <span className="badge badge-yellow" style={{fontSize:'0.6rem',padding:'1px 4px'}} title="Catch-All-Domain">CA</span>}
                                  {l.linkedin_url && <>{' '}<a href={l.linkedin_url} target="_blank" rel="noopener noreferrer" className="post-link" style={{fontSize:'0.6rem'}}>in</a></>}
                                </span>
                                {l.verification_notes && <span className="sub verify-notes" title={l.verification_notes}>📝 {l.verification_notes.split(' | ')[0]}</span>}
                              </div>
                              <div className="list-actions">
                                {l.email && !l.email_verified && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verifizieren</button>}
                                {l.email && l.email_verified && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)} title="Erneut verifizieren">↻</button>}
                                {l.email && <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => verifyEmailTechnical(l.id)} title="Technische SMTP/MX-Prüfung">SMTP</button>}
                                {l.email_verified && !abEmails.has(l.email?.toLowerCase()) && <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => addToAddressBook(l.id)} title="Ins Adressbuch">📖+</button>}
                                {l.email_verified && abEmails.has(l.email?.toLowerCase()) && <span className="badge badge-green">Im AB</span>}
                              </div>
                            </div>
                          ))}
                          {filteredLeads.length > leadsDisplayLimit && (
                            <button className="btn btn-secondary" style={{margin:'0.5rem auto',display:'block'}} onClick={() => setLeadsDisplayLimit(prev => prev + 50)}>
                              Weitere {Math.min(50, filteredLeads.length - leadsDisplayLimit)} von {filteredLeads.length - leadsDisplayLimit} anzeigen
                            </button>
                          )}
                        </>
                      )}
                      {leads.length === 0 && <p className="empty">Keine Kontakte.</p>}
                      {leads.length > 0 && filteredLeads.length === 0 && <p className="empty">Keine Kontakte für diesen Filter.</p>}
                    </div>
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

            {/* ── Gezielte Unternehmenssuche ── */}
            <div className="card">
              <div className="card-header">
                <h2>Unternehmen suchen</h2>
              </div>
              <p className="card-desc">Gezielt nach einem Unternehmen suchen und relevante Ansprechpartner finden, verifizieren und ins Adressbuch übernehmen.</p>
              <div className="search-inline">
                <input
                  type="text"
                  placeholder="Unternehmensname eingeben (z.B. Siemens, Deutsche Bank, SAP...)"
                  value={abSearchQuery}
                  onChange={e => setAbSearchQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !abSearching && abSearchQuery.trim() && searchCompany()}
                  disabled={abSearching}
                  className="search-input-wide"
                />
                <button className="btn btn-primary" disabled={abSearching || !abSearchQuery.trim()} onClick={searchCompany}>
                  {abSearching ? 'Suche läuft...' : 'Suchen'}
                </button>
                {abSearchResult && (
                  <button className="btn btn-ghost" onClick={() => { setAbSearchResult(null); setAbSearchQuery('') }}>Zurücksetzen</button>
                )}
              </div>

              {/* Search Results */}
              {abSearchResult && (
                <div className="search-results">
                  <div className="search-result-company">
                    <strong>{abSearchResult.company.name}</strong>
                    <span className="sub">{abSearchResult.company.industry} · {abSearchResult.company.country} · {abSearchResult.company.employee_count?.toLocaleString()} Mitarbeiter</span>
                    {abSearchResult.company.website && <a href={abSearchResult.company.website} target="_blank" rel="noopener noreferrer" className="sub link">{abSearchResult.company.website}</a>}
                  </div>
                  <div className="search-result-contacts-header">
                    <h3>Gefundene Kontakte ({abSearchResult.contacts.length})</h3>
                    <div className="card-actions">
                      {abSearchResult.contacts.filter(c => c.email_verified && !abEmails.has(c.email?.toLowerCase())).length > 0 && (
                        <button className="btn btn-primary btn-sm" disabled={loading} onClick={addAllVerifiedSearchContactsToAB}>
                          Alle Verifizierten ins Adressbuch ({abSearchResult.contacts.filter(c => c.email_verified && !abEmails.has(c.email?.toLowerCase())).length})
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="list">
                    {abSearchResult.contacts.map(c => (
                      <div key={c.id} className="list-item">
                        <div className="list-main">
                          <strong>{c.name}</strong>
                          <span className="sub">{c.title} · {c.company}</span>
                          <span className="sub">
                            {c.email || '—'}
                            {c.email_verified && <span className="verified">✓</span>}
                            {c.email_risk_level && c.email_risk_level !== 'unknown' && <>{' '}{riskBadge(c.email_risk_level)}</>}
                          </span>
                        </div>
                        <div className="list-actions">
                          {statusBadge(c.status)}
                          {c.email_verified && !abEmails.has(c.email?.toLowerCase())
                            ? <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => addSearchContactToAB(c.id)}>Ins Adressbuch</button>
                            : c.email_verified && abEmails.has(c.email?.toLowerCase())
                              ? <span className="badge badge-green">Im Adressbuch</span>
                              : !c.email
                                ? <span className="badge badge-gray">Keine E-Mail</span>
                                : <span className="badge badge-yellow">Verifizierung ausstehend</span>
                          }
                        </div>
                      </div>
                    ))}
                    {abSearchResult.contacts.length === 0 && <p className="empty">Keine Kontakte gefunden.</p>}
                  </div>
                </div>
              )}
            </div>

            {/* ── Adressbuch-Kontakte ── */}
            <div className="card">
              <div className="card-header">
                <h2>Kontakte ({addressBook.length})</h2>
                <div className="card-actions">
                  {addressBook.filter(a => (a.contact_status || 'active') === 'active' && a.email).length > 0 && (
                    <button className="btn btn-secondary" onClick={() => { setSection('campaign'); setCampStep(1) }}>
                      ✉ Kampagne ({addressBook.filter(a => (a.contact_status || 'active') === 'active' && a.email).length})
                    </button>
                  )}
                  {addressBook.length > 0 && <button className="btn btn-ghost" onClick={() => exportCSV('address-book')}>CSV ↓</button>}
                  <label className="btn btn-ghost" style={{cursor:'pointer'}}>
                    CSV ↑ <input type="file" accept=".csv" style={{display:'none'}} onChange={e => { if (e.target.files[0]) { importCSV(e.target.files[0]); e.target.value = '' } }} />
                  </label>
                  <button className="btn btn-primary" onClick={() => setShowAddForm(!showAddForm)}>{showAddForm ? 'Abbrechen' : '+ Kontakt'}</button>
                </div>
              </div>
              {addressBook.length > 0 && (
                <div className="filter-bar">
                  <button className={`btn btn-sm ${abFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('all')}>Alle ({addressBook.length})</button>
                  <button className={`btn btn-sm ${abFilter === 'active' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('active')}>Nutzbar ({addressBook.filter(a => (a.contact_status || 'active') === 'active').length})</button>
                  <button className={`btn btn-sm ${abFilter === 'blocked' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAbFilter('blocked')}>Gesperrt ({addressBook.filter(a => a.contact_status === 'blocked').length})</button>
                  <button className={`btn btn-sm ${abGroupByCompany ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => setAbGroupByCompany(!abGroupByCompany)} title="Nach Firma gruppieren">🏢</button>
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
                {(() => {
                  const abFiltered = addressBook.filter(a => abFilter === 'all' || (abFilter === 'active' ? (a.contact_status || 'active') === 'active' : a.contact_status === 'blocked'))
                  const renderRow = (a, grouped) => {
                    const isBlocked = a.contact_status === 'blocked'
                    // Find matching sent email for last activity
                    const matchingSent = sentEmails.find(e => e.email?.toLowerCase() === a.email?.toLowerCase())
                    const lastActivity = matchingSent?.reply_received ? 'Antwort' : matchingSent?.date_email_sent ? `Gesendet ${matchingSent.date_email_sent.split('T')[0]}` : null
                          return (
                            <div key={a.id} className={`list-item ${isBlocked ? 'list-item-blocked' : ''}`} style={grouped ? {paddingLeft:'0.5rem'} : {}}>
                              <div className="list-main">
                                <strong>{a.name}</strong>
                                <span className="sub">{grouped ? a.title : `${a.title} · ${a.company}`}</span>
                                <span className="sub">
                                  {a.email}{a.email_verified && <span className="verified">✓</span>}
                                  {a.linkedin_url && <>{' '}<a href={a.linkedin_url} target="_blank" rel="noopener noreferrer" className="post-link" style={{fontSize:'0.65rem'}}>LinkedIn</a></>}
                                </span>
                                {lastActivity && <span className="sub" style={{color: matchingSent?.reply_received ? '#22c55e' : '#6b7280'}}>Letzte Aktivität: {lastActivity}</span>}
                              </div>
                              <div className="list-actions">
                                <span className={`badge ${a.source === 'verified' ? 'badge-green' : 'badge-blue'}`}>{a.source === 'verified' ? '✓' : '✎'}</span>
                                {isBlocked
                                  ? <button className="btn btn-ghost btn-sm" style={{fontSize:'0.85rem'}} disabled={loading} onClick={() => setContactStatus(a.id, 'active')} title="Freischalten">🔓</button>
                                  : <button className="btn btn-ghost btn-sm" style={{fontSize:'0.85rem'}} disabled={loading} onClick={() => setContactStatus(a.id, 'blocked')} title="Sperren">🔒</button>
                                }
                                <span className="action-separator" />
                                <button className="btn btn-ghost btn-sm btn-danger-subtle" disabled={loading} onClick={() => permanentlyDeleteContact(a.id)} title="Endgültig löschen">×</button>
                              </div>
                            </div>
                          )
                  }
                  if (abGroupByCompany && abFiltered.length > 0) {
                    const abGrouped = abFiltered.reduce((acc, a) => { const k = a.company || 'Sonstige'; if (!acc[k]) acc[k] = []; acc[k].push(a); return acc }, {})
                    return Object.entries(abGrouped).sort(([,a],[,b]) => b.length - a.length).map(([company, contacts]) => (
                      <div key={company} className="leads-company-group">
                        <div className="leads-company-header">
                          <strong>{company}</strong>
                          <span className="sub">{contacts.length} Kontakte</span>
                        </div>
                        {contacts.map(a => renderRow(a, true))}
                      </div>
                    ))
                  }
                  return abFiltered.map(a => renderRow(a, false))
                })()}
                {addressBook.length === 0 && <div className="empty-cta"><p>Adressbuch ist leer.</p><button className="btn btn-secondary" onClick={() => setSection('search')}>Zur Suche →</button><span className="sub">Oder oben manuell eintragen.</span></div>}
                {addressBook.length > 0 && addressBook.filter(a => abFilter === 'all' || (abFilter === 'active' ? (a.contact_status || 'active') === 'active' : a.contact_status === 'blocked')).length === 0 && <p className="empty">Keine Kontakte mit diesem Filter.</p>}
              </div>
            </div>
          </div>
        )}

        {/* ═══ KAMPAGNE (Wizard + Sequences) ═══════════════════════ */}
        {section === 'campaign' && (
          <div key="campaign">
            <h1 className="page-title">E-Mail-Kampagne</h1>
            <p className="page-desc">Kontakte auswählen → Personalisierte E-Mails erstellen → Freigeben → Versenden</p>

            {/* View Toggle */}
            <div className="filter-bar" style={{marginBottom:'1rem'}}>
              <button className={`btn btn-sm ${seqView === 'wizard' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSeqView('wizard')}>Kampagnen-Wizard</button>
              <button className={`btn btn-sm ${seqView === 'sequences' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setSeqView('sequences')}>
                Sequenzen {seqCampaigns.length > 0 && `(${seqCampaigns.length})`}
              </button>
            </div>

            {seqView === 'wizard' && (
              <>
                <WizardSteps />

                {/* ── Step 1: Kontakte auswählen ── */}
                {campStep === 1 && (
                  <div className="card">
                    <div className="card-header">
                      <h2>Kontakte aus Adressbuch auswählen ({activeContacts.length} nutzbar)</h2>
                      <div className="card-actions">
                        <button className="btn btn-ghost btn-sm" onClick={toggleCampSelectAll}>
                          {campSelected.size === activeContacts.length ? 'Keine' : 'Alle'} auswählen
                        </button>
                      </div>
                    </div>
                    {activeContacts.length === 0 ? (
                      <div className="empty-cta"><p>Keine nutzbaren Kontakte im Adressbuch.</p><button className="btn btn-secondary" onClick={() => setSection('search')}>Zur Suche →</button><button className="btn btn-ghost" onClick={() => setSection('addressbook')}>Adressbuch →</button></div>
                    ) : (
                      <>
                        <div className="list">
                          {activeContacts.map(a => (
                            <div key={a.id} className={`list-item camp-select-item ${campSelected.has(a.id) ? 'camp-selected' : ''}`} onClick={() => toggleCampSelect(a.id)}>
                              <div className="camp-checkbox">
                                <input type="checkbox" checked={campSelected.has(a.id)} onChange={() => toggleCampSelect(a.id)} onClick={e => e.stopPropagation()} />
                              </div>
                              <div className="list-main">
                                <strong>{a.name}</strong>
                                <span className="sub">{a.title} · {a.company}</span>
                                <span className="sub">{a.email}{a.email_verified && <span className="verified">✓</span>}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="wizard-actions">
                          <span className="hint">{campSelected.size} von {activeContacts.length} ausgewählt</span>
                          <div style={{display:'flex',alignItems:'center',gap:'0.5rem'}}>
                            {campSelected.size === 0 && <span className="sub">Bitte mindestens einen Kontakt auswählen</span>}
                            <button className="btn btn-primary" disabled={loading || campSelected.size === 0} onClick={campGoToStep2}>
                              Weiter — Entwürfe erstellen ({campSelected.size})
                            </button>
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* ── Step 2: Entwürfe bearbeiten (two-column) ── */}
                {campStep === 2 && (
                  <div className="camp-two-col">
                    {/* Left: Contact list */}
                    <div className="camp-col-left">
                      <div className="card">
                        <h2>Kontakte ({campLeads.length})</h2>
                        <div className="list">
                          {campLeads.map(l => (
                            <div key={l.id} className={`list-item camp-lead-item ${campActiveLeadId === l.id ? 'camp-lead-active' : ''}`} onClick={() => campSelectLead(l)}>
                              <div className="list-main">
                                <strong>{l.name}</strong>
                                <span className="sub">{l.title} · {l.company}</span>
                              </div>
                              <div className="list-actions">
                                {l.drafted_email ? <span className="badge badge-yellow">Entwurf</span> : <span className="badge badge-gray">Kein Entwurf</span>}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Right: Email editor */}
                    <div className="camp-col-right">
                      <div className="card">
                        {campActiveLeadId ? (
                          <>
                            {(() => {
                              const activeLead = campLeads.find(l => l.id === campActiveLeadId)
                              return activeLead ? (
                                <>
                                  <div className="card-header">
                                    <h2>E-Mail an {activeLead.name}</h2>
                                    <div className="card-actions">
                                      <button className="btn btn-ghost btn-sm" disabled={loading} onClick={() => campRegenerateDraft(activeLead.id)}>Neu generieren</button>
                                    </div>
                                  </div>
                                  <div className="camp-recipient">
                                    <span className="sub">An: {activeLead.email} · {activeLead.title} · {activeLead.company}</span>
                                  </div>
                                  {activeLead.drafted_email ? (
                                    <div className="camp-editor">
                                      <div className="form-group">
                                        <label>Betreff</label>
                                        <input value={campDraftSubject} onChange={e => setCampDraftSubject(e.target.value)} />
                                      </div>
                                      <div className="form-group">
                                        <label>Nachricht</label>
                                        <textarea className="camp-textarea" value={campDraftBody} onChange={e => setCampDraftBody(e.target.value)} rows={14} />
                                      </div>
                                      <button className="btn btn-secondary" disabled={loading} onClick={campSaveDraft}>Änderungen speichern</button>
                                    </div>
                                  ) : (
                                    <p className="empty">Kein Entwurf vorhanden. Klicke "Neu generieren" um einen Entwurf zu erstellen.</p>
                                  )}
                                </>
                              ) : null
                            })()}
                          </>
                        ) : (
                          <p className="empty">Kontakt links auswählen, um den E-Mail-Entwurf zu sehen und zu bearbeiten.</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* Step 2 navigation */}
                {campStep === 2 && (
                  <div className="wizard-actions">
                    <button className="btn btn-ghost" onClick={() => setCampStep(1)}>Zurück</button>
                    <button className="btn btn-primary" disabled={loading} onClick={campGoToStep3}>
                      Weiter — Zur Freigabe
                    </button>
                  </div>
                )}

                {/* ── Step 3: Freigabe ── */}
                {campStep === 3 && (
                  <div className="card">
                    <div className="card-header">
                      <h2>Entwürfe freigeben</h2>
                      <div className="card-actions">
                        <button className="btn btn-secondary btn-sm" disabled={loading} onClick={campApproveAll}>Alle freigeben</button>
                      </div>
                    </div>
                    <p className="hint" style={{marginBottom:'0.75rem'}}>Prüfe jeden Entwurf und gib ihn einzeln oder alle auf einmal frei.</p>
                    <div className="list">
                      {campLeads.filter(l => l.drafted_email).map(l => {
                        const approved = l.drafted_email?.is_approved
                        return (
                          <div key={l.id} className={`list-item ${approved ? 'camp-approved-item' : ''}`}>
                            <div className="list-main">
                              <strong>{l.name}</strong>
                              <span className="sub">{l.title} · {l.company} · {l.email}</span>
                              <span className="sub camp-subject-preview">Betreff: {l.drafted_email?.subject || '—'}</span>
                            </div>
                            <div className="list-actions">
                              {approved
                                ? <>
                                    <span className="badge badge-green">Freigegeben</span>
                                    <button className="btn btn-ghost btn-sm" onClick={() => campUnapprove(l.id)}>Widerrufen</button>
                                  </>
                                : <>
                                    <span className="badge badge-yellow">Entwurf</span>
                                    <button className="btn btn-primary btn-sm" onClick={() => campApprove(l.id)}>Freigeben</button>
                                  </>
                              }
                              <button className="btn btn-ghost btn-sm" onClick={() => { setCampActiveLeadId(l.id); setCampDraftSubject(l.drafted_email?.subject || ''); setCampDraftBody(l.drafted_email?.body || ''); setCampStep(2) }}>Bearbeiten</button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className="wizard-actions">
                      <button className="btn btn-ghost" onClick={() => setCampStep(2)}>Zurück</button>
                      <button className="btn btn-primary" disabled={loading} onClick={campGoToStep4}>
                        Weiter — Zum Versand
                      </button>
                    </div>
                  </div>
                )}

                {/* ── Step 4: Versand ── */}
                {campStep === 4 && (
                  <div className="card">
                    <div className="card-header">
                      <h2>E-Mails versenden</h2>
                      <div className="card-actions">
                        <button className="btn btn-ghost btn-sm" onClick={toggleSendSelectAll}>
                          {campSendSelected.size === campLeads.filter(l => l.drafted_email?.is_approved && !l.date_email_sent).length ? 'Keine' : 'Alle'} auswählen
                        </button>
                      </div>
                    </div>
                    {!authStatus?.authenticated && (
                      <div className="card card-warn" style={{marginBottom:'0.75rem'}}>
                        <a href="/api/auth/google/login">Mit Google verbinden</a> um E-Mails zu senden.
                      </div>
                    )}
                    <p className="hint" style={{marginBottom:'0.75rem'}}>
                      Wähle die E-Mails aus, die gesendet werden sollen. Zwischen Sendungen wird 30–90 Sekunden gewartet (Google API Rate Limit).
                    </p>
                    <div className="list">
                      {campLeads.filter(l => l.drafted_email?.is_approved).map(l => {
                        const alreadySent = !!l.date_email_sent
                        return (
                          <div key={l.id} className={`list-item ${alreadySent ? 'camp-sent-item' : ''} ${campSendSelected.has(l.id) ? 'camp-selected' : ''}`}>
                            {!alreadySent && (
                              <div className="camp-checkbox">
                                <input type="checkbox" checked={campSendSelected.has(l.id)} onChange={() => toggleSendSelect(l.id)} />
                              </div>
                            )}
                            <div className="list-main">
                              <strong>{l.name}</strong>
                              <span className="sub">{l.email} · {l.title} · {l.company}</span>
                              <span className="sub camp-subject-preview">Betreff: {l.drafted_email?.subject || '—'}</span>
                            </div>
                            <div className="list-actions">
                              {alreadySent
                                ? <span className="badge badge-green">Gesendet</span>
                                : <span className="badge badge-blue">Bereit</span>
                              }
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className="wizard-actions">
                      <button className="btn btn-ghost" onClick={() => setCampStep(3)}>Zurück</button>
                      <button className="btn btn-primary btn-send" disabled={loading || campSendSelected.size === 0 || !authStatus?.authenticated} onClick={campSendEmails}>
                        {campSendSelected.size} E-Mail{campSendSelected.size !== 1 ? 's' : ''} jetzt senden
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ═══ SEQUENZEN VIEW ═══════════════════════ */}
            {seqView === 'sequences' && (
              <div>
                {/* Sequence Actions Bar */}
                <div className="card">
                  <div className="card-header">
                    <h2>Multi-Touch-Sequenzen</h2>
                    <div className="card-actions">
                      <button className="btn btn-secondary btn-sm" disabled={loading} onClick={seqDraftAllNext}>Alle nächsten Schritte erstellen</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => { loadSeqCampaigns(); loadSeqTemplates() }}>Aktualisieren</button>
                    </div>
                  </div>
                  <p className="hint" style={{marginBottom:'0.5rem'}}>
                    4-Schritt-Sequenz: Initial → Follow-Up 1 (Tag 3) → Follow-Up 2 (Tag 8) → Breakup (Tag 15). Jeder Schritt muss einzeln freigegeben werden.
                  </p>

                  {/* Start new sequence for leads without campaign */}
                  {leads.filter(l => l.email_verified && !l.campaign_sequence && !l.opted_out).length > 0 && (
                    <div style={{padding:'0.75rem',background:'#f0f9ff',borderRadius:'0.5rem',border:'1px solid #bae6fd',marginBottom:'0.75rem'}}>
                      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.5rem'}}>
                        <span style={{fontSize:'0.85rem'}}>
                          <strong>{leads.filter(l => l.email_verified && !l.campaign_sequence && !l.opted_out).length}</strong> verifizierte Leads ohne Sequenz
                        </span>
                        <button className="btn btn-primary btn-sm" disabled={loading} onClick={() => {
                          const eligibleIds = leads.filter(l => l.email_verified && !l.campaign_sequence && !l.opted_out).map(l => l.id)
                          seqStartCampaign(eligibleIds)
                        }}>Sequenz für alle starten</button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Campaign List */}
                {seqCampaigns.length === 0 ? (
                  <div className="card"><p className="empty">Keine aktiven Sequenzen. Starte eine Sequenz für verifizierte Leads.</p></div>
                ) : (
                  seqCampaigns.map(camp => (
                    <div key={camp.lead_id} className="card" style={{marginBottom:'0.75rem'}}>
                      <div className="card-header">
                        <div>
                          <h2 style={{margin:0,fontSize:'1rem'}}>{camp.name}</h2>
                          <span className="sub">{camp.company} · {camp.email}</span>
                        </div>
                        <div className="card-actions">
                          {camp.has_reply && <span className="badge badge-green">Antwort erhalten</span>}
                          {camp.is_paused
                            ? <>
                                <span className="badge badge-yellow">Pausiert</span>
                                <button className="btn btn-secondary btn-sm" onClick={() => seqResume(camp.lead_id)}>Fortsetzen</button>
                              </>
                            : <button className="btn btn-ghost btn-sm" onClick={() => seqPause(camp.lead_id)}>Pausieren</button>
                          }
                        </div>
                      </div>

                      {/* Progress bar */}
                      <div style={{margin:'0.5rem 0',background:'#f3f4f6',borderRadius:'0.25rem',height:'6px',overflow:'hidden'}}>
                        <div style={{width:`${(camp.completed_steps / camp.total_steps) * 100}%`,height:'100%',background:'#22c55e',borderRadius:'0.25rem',transition:'width 0.3s'}} />
                      </div>
                      <div className="sub" style={{marginBottom:'0.5rem'}}>{camp.completed_steps}/{camp.total_steps} Schritte abgeschlossen</div>

                      {/* Sequence Steps */}
                      <div style={{display:'flex',flexDirection:'column',gap:'0.375rem'}}>
                        {camp.sequence.map(step => (
                          <div key={step.step} style={{display:'flex',alignItems:'center',gap:'0.5rem',padding:'0.375rem 0.5rem',background:step.status === 'drafted' ? '#fffbeb' : step.status === 'approved' ? '#eff6ff' : step.status === 'sent' ? '#f0fdf4' : '#fff',borderRadius:'0.375rem',border:'1px solid #e5e7eb',fontSize:'0.8rem'}}>
                            <span style={{fontWeight:500,minWidth:'80px'}}>{stepTypeLabel(step.type)}</span>
                            {stepStatusBadge(step.status)}
                            {step.subject && <span className="sub" style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{step.subject}</span>}
                            {step.scheduled_at && step.status === 'pending' && <span className="sub" style={{fontSize:'0.7rem'}}>{new Date(step.scheduled_at).toLocaleDateString('de-DE')}</span>}
                            <div style={{display:'flex',gap:'0.25rem',flexShrink:0}}>
                              {step.status === 'drafted' && (
                                <button className="btn btn-primary btn-sm" style={{fontSize:'0.7rem',padding:'2px 6px'}} onClick={() => seqApproveStep(camp.lead_id, step.step)}>Freigeben</button>
                              )}
                              {step.status === 'pending' && !camp.is_paused && (
                                <button className="btn btn-secondary btn-sm" style={{fontSize:'0.7rem',padding:'2px 6px'}} disabled={loading} onClick={() => seqDraftNext(camp.lead_id)}>Entwerfen</button>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {/* ═══ LINKEDIN ════════════════════════════════ */}
        {section === 'social' && (
          <div key="social">
            <h1 className="page-title">LinkedIn</h1>
            <div className="card">
              <h2>Post generieren</h2>
              <div style={{display:'flex',gap:'0.5rem',alignItems:'end',flexWrap:'wrap'}}>
                <div className="form-group" style={{flex:'0 0 180px'}}><label>Kategorie</label>
                  <select id="postTopic" onChange={e => { if (e.target.value !== '__custom__') document.getElementById('postCustomTopic').value = '' }}>
                    <option value="Regulatory Update">Regulatory Update</option>
                    <option value="Compliance Tip">Compliance Tip</option>
                    <option value="Industry Insight">Industry Insight</option>
                    <option value="Product Feature">Product Feature</option>
                    <option value="Thought Leadership">Thought Leadership</option>
                    <option value="Case Study">Case Study</option>
                    <option value="__custom__">Eigenes Thema...</option>
                  </select>
                </div>
                <div className="form-group" style={{flex:1,minWidth:'200px'}}><label>Eigenes Thema (optional)</label>
                  <input id="postCustomTopic" placeholder="z.B. DORA Deadline März 2026, Digital Euro Update, NIS2..." onFocus={() => { document.getElementById('postTopic').value = '__custom__' }} />
                </div>
                <button className="btn btn-primary" disabled={loading} onClick={() => {
                  const sel = document.getElementById('postTopic').value
                  const custom = document.getElementById('postCustomTopic').value.trim()
                  const topic = sel === '__custom__' && custom ? custom : sel === '__custom__' ? 'Regulatory Update' : sel
                  generatePost(topic, 'LinkedIn')
                }}>Generieren</button>
              </div>
            </div>
            <div className="card"><h2>Posts ({posts.length})</h2>
              {posts.map(p => (
                <div key={p.id} className={`post-item ${p.is_copied ? 'post-copied' : ''}`}>
                  <div className="post-header">
                    <div style={{display:'flex',gap:'0.375rem',alignItems:'center'}}>
                      <span className="badge badge-blue">LinkedIn</span>
                      {p.is_copied && <span className="badge badge-yellow">Kopiert</span>}
                    </div>
                    <div className="post-actions"><span className="sub">{p.created_date?.split('T')[0]}</span>
                      {!p.is_published ? (
                        <button className="btn btn-primary btn-sm" style={{fontSize:'0.65rem',padding:'0.25rem 0.5rem'}} onClick={() => publishToLinkedIn(p.id)}>Auf LinkedIn posten</button>
                      ) : (
                        <span className="badge badge-green" style={{fontSize:'0.6rem'}}>Veröffentlicht{p.published_at ? ` ${p.published_at.split('T')[0]}` : ''}</span>
                      )}
                      <button className="btn btn-ghost btn-sm" onClick={() => copyPost(p.id, p.content)}>{p.is_copied ? 'Erneut kopieren' : 'Kopieren'}</button>
                      {!p.is_published && <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>}
                    </div>
                  </div>
                  <div className="post-content" dangerouslySetInnerHTML={{__html: renderPostContent(p.content)}} />
                </div>
              ))}{posts.length === 0 && <p className="empty">Noch keine Posts. Wähle oben eine Kategorie und klicke "Generieren".</p>}
            </div>
          </div>
        )}

        {/* ═══ ANALYTICS ═════════════════════════════════ */}
        {section === 'analytics' && (
          <div key="analytics">
            <h1 className="page-title">Analytics</h1>
            <p className="page-desc">Übersicht aller versendeten E-Mails, Antworten und Kampagnen-Performance</p>

            {/* Check Replies - prominent at top */}
            <div className="card" style={{background:'#f0f9ff',border:'1px solid #bae6fd'}}>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.75rem'}}>
                <div>
                  <h2 style={{margin:0,color:'#0c4a6e'}}>Gmail-Antworten prüfen</h2>
                  <p className="sub" style={{margin:'0.25rem 0 0'}}>Durchsucht Gmail nach Antworten, Abmeldungen und Bounces</p>
                </div>
                <button className="btn btn-primary btn-send" disabled={checkingReplies} onClick={checkReplies}>
                  {checkingReplies ? <><span className="spinner" style={{width:'14px',height:'14px',marginRight:'0.5rem'}} />Wird geprüft...</> : '📩 Antworten prüfen'}
                </button>
              </div>
              {replyCheckResult && replyCheckResult.details && replyCheckResult.details.length > 0 && (
                <div style={{marginTop:'1rem',padding:'0.75rem',background:'#fff',borderRadius:'0.5rem',border:'1px solid #bbf7d0'}}>
                  <strong>Ergebnis:</strong>
                  <ul style={{margin:'0.5rem 0 0',paddingLeft:'1.25rem'}}>
                    {replyCheckResult.details.map((d, i) => (
                      <li key={i} style={{marginBottom:'0.25rem'}}>
                        <span style={{fontWeight:500}}>{d.name}</span> ({d.email}) —{' '}
                        {d.type === 'reply' && <span className="badge badge-green">Antwort</span>}
                        {d.type === 'unsubscribe' && <span className="badge badge-yellow">Abmeldung</span>}
                        {d.type === 'bounce' && <span className="badge badge-red">Bounce</span>}
                        {d.snippet && <span className="sub" style={{marginLeft:'0.5rem'}}>{d.snippet}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {/* Enhanced Summary Stats */}
            <div className="card">
              <h2>Funnel-Übersicht</h2>
              <div className="stats-grid">
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_leads || 0}</div><div className="stat-lbl">Leads gesamt</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_verified || 0}</div><div className="stat-lbl">Verifiziert</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_sent || 0}</div><div className="stat-lbl">Gesendet</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_delivered || 0}</div><div className="stat-lbl">Zugestellt</div></div>
                <div className="stat-card" style={analyticsSummary?.total_bounced > 0 ? {borderColor:'#ef4444'} : {}}><div className="stat-val">{analyticsSummary?.total_bounced || 0}</div><div className="stat-lbl">Bounced</div></div>
                <div className="stat-card" style={analyticsSummary?.total_replied > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{analyticsSummary?.total_replied || 0}</div><div className="stat-lbl">Antworten</div></div>
                <div className="stat-card" style={analyticsSummary?.total_unsubscribed > 0 ? {borderColor:'#f59e0b'} : {}}><div className="stat-val">{analyticsSummary?.total_unsubscribed || 0}</div><div className="stat-lbl">Abgemeldet</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_follow_ups || 0}</div><div className="stat-lbl">Follow-Ups</div></div>
              </div>

              {/* Rates */}
              <div style={{display:'flex',gap:'1rem',flexWrap:'wrap',marginTop:'1rem',paddingTop:'1rem',borderTop:'1px solid #e5e7eb'}}>
                <div style={{flex:1,minWidth:'120px',textAlign:'center',padding:'0.75rem',background:'#f9fafb',borderRadius:'0.5rem'}}>
                  <div style={{fontSize:'1.5rem',fontWeight:700,color: (analyticsSummary?.reply_rate || 0) > 5 ? '#22c55e' : '#6b7280'}}>{analyticsSummary?.reply_rate || 0}%</div>
                  <div style={{fontSize:'0.75rem',color:'#6b7280'}}>Antwort-Rate</div>
                </div>
                <div style={{flex:1,minWidth:'120px',textAlign:'center',padding:'0.75rem',background:'#f9fafb',borderRadius:'0.5rem'}}>
                  <div style={{fontSize:'1.5rem',fontWeight:700,color: (analyticsSummary?.effective_reply_rate || 0) > 5 ? '#22c55e' : '#6b7280'}}>{analyticsSummary?.effective_reply_rate || 0}%</div>
                  <div style={{fontSize:'0.75rem',color:'#6b7280'}}>Effektive Rate (ohne Bounces)</div>
                </div>
                <div style={{flex:1,minWidth:'120px',textAlign:'center',padding:'0.75rem',background:'#f9fafb',borderRadius:'0.5rem'}}>
                  <div style={{fontSize:'1.5rem',fontWeight:700,color: (analyticsSummary?.bounce_rate || 0) > 5 ? '#ef4444' : '#6b7280'}}>{analyticsSummary?.bounce_rate || 0}%</div>
                  <div style={{fontSize:'0.75rem',color:'#6b7280'}}>Bounce-Rate</div>
                </div>
                <div style={{flex:1,minWidth:'120px',textAlign:'center',padding:'0.75rem',background:'#f9fafb',borderRadius:'0.5rem'}}>
                  <div style={{fontSize:'1.5rem',fontWeight:700,color: (analyticsSummary?.unsub_rate || 0) > 2 ? '#f59e0b' : '#6b7280'}}>{analyticsSummary?.unsub_rate || 0}%</div>
                  <div style={{fontSize:'0.75rem',color:'#6b7280'}}>Abmelde-Rate</div>
                </div>
              </div>
            </div>

            {/* Verification Quality */}
            {analyticsSummary?.by_risk_level && (analyticsSummary.by_risk_level.low > 0 || analyticsSummary.by_risk_level.medium > 0 || analyticsSummary.by_risk_level.high > 0) && (
              <div className="card">
                <h2>E-Mail-Qualität (SMTP-Verifizierung)</h2>
                <div className="stats-grid">
                  <div className="stat-card" style={{borderColor:'#22c55e'}}><div className="stat-val">{analyticsSummary.by_risk_level.low}</div><div className="stat-lbl">Niedriges Risiko</div></div>
                  <div className="stat-card" style={{borderColor:'#f59e0b'}}><div className="stat-val">{analyticsSummary.by_risk_level.medium}</div><div className="stat-lbl">Mittleres Risiko</div></div>
                  <div className="stat-card" style={{borderColor:'#ef4444'}}><div className="stat-val">{analyticsSummary.by_risk_level.high}</div><div className="stat-lbl">Hohes Risiko</div></div>
                  <div className="stat-card" style={{borderColor:'#ef4444'}}><div className="stat-val">{analyticsSummary.by_risk_level.invalid}</div><div className="stat-lbl">Ungültig</div></div>
                </div>
                <div className="sub" style={{marginTop:'0.5rem'}}>{analyticsSummary.total_smtp_verified || 0} von {analyticsSummary.total_verified || 0} verifizierten Leads auch SMTP-geprüft</div>
              </div>
            )}

            {/* Campaign Sequences Stats */}
            {analyticsSummary?.total_in_campaign > 0 && (
              <div className="card">
                <h2>Kampagnen-Sequenzen</h2>
                <div className="stats-grid">
                  <div className="stat-card"><div className="stat-val">{analyticsSummary.total_in_campaign}</div><div className="stat-lbl">Leads in Sequenz</div></div>
                  <div className="stat-card"><div className="stat-val">{analyticsSummary.total_campaign_steps_sent}</div><div className="stat-lbl">Schritte gesendet</div></div>
                  <div className="stat-card"><div className="stat-val">{analyticsSummary.total_campaign_steps_pending}</div><div className="stat-lbl">Schritte ausstehend</div></div>
                  <div className="stat-card" style={analyticsSummary.total_campaign_paused > 0 ? {borderColor:'#f59e0b'} : {}}><div className="stat-val">{analyticsSummary.total_campaign_paused}</div><div className="stat-lbl">Pausiert</div></div>
                </div>
              </div>
            )}

            {/* Funnel View */}
            {analyticsFunnel?.stages && (
              <div className="card">
                <h2>Pipeline-Funnel</h2>
                <div style={{display:'flex',flexDirection:'column',gap:'0.25rem'}}>
                  {[
                    { key: 'identified', label: 'Identifiziert', color: '#6b7280' },
                    { key: 'verified', label: 'Verifiziert', color: '#3b82f6' },
                    { key: 'email_drafted', label: 'E-Mail erstellt', color: '#8b5cf6' },
                    { key: 'email_sent', label: 'Gesendet', color: '#f59e0b' },
                    { key: 'follow_up_sent', label: 'Follow-Up gesendet', color: '#f97316' },
                    { key: 'replied', label: 'Antwort erhalten', color: '#22c55e' },
                  ].map(stage => {
                    const val = analyticsFunnel.stages[stage.key] || 0
                    const max = analyticsFunnel.stages.identified || 1
                    const pct = Math.round((val / max) * 100)
                    return (
                      <div key={stage.key} style={{display:'flex',alignItems:'center',gap:'0.75rem'}}>
                        <div style={{width:'120px',fontSize:'0.8rem',color:'#6b7280',textAlign:'right'}}>{stage.label}</div>
                        <div style={{flex:1,background:'#f3f4f6',borderRadius:'0.25rem',height:'24px',overflow:'hidden'}}>
                          <div style={{width:`${pct}%`,height:'100%',background:stage.color,borderRadius:'0.25rem',transition:'width 0.5s',minWidth:val > 0 ? '2px' : 0}} />
                        </div>
                        <div style={{width:'50px',fontSize:'0.8rem',fontWeight:600}}>{val}</div>
                      </div>
                    )
                  })}
                </div>
                {analyticsFunnel.conversions && (
                  <div className="sub" style={{marginTop:'0.75rem',paddingTop:'0.5rem',borderTop:'1px solid #e5e7eb'}}>
                    {analyticsFunnel.conversions.identified_to_verified != null && <span style={{marginRight:'1rem'}}>Identifiziert → Verifiziert: {analyticsFunnel.conversions.identified_to_verified}%</span>}
                    {analyticsFunnel.conversions.verified_to_sent != null && <span style={{marginRight:'1rem'}}>Verifiziert → Gesendet: {analyticsFunnel.conversions.verified_to_sent}%</span>}
                    {analyticsFunnel.conversions.sent_to_replied != null && <span>Gesendet → Antwort: {analyticsFunnel.conversions.sent_to_replied}%</span>}
                  </div>
                )}
              </div>
            )}

            {/* Sent Emails List */}
            <div className="card">
              <h2>Versendete E-Mails ({sentEmails.length})</h2>
              {sentEmails.length === 0 && <div className="empty-cta"><p>Noch keine E-Mails versendet.</p><button className="btn btn-secondary" onClick={() => setSection('campaign')}>Kampagne starten →</button></div>}
              {sentEmails.map(em => (
                <div key={em.id} style={{border:'1px solid #e5e7eb',borderRadius:'0.5rem',marginBottom:'0.75rem',overflow:'hidden'}}>
                  {/* Header row - clickable */}
                  <div
                    onClick={() => toggleAnalyticsRow(em.id)}
                    style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'0.75rem 1rem',cursor:'pointer',background:analyticsExpanded[em.id]?'#f9fafb':'#fff',gap:'0.5rem',flexWrap:'wrap'}}
                  >
                    <div style={{display:'flex',alignItems:'center',gap:'0.75rem',flex:1,minWidth:0}}>
                      <span style={{transform:analyticsExpanded[em.id]?'rotate(90deg)':'rotate(0)',transition:'transform 0.15s',fontSize:'0.75rem',color:'#9ca3af'}}>▶</span>
                      <div style={{minWidth:0}}>
                        <div style={{fontWeight:500,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{em.name}</div>
                        <div className="sub" style={{fontSize:'0.75rem'}}>{em.company} · {em.email}</div>
                      </div>
                    </div>
                    <div style={{display:'flex',alignItems:'center',gap:'0.5rem',flexShrink:0}}>
                      {em.campaign_current_step > 0 && <span className="badge badge-blue" style={{fontSize:'0.65rem'}}>Schritt {em.campaign_current_step}</span>}
                      {em.reply_received && !em.reply_received.startsWith('[UNSUBSCRIBE]') && <span className="badge badge-green">Antwort</span>}
                      {em.opted_out && <span className="badge badge-yellow">Abgemeldet</span>}
                      {em.delivery_status === 'Bounced' && <span className="badge badge-red">Bounced</span>}
                      {em.delivery_status === 'Delivered' && <span className="badge badge-blue">Zugestellt</span>}
                      {!em.reply_received && !em.opted_out && em.delivery_status !== 'Bounced' && em.delivery_status !== 'Delivered' && <span className="badge">Gesendet</span>}
                      <span className="sub" style={{fontSize:'0.7rem',whiteSpace:'nowrap'}}>{em.date_email_sent?.split('T')[0]}</span>
                    </div>
                  </div>
                  {/* Expanded details */}
                  {analyticsExpanded[em.id] && (
                    <div style={{padding:'0.75rem 1rem 1rem',borderTop:'1px solid #e5e7eb',background:'#f9fafb'}}>
                      <div style={{marginBottom:'0.75rem'}}>
                        <div style={{fontWeight:600,fontSize:'0.8rem',color:'#6b7280',marginBottom:'0.25rem'}}>Betreff</div>
                        <div style={{background:'#fff',padding:'0.5rem 0.75rem',borderRadius:'0.375rem',border:'1px solid #e5e7eb'}}>{em.subject || '—'}</div>
                      </div>
                      <div style={{marginBottom:'0.75rem'}}>
                        <div style={{fontWeight:600,fontSize:'0.8rem',color:'#6b7280',marginBottom:'0.25rem'}}>E-Mail-Text</div>
                        <div style={{background:'#fff',padding:'0.5rem 0.75rem',borderRadius:'0.375rem',border:'1px solid #e5e7eb',whiteSpace:'pre-wrap',fontSize:'0.85rem',maxHeight:'300px',overflowY:'auto'}}>{em.body || '—'}</div>
                      </div>
                      {em.follow_up_subject && (
                        <div style={{marginBottom:'0.75rem'}}>
                          <div style={{fontWeight:600,fontSize:'0.8rem',color:'#6b7280',marginBottom:'0.25rem'}}>Follow-up</div>
                          <div style={{background:'#fff',padding:'0.5rem 0.75rem',borderRadius:'0.375rem',border:'1px solid #e5e7eb'}}>
                            <div style={{fontWeight:500,marginBottom:'0.25rem'}}>{em.follow_up_subject}</div>
                            <div style={{whiteSpace:'pre-wrap',fontSize:'0.85rem'}}>{em.follow_up_body || '—'}</div>
                          </div>
                        </div>
                      )}
                      {em.reply_received && (
                        <div>
                          <div style={{fontWeight:600,fontSize:'0.8rem',color:em.reply_received.startsWith('[UNSUBSCRIBE]') ? '#f59e0b' : '#22c55e',marginBottom:'0.25rem'}}>
                            {em.reply_received.startsWith('[UNSUBSCRIBE]') ? 'Abmeldung' : 'Antwort erhalten'}
                          </div>
                          <div style={{background:em.reply_received.startsWith('[UNSUBSCRIBE]') ? '#fffbeb' : '#f0fdf4',padding:'0.5rem 0.75rem',borderRadius:'0.375rem',border:`1px solid ${em.reply_received.startsWith('[UNSUBSCRIBE]') ? '#fde68a' : '#bbf7d0'}`,whiteSpace:'pre-wrap',fontSize:'0.85rem'}}>{em.reply_received}</div>
                        </div>
                      )}
                      {/* Reset / Resend buttons */}
                      <div style={{marginTop:'0.75rem',paddingTop:'0.75rem',borderTop:'1px solid #e5e7eb',display:'flex',justifyContent:'flex-end',gap:'0.5rem'}}>
                        <button className="btn btn-secondary btn-sm" style={{fontSize:'0.75rem'}} onClick={async (e) => {
                          e.stopPropagation()
                          if (!window.confirm(`E-Mail an ${em.name} erneut senden ermöglichen? Der bestehende Draft bleibt erhalten.`)) return
                          try {
                            await fetchJson(`${API}/email/resend/${em.id}`, { method: 'POST' })
                            showSuccess(`${em.name}: bereit zum erneuten Senden`)
                            loadSentEmails(); loadAnalyticsSummary()
                          } catch (err) { setError('Resend-Reset fehlgeschlagen: ' + (err.message || err)) }
                        }}>Erneut senden ermöglichen</button>
                        <button className="btn btn-ghost btn-sm" style={{color:'#ef4444',fontSize:'0.75rem'}} onClick={async (e) => {
                          e.stopPropagation()
                          if (!window.confirm(`Kampagne für ${em.name} komplett zurücksetzen? Draft, Sendedatum und Status werden gelöscht.`)) return
                          try {
                            await fetchJson(`${API}/email/reset/${em.id}`, { method: 'POST' })
                            loadSentEmails(); loadAnalyticsSummary()
                          } catch (err) { setError('Reset fehlgeschlagen: ' + (err.message || err)) }
                        }}>Komplett zurücksetzen</button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ═══ SETTINGS ════════════════════════════════ */}
        {section === 'settings' && (
          <div key="settings">
            <h1 className="page-title">Einstellungen</h1>
            <p className="page-desc">Integrationen und Konfiguration</p>

            <div className="card">
              <h2>Google-Anbindung</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Wird für den E-Mail-Versand und das Prüfen von Antworten benötigt.</p>
              {authStatus?.authenticated
                ? <div style={{display:'flex',alignItems:'center',gap:'0.75rem',flexWrap:'wrap'}}>
                    <span style={{display:'flex',alignItems:'center',gap:'0.375rem'}}><span style={{color:'#22c55e',fontSize:'1.1rem'}}>●</span> Verbunden als <strong>{authStatus.email}</strong></span>
                    <button className="btn btn-secondary btn-sm" onClick={async () => { await fetchJson(`${API}/auth/logout`, { method: 'POST' }); loadAuthStatus() }}>Verbindung trennen</button>
                  </div>
                : <div style={{display:'flex',alignItems:'center',gap:'0.75rem',flexWrap:'wrap'}}>
                    <a href="/api/auth/google/login" className="btn btn-primary">Mit Google verbinden</a>
                    {authStatus?.token_expired && <span className="badge badge-yellow">Token abgelaufen — erneut verbinden</span>}
                  </div>}
            </div>

            <div className="card">
              <h2>Absender</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Informationen, die als Absender in E-Mails verwendet werden.</p>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'0.75rem',maxWidth:'500px'}}>
                <div className="form-group"><label>Name</label><input value="Martin Foerster" disabled style={{background:'#f9fafb'}} /></div>
                <div className="form-group"><label>E-Mail</label><input value="mf@harpocrates-corp.com" disabled style={{background:'#f9fafb'}} /></div>
              </div>
              <span className="sub">Absender-Konfiguration wird serverseitig verwaltet.</span>
            </div>

            <div className="card">
              <h2>LinkedIn-Integration</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Zugangsdaten für die direkte Veröffentlichung auf der Harpocrates LinkedIn-Seite.</p>
              {linkedinSettings.has_token
                ? <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'0.75rem'}}>
                    <span style={{color:'#22c55e',fontSize:'1.1rem'}}>●</span>
                    <span>Access Token hinterlegt</span>
                    {linkedinSettings.org_id && <span className="badge badge-blue">Org: {linkedinSettings.org_id}</span>}
                  </div>
                : <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'0.75rem'}}>
                    <span style={{color:'#ef4444',fontSize:'1.1rem'}}>●</span>
                    <span>Nicht konfiguriert — bitte Access Token eintragen</span>
                  </div>}
              <form onSubmit={saveLinkedinSettings}>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'0.75rem',maxWidth:'600px'}}>
                  <div className="form-group">
                    <label>Access Token</label>
                    <input name="linkedin_access_token" type="password" placeholder={linkedinSettings.has_token ? '••••••• (gespeichert)' : 'Bearer Token einfügen'} />
                  </div>
                  <div className="form-group">
                    <label>Organization ID</label>
                    <input name="linkedin_org_id" defaultValue={linkedinSettings.org_id} placeholder="z.B. 42109305" />
                  </div>
                </div>
                <button type="submit" className="btn btn-primary btn-sm" style={{marginTop:'0.5rem'}} disabled={loading}>Speichern</button>
              </form>
              <p className="sub" style={{fontSize:'0.65rem',marginTop:'0.5rem'}}>Token über linkedin.com/developers/tools/oauth/token-generator generieren. Scopes: w_organization_social, r_organization_admin.</p>
            </div>

            <div className="card">
              <h2>Daten verwalten</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Export und Import deiner Outreach-Daten.</p>
              <div style={{display:'flex',gap:'0.5rem',flexWrap:'wrap'}}>
                <button className="btn btn-secondary" onClick={() => exportCSV('companies')}>Unternehmen CSV</button>
                <button className="btn btn-secondary" onClick={() => exportCSV('leads')}>Kontakte CSV</button>
                <button className="btn btn-secondary" onClick={() => exportCSV('address-book')}>Adressbuch CSV</button>
              </div>
            </div>

            <div className="card">
              <h2>Info</h2>
              <div style={{display:'flex',flexDirection:'column',gap:'0.25rem',fontSize:'0.8125rem',color:'#6b7280'}}>
                <span>Harpocrates Outreach — v2.0</span>
                <span>Frontend: React (Vite) · Backend: FastAPI (Cloud Run)</span>
                <span>KI-Recherche: Perplexity Sonar Pro</span>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App

