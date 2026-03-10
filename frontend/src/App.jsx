import { useState, useEffect, useCallback, useRef } from 'react'
import harpoLogo from './assets/logo.webp'
import { Phase2Panel } from './Phase2Sections.jsx'

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
  const [linkedinAnalytics, setLinkedinAnalytics] = useState(null)
  const [authStatus, setAuthStatus] = useState(null)
  const [authChecked, setAuthChecked] = useState(false) // true once initial auth check completes
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
  const [linkedinSettings, setLinkedinSettings] = useState({ org_id: '', person_urn: '', has_token: false })
  const [replyCheckResult, setReplyCheckResult] = useState(null)
  const [loadingProgress, setLoadingProgress] = useState(null) // { current, total } for batch ops
  const [searchLeadsFilter, setSearchLeadsFilter] = useState('with_email') // 'all' | 'verified' | 'unverified'
  const [searchLeadsQuery, setSearchLeadsQuery] = useState('') // text filter for leads
  const [leadsGroupByCompany, setLeadsGroupByCompany] = useState(true) // group contacts by company
  const [leadsDisplayLimit, setLeadsDisplayLimit] = useState(50) // pagination: show N leads at a time
  const [scoringLeads, setScoringLeads] = useState(false)
  const [checkingBounces, setCheckingBounces] = useState(false)
  const [checkingRepliesImap, setCheckingRepliesImap] = useState(false)
  const [bounceCheckResult, setBounceCheckResult] = useState(null)
  const [imapReplyResult, setImapReplyResult] = useState(null)
  const [activityLog, setActivityLog] = useState([])

  // Content Calendar state
  const [contentCalendar, setContentCalendar] = useState(null)
  const [socialView, setSocialView] = useState('posts') // 'posts' | 'calendar'
  const [generatingWeekly, setGeneratingWeekly] = useState(false)

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
  const loadContentCalendar = useCallback(async () => { try { const r = await fetchJson(`${API}/data/content-calendar`); setContentCalendar(r) } catch {} }, [])
  const loadAddressBook = useCallback(async () => { try { const r = await fetchJson(`${API}/data/address-book`); setAddressBook(r.data || []) } catch {} }, [])
  const loadSentEmails = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/sent-emails`); setSentEmails(r.data || []) } catch {} }, [])
  const loadAnalyticsSummary = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/summary`); setAnalyticsSummary(r.data || null) } catch {} }, [])
  const loadAnalyticsFunnel = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/funnel`); setAnalyticsFunnel(r.data || null) } catch {} }, [])
  const loadLinkedinAnalytics = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/linkedin-posts`); setLinkedinAnalytics(r) } catch(e) { console.warn('LinkedIn analytics load failed:', e) } }, [])
  const loadActivityLog = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/activity-log?limit=30`); setActivityLog(r.data || []) } catch {} }, [])
  const loadAuthStatus = useCallback(async () => { try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {} finally { setAuthChecked(true) } }, [])
  const loadLinkedinSettings = useCallback(async () => {
    try {
      const r = await fetchJson(`${API}/data/settings`)
      const s = r.data || {}
      setLinkedinSettings({ org_id: s.linkedin_org_id || '', person_urn: s.linkedin_person_urn || '', has_token: !!(s.linkedin_access_token && s.linkedin_access_token !== '') })
    } catch {}
  }, [])
  const loadSeqCampaigns = useCallback(async () => { try { const r = await fetchJson(`${API}/campaigns/status`); setSeqCampaigns(r.data || []) } catch {} }, [])
  const loadSeqTemplates = useCallback(async () => { try { const r = await fetchJson(`${API}/campaigns/templates`); setSeqTemplates(r.data || []) } catch {} }, [])

  // Handle auth callback parameters from URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authResult = params.get('auth')
    if (authResult === 'success') {
      showSuccess('Erfolgreich angemeldet')
      window.history.replaceState({}, '', window.location.pathname)
    } else if (authResult === 'denied') {
      const email = params.get('email')
      const reason = params.get('reason')
      if (reason === 'deactivated') setError('Dein Konto wurde deaktiviert. Bitte kontaktiere den Administrator.')
      else setError(`Zugriff verweigert${email ? ` für ${email}` : ''}. Du musst von einem Admin eingeladen werden.`)
      window.history.replaceState({}, '', window.location.pathname)
    } else if (authResult === 'error') {
      setError('Anmeldefehler. Bitte erneut versuchen.')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  useEffect(() => { loadDashboard(); loadAuthStatus(); loadLinkedinSettings() }, [loadDashboard, loadAuthStatus, loadLinkedinSettings])
  useEffect(() => {
    setError(''); setSuccessMsg('')
    if (section === 'overview') { loadDashboard(); loadLeads(); loadAddressBook(); loadCompanies(); loadAnalyticsSummary() }
    else if (section === 'search') { loadCompanies(); loadLeads() }
    else if (section === 'addressbook') { loadAddressBook(); loadLeads(); loadSentEmails() }
    else if (section === 'campaign') { loadAddressBook(); loadLeads(); loadSeqCampaigns(); loadSeqTemplates() }
    else if (section === 'social') { loadPosts(); loadContentCalendar() }
    else if (section === 'analytics') { loadSentEmails(); loadAnalyticsSummary(); loadAnalyticsFunnel(); loadLinkedinAnalytics(); loadPosts(); loadActivityLog() }
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
  // ─── Score Leads ──────────────────────────────────────
  const scoreAllLeads = async () => {
    setScoringLeads(true); setError('')
    try {
      const r = await fetchJson(`${API}/prospecting/score-leads`, { method: 'POST' })
      showSuccess(`${r.scored || 0} Leads bewertet`)
      await loadLeads()
    } catch (e) { setError(e.message) }
    setScoringLeads(false)
  }

  // ─── IMAP Bounce Check ────────────────────────────────
  const checkBouncesImap = async () => {
    setCheckingBounces(true); setBounceCheckResult(null); setError('')
    try {
      const r = await fetchJson(`${API}/email/check-bounces`, { method: 'POST' })
      setBounceCheckResult(r)
      showSuccess(`Bounce-Check: ${r.bounces_found || 0} Bounces gefunden, ${r.leads_updated || 0} Leads aktualisiert`)
      await loadSentEmails()
      await loadAnalyticsSummary()
    } catch (e) { setError(e.message) }
    setCheckingBounces(false)
  }

  // ─── IMAP Reply Check (Hostinger) ─────────────────────
  const checkRepliesImap = async () => {
    setCheckingRepliesImap(true); setImapReplyResult(null); setError('')
    try {
      const r = await fetchJson(`${API}/email/check-replies-imap`, { method: 'POST' })
      setImapReplyResult(r)
      showSuccess(`IMAP-Prüfung: ${r.replies_found || 0} Antworten, ${r.auto_opt_outs || 0} Abmeldungen`)
      await loadSentEmails()
      await loadAnalyticsSummary()
    } catch (e) { setError(e.message) }
    setCheckingRepliesImap(false)
  }

  // ─── Send Follow-Up ───────────────────────────────────
  const sendFollowUp = async (leadId) => {
    if (!confirm('Follow-Up jetzt senden?')) return
    startLoading('Follow-Up wird gesendet...'); setError('')
    try {
      await fetchJson(`${API}/email/send-follow-up/${leadId}`, { method: 'POST' })
      showSuccess('Follow-Up gesendet')
      await loadSentEmails()
      await loadAnalyticsSummary()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // ─── Send Campaign Step ───────────────────────────────
  const sendCampaignStep = async (leadId, stepNum) => {
    if (!confirm(`Schritt ${stepNum} jetzt senden?`)) return
    startLoading(`Schritt ${stepNum} wird gesendet...`); setError('')
    try {
      const r = await fetchJson(`${API}/campaigns/send-step/${leadId}/${stepNum}`, { method: 'POST' })
      showSuccess(`Schritt ${stepNum} (${r.type || ''}) gesendet`)
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  // ─── Send All Approved Campaign Steps ─────────────────
  const sendApprovedSteps = async () => {
    if (!confirm('Alle genehmigten Schritte jetzt senden?')) return
    startLoading('Genehmigte Schritte werden gesendet...'); setError('')
    try {
      const r = await fetchJson(`${API}/campaigns/send-approved-steps`, { method: 'POST' })
      showSuccess(`${r.sent || 0} gesendet${r.failed ? `, ${r.failed} fehlgeschlagen` : ''}${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      await loadSeqCampaigns()
    } catch (e) { setError(e.message) }
    stopLoading()
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

  const generateWeeklyPosts = async () => {
    setGeneratingWeekly(true)
    startLoading('2 Posts f\u00fcr die Woche werden generiert + Cross-Check (kann bis zu 5 Min. dauern)...')
    setError('')
    try {
      const tueTopic = document.getElementById('tueTopic')?.value || 'Regulatory Update'
      const friTopic = document.getElementById('friTopic')?.value || 'Compliance Tip'
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 8 * 60 * 1000)
      const resp = await fetch(`${API}/data/social-posts/generate-weekly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tuesday_topic: tueTopic, friday_topic: friTopic, week_offset: 0 }),
        signal: controller.signal,
      })
      clearTimeout(timeout)
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `Fehler ${resp.status}`) }
      const data = await resp.json()
      showSuccess(`${data.generated} Posts generiert und geplant`)
      await loadPosts()
      await loadContentCalendar()
    } catch (e) {
      if (e.name === 'AbortError') setError('Generierung hat zu lange gedauert.')
      else setError(e.message)
    }
    stopLoading()
    setGeneratingWeekly(false)
  }

  const generatePost = async (topic, platform) => {
    startLoading('Post wird generiert + Cross-Check l\u00e4uft (kann bis zu 3 Min. dauern bei Auto-Regenerierung)...'); setError('')
    try {
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000)
      const resp = await fetch(`${API}/data/social-posts/generate?topic=${encodeURIComponent(topic)}&platform=${encodeURIComponent(platform)}`, { method: 'POST', signal: controller.signal })
      clearTimeout(timeout)
      if (!resp.ok) { const err = await resp.json().catch(() => ({})); throw new Error(err.detail || `Fehler ${resp.status}`) }
      showSuccess('Post generiert und verifiziert'); await loadPosts()
    } catch (e) {
      if (e.name === 'AbortError') setError('Generierung hat zu lange gedauert. Bitte erneut versuchen.')
      else setError(e.message)
    } stopLoading()
  }
  const [verifyExpanded, setVerifyExpanded] = useState({})
  const verifyPost = async (postId) => {
    startLoading('Cross-Check l\u00e4uft (3 Pr\u00fcfungen)...'); setError('')
    try {
      await fetchJson(`${API}/data/social-posts/${postId}/verify`, { method: 'POST' }, 0)
      showSuccess('Cross-Check abgeschlossen')
      await loadPosts()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const regeneratePost = async (postId) => {
    startLoading('Post wird neu generiert + Cross-Check...'); setError('')
    try {
      await fetchJson(`${API}/data/social-posts/${postId}/regenerate`, { method: 'POST' }, 0)
      showSuccess('Post neu generiert und geprüft')
      await loadPosts()
    } catch (e) { setError(e.message) }
    stopLoading()
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
    if (!confirm('Post als Harpocrates Solutions auf LinkedIn ver\u00f6ffentlichen?')) return
    startLoading('Post wird in die Warteschlange gestellt...')
    try {
      const r = await fetchJson(`${API}/data/social-posts/${postId}/publish-linkedin`, { method: 'POST' })
      showSuccess('Post in Warteschlange \u2014 wird in K\u00fcrze als Harpocrates ver\u00f6ffentlicht.')
      await loadPosts()
    } catch (e) { setError(e.message) }
    stopLoading()
  }
  const cancelPublish = async (postId) => {
    startLoading('Wird abgebrochen...')
    try {
      await fetchJson(`${API}/data/social-posts/${postId}/cancel-publish`, { method: 'POST' })
      showSuccess('Ver\u00f6ffentlichung abgebrochen.')
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
    const personUrn = fd.get('linkedin_person_urn')
    if (token && token.trim()) payload.linkedin_access_token = token.trim()
    if (orgId !== undefined) payload.linkedin_org_id = (orgId || '').trim()
    if (personUrn !== undefined) payload.linkedin_person_urn = (personUrn || '').trim()
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
    // Strip markdown bold **text** and *italic*
    let rendered = escaped.replace(/\*\*(.+?)\*\*/g, '$1')
    rendered = rendered.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '$1')
    // Convert markdown links [text](url) to just the URL (plain text for LinkedIn)
    rendered = rendered.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$2')
    // Auto-link plain URLs
    const withLinks = rendered.replace(
      /(https?:\/\/[^\s)<>&]+)/g,
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
    if (!confirm(`${count} E-Mail${count > 1 ? 's' : ''} jetzt senden?\n\nVersand über Hostinger SMTP (mf@harpocrates-corp.com).`)) return

    startLoading(`${count} E-Mails werden gesendet...`); setError('')
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

  // ─── Live Countdown Timer for Cron Publish ────────────
  const [cronCountdown, setCronCountdown] = useState('')
  useEffect(() => {
    const calcCountdown = () => {
      const now = new Date()
      const next = new Date(now)
      next.setMinutes(50, 0, 0)
      if (now.getMinutes() >= 50) next.setHours(next.getHours() + 1)
      const diff = Math.max(0, Math.floor((next - now) / 1000))
      const m = Math.floor(diff / 60)
      const s = diff % 60
      return `${m}:${s.toString().padStart(2, '0')}`
    }
    setCronCountdown(calcCountdown())
    const iv = setInterval(() => setCronCountdown(calcCountdown()), 1000)
    return () => clearInterval(iv)
  }, [])

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

  // Logout handler
  const handleLogout = async () => {
    try {
      await fetchJson(`${API}/auth/logout`, { method: 'POST' })
    } catch {}
    setAuthStatus(null)
    setAuthChecked(true)
  }

  // ─── LOGIN SCREEN ──────────────────────────────────────
  const [loginTab, setLoginTab] = useState('google') // 'google' | 'email'
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)

  const handleEmailLogin = async (e) => {
    e.preventDefault()
    if (!loginEmail || !loginPassword) return
    setLoginLoading(true); setError('')
    try {
      const resp = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || 'Anmeldung fehlgeschlagen')
      }
      // Cookie is set by the response — reload auth status
      await loadAuthStatus()
      showSuccess('Erfolgreich angemeldet')
    } catch (e) { setError(e.message) }
    setLoginLoading(false)
  }

  // Show login screen when auth check is done and user is not authenticated via session cookie
  if (authChecked && !authStatus?.authenticated) {
    return (
      <div className="login-page">
        <div className="login-card">
          <img src={harpoLogo} alt="Harpocrates" className="login-logo" />
          <h1 className="login-title">Harpocrates Outreach</h1>
          <p className="login-desc">Compliance-Outreach-Plattform f\u00fcr dein Team</p>
          {error && <div className="msg msg-error" style={{marginBottom:'1rem',fontSize:'0.8125rem'}}>{error} <button onClick={() => setError('')}>\u00d7</button></div>}
          
          <div className="login-tabs">
            <button className={`login-tab ${loginTab === 'google' ? 'active' : ''}`} onClick={() => setLoginTab('google')}>Google</button>
            <button className={`login-tab ${loginTab === 'email' ? 'active' : ''}`} onClick={() => setLoginTab('email')}>E-Mail</button>
          </div>

          {loginTab === 'google' && (
            <a href="/api/auth/google/login" className="login-google-btn">
              <svg width="18" height="18" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
              Mit Google anmelden
            </a>
          )}

          {loginTab === 'email' && (
            <form onSubmit={handleEmailLogin} className="login-email-form">
              <input type="email" placeholder="E-Mail-Adresse" value={loginEmail} onChange={e => setLoginEmail(e.target.value)} required autoComplete="email" />
              <input type="password" placeholder="Passwort" value={loginPassword} onChange={e => setLoginPassword(e.target.value)} required autoComplete="current-password" />
              <button type="submit" className="login-email-btn" disabled={loginLoading}>{loginLoading ? 'Wird angemeldet...' : 'Anmelden'}</button>
            </form>
          )}

          <p className="login-footer">Nur eingeladene Teammitglieder k\u00f6nnen sich anmelden.<br/>Der erste Benutzer wird automatisch Admin.</p>
        </div>
      </div>
    )
  }

  // Show nothing while checking auth (avoid flash)
  if (!authChecked) {
    return (
      <div className="login-page">
        <div className="login-card">
          <img src={harpoLogo} alt="Harpocrates" className="login-logo" />
          <span className="spinner" style={{margin:'1rem auto'}} />
        </div>
      </div>
    )
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <img src={harpoLogo} alt="Harpocrates" className="sidebar-logo" />
          <div className="sidebar-user">
            {authStatus?.avatar_url && <img src={authStatus.avatar_url} alt="" className="user-avatar-sm" />}
            <div className="user-info-sidebar">
              <span className="user-name-sidebar">{authStatus?.name || authStatus?.email}</span>
              <span className="user-role-sidebar">{authStatus?.role === 'admin' ? 'Admin' : 'Benutzer'}</span>
            </div>
            <button className="btn-logout-sm" onClick={handleLogout} title="Abmelden">⏻</button>
          </div>
        </div>
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



            {stats && (
              <div className="stats-grid" style={{marginBottom:'1.25rem'}}>
                <div className="stat-card"><div className="stat-val">{companies.length}</div><div className="stat-lbl">Unternehmen</div></div>
                <div className="stat-card"><div className="stat-val">{leads.length}</div><div className="stat-lbl">Kontakte</div></div>
                <div className="stat-card"><div className="stat-val">{leads.filter(l => l.email_verified).length}</div><div className="stat-lbl">Verifiziert</div></div>
                <div className="stat-card"><div className="stat-val">{addressBook.length}</div><div className="stat-lbl">Adressbuch</div></div>
                <div className="stat-card"><div className="stat-val">{stats.emails_sent || 0}</div><div className="stat-lbl">Gesendet</div></div>
                <div className="stat-card" style={analyticsSummary?.total_replied > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{analyticsSummary?.total_replied || 0}</div><div className="stat-lbl">Antworten</div></div>
                {analyticsSummary?.tracking_total_tracked > 0 && (
                  <div className="stat-card" style={{borderColor:'#3b82f6'}}><div className="stat-val">{analyticsSummary.tracking_open_rate}%</div><div className="stat-lbl">Open-Rate</div></div>
                )}
                {analyticsSummary?.tracking_total_tracked > 0 && (
                  <div className="stat-card" style={{borderColor:'#8b5cf6'}}><div className="stat-val">{analyticsSummary.tracking_click_rate}%</div><div className="stat-lbl">Click-Rate</div></div>
                )}
              </div>
            )}
            {/* Sender Pool Status */}
            {analyticsSummary?.pool_active_senders > 0 && (
              <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'1rem',padding:'0.5rem 0.75rem',background:'#f0f9ff',borderRadius:'0.375rem',border:'1px solid #bae6fd',fontSize:'0.8rem',color:'#0c4a6e'}}>
                <span style={{fontSize:'1rem'}}>🔄</span>
                <span>Sender Pool: <strong>{analyticsSummary.pool_active_senders}</strong> aktive Absender · <strong>{analyticsSummary.pool_sent_today}</strong>/{analyticsSummary.pool_daily_capacity} heute gesendet</span>
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
                        {companies.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={async () => { setLoading(true); setLoadingMsg('Compliance-Scores werden berechnet...'); try { const r = await fetch(`${API}/prospecting/compute-compliance-scores`, {method:'POST'}); const d = await r.json(); if (d.success) { setSuccessMsg(`${d.updated} Companies bewertet`); loadData() } else { setError('Fehler bei Score-Berechnung') } } catch(e) { setError(e.message) } finally { setLoading(false); setLoadingMsg('') } }}>⚖️ Compliance</button>}
                        {companies.length > 0 && <button className="btn btn-secondary" disabled={loading} onClick={findAllContacts}>Alle Kontakte</button>}
                      </div>
                    </div>
                    <div className="list">{companies.map(c => (
                      <div key={c.id} className="list-item">
                        <div className="list-main">
                          <strong>{c.name}</strong>
                          <span className="sub">{c.industry} · {c.country} · {c.employee_count?.toLocaleString()} MA</span>
                          {(c.compliance_score > 0 || c.key_regulations) && (
                            <span className="sub" style={{display:'flex',alignItems:'center',gap:'0.375rem',flexWrap:'wrap'}}>
                              {c.compliance_score > 0 && (
                                <span className={`badge ${c.compliance_score >= 0.7 ? 'badge-green' : c.compliance_score >= 0.4 ? 'badge-yellow' : 'badge-gray'}`} style={{fontSize:'0.6rem'}} title={`Compliance-Relevanz: ${Math.round(c.compliance_score * 100)}%`}>
                                  ⚖️ {Math.round(c.compliance_score * 100)}%
                                </span>
                              )}
                              {c.key_regulations && (() => { const regs = c.key_regulations.split(',').map(r => r.trim()).filter(Boolean); return (<>{regs.slice(0,4).map(reg => (<span key={reg} className="badge badge-blue" style={{fontSize:'0.55rem',padding:'1px 4px'}}>{reg}</span>))}{regs.length > 4 && <span className="badge badge-gray" style={{fontSize:'0.55rem',padding:'1px 4px'}}>+{regs.length-4}</span>}</>)})()}
                            </span>
                          )}
                        </div>
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
                        {leads.length > 0 && <button className={`btn btn-ghost btn-sm ${scoringLeads ? 'btn-loading' : ''}`} disabled={scoringLeads || loading} onClick={scoreAllLeads} title="Leads nach Relevanz bewerten">{scoringLeads ? '⚙️ Scoring...' : '⚙️ Score'}</button>}
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
                                  <strong>{l.name}{l.lead_score > 0 && <span style={{fontSize:'0.65rem',fontWeight:400,marginLeft:'0.375rem',color:l.lead_score >= 0.7 ? '#22c55e' : l.lead_score >= 0.4 ? '#f59e0b' : '#9ca3af'}} title={l.lead_score_details || ''}>★ {Math.round(l.lead_score * 100)}%</span>}</strong>
                                  <span className="sub">{l.title}</span>
                                  <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}
                                    {l.email_risk_level && l.email_risk_level !== 'unknown' && <>{' '}{riskBadge(l.email_risk_level)}</>}
                                    {l.email_smtp_verified && <span className="verified" title="SMTP-verifiziert">⚡</span>}
                                    {l.email_is_catch_all && <span className="badge badge-yellow" style={{fontSize:'0.6rem',padding:'1px 4px'}} title="Catch-All-Domain">CA</span>}
                                    {l.delivery_status === 'Bounced' && <span className="badge badge-red" style={{fontSize:'0.55rem',padding:'1px 4px'}}>Bounced</span>}
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
                                <strong>{l.name}{l.lead_score > 0 && <span style={{fontSize:'0.65rem',fontWeight:400,marginLeft:'0.375rem',color:l.lead_score >= 0.7 ? '#22c55e' : l.lead_score >= 0.4 ? '#f59e0b' : '#9ca3af'}} title={l.lead_score_details || ''}>★ {Math.round(l.lead_score * 100)}%</span>}</strong>
                                <span className="sub">{l.title} · {l.company}</span>
                                <span className="sub">{l.email || '—'}{l.email_verified && <span className="verified">✓</span>}
                                  {l.email_risk_level && l.email_risk_level !== 'unknown' && <>{' '}{riskBadge(l.email_risk_level)}</>}
                                  {l.email_smtp_verified && <span className="verified" title="SMTP-verifiziert">⚡</span>}
                                  {l.email_is_catch_all && <span className="badge badge-yellow" style={{fontSize:'0.6rem',padding:'1px 4px'}} title="Catch-All-Domain">CA</span>}
                                  {l.delivery_status === 'Bounced' && <span className="badge badge-red" style={{fontSize:'0.55rem',padding:'1px 4px'}}>Bounced</span>}
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
                      Wähle die E-Mails aus, die gesendet werden sollen. Versand über Hostinger SMTP (mf@harpocrates-corp.com).
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
                      <button className="btn btn-primary btn-sm" disabled={loading} onClick={sendApprovedSteps}>Alle genehmigten senden</button>
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
                              {step.status === 'approved' && (
                                <button className="btn btn-primary btn-sm" style={{fontSize:'0.7rem',padding:'2px 6px',background:'#22c55e',borderColor:'#22c55e'}} disabled={loading} onClick={() => sendCampaignStep(camp.lead_id, step.step)}>✉ Senden</button>
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
            {/* Tab navigation: Posts | Kalender | Woche generieren */}
            <div style={{display:'flex',gap:'0.25rem',marginBottom:'1rem',borderBottom:'2px solid #e5e7eb',paddingBottom:'0'}}>
              {[{id:'posts',label:'Posts'},{id:'calendar',label:'Content-Kalender'},{id:'weekly',label:'Woche generieren'}].map(t => (
                <button key={t.id} style={{padding:'0.5rem 1rem',background:socialView===t.id?'#1e293b':'transparent',color:socialView===t.id?'#fff':'#6b7280',border:'none',borderRadius:'0.5rem 0.5rem 0 0',fontWeight:socialView===t.id?600:400,fontSize:'0.8rem',cursor:'pointer',transition:'all 0.15s'}} onClick={()=>setSocialView(t.id)}>{t.label}</button>
              ))}
            </div>

            {/* ── Weekly Generator ── */}
            {socialView === 'weekly' && (
              <div className="card">
                <h2>Woche planen</h2>
                <p style={{color:'#6b7280',fontSize:'0.8rem',marginBottom:'1rem'}}>Generiert 2 Posts: einen f\u00fcr Dienstag, einen f\u00fcr Freitag. Beide m\u00fcssen vor Ver\u00f6ffentlichung freigegeben werden.</p>
                <div style={{display:'flex',gap:'1rem',flexWrap:'wrap',marginBottom:'1rem'}}>
                  <div className="form-group" style={{flex:1,minWidth:'200px'}}>
                    <label>Dienstag-Post: Kategorie</label>
                    <select id="tueTopic">
                      <option value="Regulatory Update">Regulatory Update</option>
                      <option value="Compliance Tip">Compliance Tip</option>
                      <option value="Industry Insight">Industry Insight</option>
                      <option value="Product Feature">Product Feature</option>
                      <option value="Thought Leadership">Thought Leadership</option>
                      <option value="Case Study">Case Study</option>
                    </select>
                  </div>
                  <div className="form-group" style={{flex:1,minWidth:'200px'}}>
                    <label>Freitag-Post: Kategorie</label>
                    <select id="friTopic">
                      <option value="Compliance Tip">Compliance Tip</option>
                      <option value="Regulatory Update">Regulatory Update</option>
                      <option value="Industry Insight">Industry Insight</option>
                      <option value="Product Feature">Product Feature</option>
                      <option value="Thought Leadership">Thought Leadership</option>
                      <option value="Case Study">Case Study</option>
                    </select>
                  </div>
                </div>
                <button className="btn btn-primary" disabled={loading || generatingWeekly} onClick={generateWeeklyPosts}>
                  {generatingWeekly ? 'Wird generiert...' : 'N\u00e4chste Woche generieren'}
                </button>
              </div>
            )}

            {/* ── Content Calendar ── */}
            {socialView === 'calendar' && (
              <div className="card">
                <h2>Content-Kalender</h2>
                {!contentCalendar ? <p className="empty">Lade...</p> : (
                  <div>
                    <h3 style={{fontSize:'0.85rem',fontWeight:600,marginBottom:'0.75rem',color:'#374151'}}>Geplant ({contentCalendar.total_scheduled})</h3>
                    {contentCalendar.upcoming?.length === 0 && <p className="empty">Keine geplanten Posts. Nutze "Woche generieren" um Posts zu planen.</p>}
                    {contentCalendar.upcoming?.map(p => {
                      const schedDate = p.scheduled_publish_date ? new Date(p.scheduled_publish_date) : null
                      const dayName = schedDate ? schedDate.toLocaleDateString('de-DE', { weekday: 'long' }) : ''
                      const dateStr = schedDate ? schedDate.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : ''
                      const s = Math.round((p.verification_score||0)*100)
                      const noFalse = !p.verification?.claims?.some(c=>c.verdict==='false')
                      const isPostable = s >= 90 && noFalse
                      return (
                        <div key={p.id} style={{padding:'0.75rem',marginBottom:'0.5rem',border:'1px solid #e5e7eb',borderRadius:'0.5rem',borderLeft:`4px solid ${isPostable ? '#22c55e' : p.verification_status === 'unverified' ? '#9ca3af' : '#ef4444'}`}}>
                          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'0.5rem'}}>
                            <div style={{display:'flex',gap:'0.5rem',alignItems:'center'}}>
                              <span style={{fontWeight:600,fontSize:'0.8rem',color:'#1e293b'}}>{dayName} {dateStr}</span>
                              {p.topic_category && <span className="badge badge-blue" style={{fontSize:'0.55rem'}}>{p.topic_category}</span>}
                              {isPostable && <span className="badge badge-green" style={{fontSize:'0.55rem'}}>Postbar ({s}%)</span>}
                              {p.verification_status !== 'unverified' && !isPostable && <span className="badge badge-red" style={{fontSize:'0.55rem'}}>Nicht postbar ({s}%)</span>}
                              {p.verification_status === 'unverified' && <span className="badge badge-gray" style={{fontSize:'0.55rem'}}>Ungepr\u00fcft</span>}
                            </div>
                            <div style={{display:'flex',gap:'0.375rem'}}>
                              {!p.is_published && !p.publish_pending && isPostable && (
                                <button className="btn btn-primary btn-sm" style={{fontSize:'0.65rem',padding:'0.25rem 0.5rem'}} onClick={() => publishToLinkedIn(p.id)}>Freigeben + Posten</button>
                              )}
                              {p.publish_pending && <span className="badge badge-yellow" style={{fontSize:'0.6rem'}}>In Warteschlange</span>}
                              {p.is_published && <span className="badge badge-green" style={{fontSize:'0.6rem'}}>Ver\u00f6ffentlicht</span>}
                            </div>
                          </div>
                          <div style={{fontSize:'0.75rem',color:'#374151',whiteSpace:'pre-wrap',maxHeight:'120px',overflow:'hidden',textOverflow:'ellipsis'}}>{p.content?.substring(0, 300)}{p.content?.length > 300 ? '...' : ''}</div>
                        </div>
                      )
                    })}
                    {contentCalendar.past?.length > 0 && (
                      <div style={{marginTop:'1.5rem'}}>
                        <h3 style={{fontSize:'0.85rem',fontWeight:600,marginBottom:'0.75rem',color:'#6b7280'}}>Vergangene geplante Posts</h3>
                        {contentCalendar.past.map(p => {
                          const schedDate = p.scheduled_publish_date ? new Date(p.scheduled_publish_date) : null
                          const dateStr = schedDate ? schedDate.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) : ''
                          return (
                            <div key={p.id} style={{padding:'0.5rem',marginBottom:'0.25rem',borderRadius:'0.375rem',background:'#f9fafb',fontSize:'0.72rem',color:'#6b7280',display:'flex',gap:'0.5rem',alignItems:'center'}}>
                              <span style={{fontWeight:500,minWidth:'50px'}}>{dateStr}</span>
                              <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.content?.substring(0, 100)}</span>
                              {p.is_published ? <span className="badge badge-green" style={{fontSize:'0.5rem'}}>Ver\u00f6ffentlicht</span> : <span className="badge badge-gray" style={{fontSize:'0.5rem'}}>Nicht ver\u00f6ffentlicht</span>}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Single Post Generator (original) ── */}
            {socialView === 'posts' && (
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
                  <input id="postCustomTopic" placeholder="z.B. DORA Deadline M\u00e4rz 2026, Digital Euro Update, NIS2..." onFocus={() => { document.getElementById('postTopic').value = '__custom__' }} />
                </div>
                <button className="btn btn-primary" disabled={loading} onClick={() => {
                  const sel = document.getElementById('postTopic').value
                  const custom = document.getElementById('postCustomTopic').value.trim()
                  const topic = sel === '__custom__' && custom ? custom : sel === '__custom__' ? 'Regulatory Update' : sel
                  generatePost(topic, 'LinkedIn')
                }}>Generieren</button>
              </div>
            </div>
            )}
            {socialView === 'posts' && (
            <div className="card"><h2>Posts ({posts.length})</h2>
              {posts.map(p => (
                <div key={p.id} className={`post-item ${p.is_copied ? 'post-copied' : ''}`}>
                  <div className="post-header">
                    <div style={{display:'flex',gap:'0.375rem',alignItems:'center',flexWrap:'wrap'}}>
                      <span className="badge badge-blue">LinkedIn</span>
                      {p.is_copied && <span className="badge badge-yellow">Kopiert</span>}
                      {/* Verification badge */}
                      {(p.verification_status === 'verified' || p.verification_status === 'issues_found') && (() => {
                        const s = Math.round((p.verification_score||0)*100)
                        const noFalse = !p.verification?.claims?.some(c=>c.verdict==='false')
                        if (s >= 90 && noFalse) return <span className="badge badge-green" style={{fontSize:'0.55rem'}}>✅ Postbar ({s}%)</span>
                        return <span className="badge badge-red" style={{fontSize:'0.55rem'}}>❌ Nicht postbar ({s}%)</span>
                      })()}
                      {p.verification_status === 'checking' && <span className="badge badge-yellow" style={{fontSize:'0.55rem'}}>⏳ Prüfung läuft...</span>}
                      {p.verification_status === 'unverified' && <span className="badge badge-gray" style={{fontSize:'0.55rem'}}>Ungeprüft</span>}
                      {p.scheduled_publish_date && !p.is_published && (
                        <span className="badge" style={{fontSize:'0.55rem',background:'#eff6ff',color:'#1d4ed8',border:'1px solid #bfdbfe'}}>
                          Geplant: {new Date(p.scheduled_publish_date).toLocaleDateString('de-DE', {weekday:'short',day:'2-digit',month:'2-digit'})}
                        </span>
                      )}
                    </div>
                    <div className="post-actions"><span className="sub">{p.created_date?.split('T')[0]}</span>
                      {p.verification_status !== 'checking' && <button className="btn btn-ghost btn-sm" style={{fontSize:'0.6rem'}} disabled={loading} onClick={() => verifyPost(p.id)}>{p.verification_status === 'unverified' ? '🔍 Prüfen' : '🔄 Erneut prüfen'}</button>}
                      {p.is_published ? (
                        <span className="badge badge-green" style={{fontSize:'0.6rem'}}>Veröffentlicht{p.published_at ? ` ${p.published_at.split('T')[0]}` : ''}</span>
                      ) : p.publish_pending ? (
                        <><span className="badge badge-yellow" style={{fontSize:'0.6rem'}}>Warteschlange — <span style={{fontFamily:'monospace'}}>⏱ {cronCountdown}</span></span>
                        <button className="btn btn-ghost btn-sm" style={{fontSize:'0.6rem',color:'#ef4444'}} onClick={() => cancelPublish(p.id)}>Abbrechen</button></>
                      ) : (
                        <button className="btn btn-primary btn-sm" style={{fontSize:'0.65rem',padding:'0.25rem 0.5rem'}} onClick={() => publishToLinkedIn(p.id)}>Auf LinkedIn posten</button>
                      )}
                      <button className="btn btn-ghost btn-sm" onClick={() => copyPost(p.id, p.content)}>{p.is_copied ? 'Erneut kopieren' : 'Kopieren'}</button>
                      {!p.is_published && !p.publish_pending && <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>}
                    </div>
                  </div>
                  {/* Verification panel — clear "postable or not" verdict */}
                  {p.verification && (() => {
                    const v = p.verification
                    const score = Math.round((p.verification_score||0)*100)
                    const claimsOk = v.claims ? v.claims.filter(c=>c.verdict==='verified').length : 0
                    const claimsTotal = v.claims ? v.claims.length : 0
                    const claimsBad = v.claims ? v.claims.filter(c=>c.verdict==='false'||c.verdict==='inaccurate').length : 0
                    const urlsOk = v.urls_checked ? v.urls_checked.filter(u=>u.reachable&&u.relevant).length : 0
                    const urlsTotal = v.urls_checked ? v.urls_checked.length : 0
                    const urlsBad = v.urls_checked ? v.urls_checked.filter(u=>!u.reachable).length : 0
                    const entOk = v.entities ? v.entities.filter(e=>e.exists).length : 0
                    const entTotal = v.entities ? v.entities.length : 0
                    const hasFalse = v.claims && v.claims.some(c=>c.verdict==='false')
                    const hasUnreachable = v.urls_checked && v.urls_checked.some(u=>!u.reachable)
                    // Verdict logic
                    let verdict, verdictColor, verdictBg, verdictBorder, verdictIcon
                    if (score >= 90 && !hasFalse) {
                      verdict = 'Postbar'; verdictColor = '#166534'; verdictBg = '#f0fdf4'; verdictBorder = '#bbf7d0'; verdictIcon = '\u2705'
                    } else {
                      verdict = 'Nicht postbar'; verdictColor = '#991b1b'; verdictBg = '#fef2f2'; verdictBorder = '#fecaca'; verdictIcon = '\u274c'
                    }
                    const expanded = verifyExpanded[p.id]
                    return (
                      <div style={{margin:'0.5rem 0',borderRadius:'0.5rem',border:`1px solid ${verdictBorder}`,overflow:'hidden'}}>
                        {/* Verdict header — always visible */}
                        <div style={{padding:'0.625rem 0.75rem',background:verdictBg,cursor:'pointer',display:'flex',alignItems:'center',justifyContent:'space-between'}} onClick={() => setVerifyExpanded(prev => ({...prev, [p.id]: !prev[p.id]}))}>
                          <div style={{display:'flex',alignItems:'center',gap:'0.5rem'}}>
                            <span style={{fontSize:'1.1rem'}}>{verdictIcon}</span>
                            <span style={{fontWeight:700,fontSize:'0.85rem',color:verdictColor}}>{verdict}</span>
                            <span style={{fontSize:'0.7rem',color:'#6b7280',marginLeft:'0.25rem'}}>Score: {score}%</span>
                          </div>
                          <div style={{display:'flex',alignItems:'center',gap:'0.75rem'}}>
                            <div style={{display:'flex',gap:'0.5rem',fontSize:'0.65rem',color:'#6b7280'}}>
                              <span>Fakten {claimsOk}/{claimsTotal}</span>
                              <span>·</span>
                              <span>URLs {urlsOk}/{urlsTotal}</span>
                              <span>·</span>
                              <span>Entitäten {entOk}/{entTotal}</span>
                            </div>
                            <span style={{fontSize:'0.6rem',color:'#9ca3af',transition:'transform 0.2s',transform:expanded?'rotate(180deg)':'rotate(0)'}}>▼</span>
                          </div>
                        </div>
                        {/* Critical issues + regenerate button */}
                        {verdict !== 'Postbar' && !p.is_published && (
                          <div style={{padding:'0.5rem 0.75rem',fontSize:'0.7rem',background:'#fff',borderTop:`1px solid ${verdictBorder}`,display:'flex',alignItems:'center',justifyContent:'space-between',gap:'0.5rem'}}>
                            <div style={{color:verdictColor}}>
                              {(claimsBad > 0 || urlsBad > 0) && <><strong>Kritisch:</strong>{' '}</>}
                              {claimsBad > 0 && <span>{claimsBad} falsche/ungenaue Behauptung{claimsBad>1?'en':''}</span>}
                              {claimsBad > 0 && urlsBad > 0 && <span> · </span>}
                              {urlsBad > 0 && <span>{urlsBad} nicht erreichbare URL{urlsBad>1?'s':''}</span>}
                            </div>
                            <button className="btn btn-primary btn-sm" style={{fontSize:'0.65rem',padding:'0.25rem 0.75rem',whiteSpace:'nowrap',flexShrink:0}} disabled={loading} onClick={(e) => { e.stopPropagation(); regeneratePost(p.id) }}>
                              🔄 Neu generieren
                            </button>
                          </div>
                        )}
                        {/* Expandable details */}
                        {expanded && (
                          <div style={{padding:'0.75rem',background:'#fff',fontSize:'0.72rem'}}>
                            {/* Claims */}
                            {v.claims && v.claims.length > 0 && (
                              <div style={{marginBottom:'0.75rem'}}>
                                <div style={{fontWeight:600,marginBottom:'0.375rem',fontSize:'0.75rem',color:'#374151'}}>Fakten-Check ({claimsOk}/{claimsTotal})</div>
                                {v.claims.map((c, i) => (
                                  <div key={i} style={{padding:'0.375rem 0.5rem',marginBottom:'0.25rem',background:c.verdict==='verified'?'#f0fdf4':c.verdict==='false'?'#fef2f2':'#fffbeb',borderRadius:'0.375rem',borderLeft:`3px solid ${c.verdict==='verified'?'#22c55e':c.verdict==='inaccurate'?'#f59e0b':c.verdict==='false'?'#ef4444':'#9ca3af'}`}}>
                                    <div style={{display:'flex',gap:'0.375rem',alignItems:'flex-start'}}>
                                      <span style={{flexShrink:0,fontSize:'0.8rem'}}>{c.verdict==='verified'?'\u2705':c.verdict==='inaccurate'?'\u26a0\ufe0f':c.verdict==='false'?'\u274c':'\u2753'}</span>
                                      <div style={{flex:1,minWidth:0}}>
                                        <div style={{fontStyle:'italic',color:'#374151',lineHeight:1.4}}>\u201e{c.claim}\u201c</div>
                                        <div style={{color:'#6b7280',marginTop:'0.25rem',lineHeight:1.4}}>{c.details}</div>
                                        {c.source_url && <a href={c.source_url} target="_blank" rel="noopener noreferrer" style={{color:'#2563eb',fontSize:'0.65rem',display:'inline-block',marginTop:'0.125rem'}}>{c.source_name || 'Quelle'}</a>}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* URLs */}
                            {v.urls_checked && v.urls_checked.length > 0 && (
                              <div style={{marginBottom:'0.75rem'}}>
                                <div style={{fontWeight:600,marginBottom:'0.375rem',fontSize:'0.75rem',color:'#374151'}}>URL-Check ({urlsOk}/{urlsTotal})</div>
                                {v.urls_checked.map((u, i) => (
                                  <div key={i} style={{padding:'0.25rem 0',display:'flex',gap:'0.375rem',alignItems:'flex-start',borderBottom:'1px solid #f3f4f6'}}>
                                    <span style={{flexShrink:0,fontSize:'0.8rem'}}>{u.reachable && u.relevant ? '\u2705' : u.reachable ? '\u26a0\ufe0f' : '\u274c'}</span>
                                    <div style={{flex:1,minWidth:0}}>
                                      <div style={{color:'#374151',wordBreak:'break-all',fontSize:'0.65rem',fontFamily:'monospace'}}>{u.url}</div>
                                      <div style={{color:'#6b7280',fontSize:'0.62rem',marginTop:'0.125rem',lineHeight:1.3}}>{u.details}</div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                            {/* Entities */}
                            {v.entities && v.entities.length > 0 && (
                              <div>
                                <div style={{fontWeight:600,marginBottom:'0.375rem',fontSize:'0.75rem',color:'#374151'}}>Entitäten ({entOk}/{entTotal})</div>
                                <div style={{display:'flex',flexWrap:'wrap',gap:'0.25rem'}}>
                                  {v.entities.map((e, i) => (
                                    <span key={i} style={{display:'inline-flex',alignItems:'center',gap:'0.25rem',padding:'0.2rem 0.5rem',background:e.exists?'#f0fdf4':'#fef2f2',border:`1px solid ${e.exists?'#bbf7d0':'#fecaca'}`,borderRadius:'1rem',fontSize:'0.62rem',color:e.exists?'#166534':'#991b1b'}} title={e.details}>
                                      {e.exists ? '\u2705' : '\u274c'} {e.name}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })()}
                  <div className="post-content" dangerouslySetInnerHTML={{__html: renderPostContent(p.content)}} />
                </div>
              ))}{posts.length === 0 && <p className="empty">Noch keine Posts. Wähle oben eine Kategorie und klicke "Generieren".</p>}
            </div>
            )}
          </div>
        )}

        {/* ═══ ANALYTICS ═════════════════════════════════ */}
        {section === 'analytics' && (
          <div key="analytics">
            <h1 className="page-title">Analytics</h1>
            <p className="page-desc">Übersicht aller versendeten E-Mails, Antworten und Kampagnen-Performance</p>

            {/* Check Replies & Bounces - prominent at top */}
            <div className="card" style={{background:'#f0f9ff',border:'1px solid #bae6fd'}}>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.75rem'}}>
                <div>
                  <h2 style={{margin:0,color:'#0c4a6e'}}>E-Mail-Prüfungen</h2>
                  <p className="sub" style={{margin:'0.25rem 0 0'}}>Antworten, Bounces und Abmeldungen prüfen (Gmail + Hostinger IMAP)</p>
                </div>
                <div style={{display:'flex',gap:'0.5rem',flexWrap:'wrap'}}>
                  <button className="btn btn-primary btn-sm" disabled={checkingReplies} onClick={checkReplies}>
                    {checkingReplies ? <><span className="spinner" style={{width:'14px',height:'14px',marginRight:'0.375rem'}} />Prüfe...</> : '📩 Gmail-Antworten'}
                  </button>
                  <button className="btn btn-secondary btn-sm" disabled={checkingRepliesImap} onClick={checkRepliesImap}>
                    {checkingRepliesImap ? <><span className="spinner" style={{width:'14px',height:'14px',marginRight:'0.375rem'}} />Prüfe...</> : '📨 IMAP-Antworten'}
                  </button>
                  <button className="btn btn-secondary btn-sm" disabled={checkingBounces} onClick={checkBouncesImap}>
                    {checkingBounces ? <><span className="spinner" style={{width:'14px',height:'14px',marginRight:'0.375rem'}} />Prüfe...</> : '⚠️ Bounce-Check'}
                  </button>
                </div>
              </div>
              {replyCheckResult && replyCheckResult.details && replyCheckResult.details.length > 0 && (
                <div style={{marginTop:'1rem',padding:'0.75rem',background:'#fff',borderRadius:'0.5rem',border:'1px solid #bbf7d0'}}>
                  <strong>Gmail-Ergebnis:</strong>
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
              {bounceCheckResult && (
                <div style={{marginTop:'0.75rem',padding:'0.75rem',background:'#fff',borderRadius:'0.5rem',border:`1px solid ${bounceCheckResult.bounces_found > 0 ? '#fecaca' : '#bbf7d0'}`}}>
                  <strong>Bounce-Check:</strong> {bounceCheckResult.bounces_found || 0} Bounces gefunden, {bounceCheckResult.leads_updated || 0} Leads aktualisiert
                </div>
              )}
              {imapReplyResult && (
                <div style={{marginTop:'0.75rem',padding:'0.75rem',background:'#fff',borderRadius:'0.5rem',border:`1px solid ${imapReplyResult.replies_found > 0 ? '#bbf7d0' : '#e5e7eb'}`}}>
                  <strong>IMAP-Check:</strong> {imapReplyResult.replies_found || 0} Antworten, {imapReplyResult.auto_opt_outs || 0} Abmeldungen
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

            {/* Open/Click Tracking Dashboard */}
            {analyticsSummary?.tracking_total_tracked > 0 && (
              <div className="card" style={{border:'1px solid #c7d2fe',background:'linear-gradient(135deg,#eef2ff 0%,#fff 100%)'}}>
                <h2 style={{color:'#3730a3'}}>Open/Click-Tracking</h2>
                <p className="sub">Echtzeit-Tracking für alle versendeten E-Mails mit Tracking-Pixel und Link-Wrapping</p>
                <div className="stats-grid" style={{marginTop:'0.75rem'}}>
                  <div className="stat-card" style={{borderColor:'#6366f1'}}><div className="stat-val">{analyticsSummary.tracking_total_tracked}</div><div className="stat-lbl">Getrackt</div></div>
                  <div className="stat-card" style={{borderColor:'#3b82f6'}}><div className="stat-val">{analyticsSummary.tracking_total_opened}</div><div className="stat-lbl">Geöffnet</div></div>
                  <div className="stat-card" style={{borderColor:'#8b5cf6'}}><div className="stat-val">{analyticsSummary.tracking_total_clicked}</div><div className="stat-lbl">Geklickt</div></div>
                  <div className="stat-card" style={{borderColor:'#3b82f6'}}><div className="stat-val">{analyticsSummary.tracking_open_rate}%</div><div className="stat-lbl">Open-Rate</div></div>
                  <div className="stat-card" style={{borderColor:'#8b5cf6'}}><div className="stat-val">{analyticsSummary.tracking_click_rate}%</div><div className="stat-lbl">Click-Rate</div></div>
                </div>
                {/* Daily breakdown chart */}
                {analyticsSummary.tracking_daily && Object.keys(analyticsSummary.tracking_daily).length > 0 && (
                  <div style={{marginTop:'1rem',paddingTop:'0.75rem',borderTop:'1px solid #e0e7ff'}}>
                    <h3 style={{fontSize:'0.875rem',fontWeight:600,color:'#4338ca',margin:'0 0 0.5rem'}}>Tagesübersicht</h3>
                    <div style={{display:'flex',flexDirection:'column',gap:'0.375rem'}}>
                      {Object.entries(analyticsSummary.tracking_daily).map(([day, d]) => (
                        <div key={day} style={{display:'flex',alignItems:'center',gap:'0.5rem',fontSize:'0.8rem'}}>
                          <span style={{width:'80px',color:'#6b7280',fontFamily:'monospace',fontSize:'0.75rem'}}>{day}</span>
                          <div style={{flex:1,display:'flex',gap:'2px',height:'20px'}}>
                            <div style={{width:`${d.sent > 0 ? Math.max(d.sent * 8, 2) : 0}px`,background:'#c7d2fe',borderRadius:'2px',height:'100%'}} title={`${d.sent} gesendet`} />
                            <div style={{width:`${d.opened > 0 ? Math.max(d.opened * 8, 2) : 0}px`,background:'#6366f1',borderRadius:'2px',height:'100%'}} title={`${d.opened} geöffnet`} />
                            <div style={{width:`${d.clicked > 0 ? Math.max(d.clicked * 8, 2) : 0}px`,background:'#8b5cf6',borderRadius:'2px',height:'100%'}} title={`${d.clicked} geklickt`} />
                          </div>
                          <div style={{display:'flex',gap:'0.75rem',fontSize:'0.7rem',color:'#6b7280',whiteSpace:'nowrap'}}>
                            <span>{d.sent} ✉</span>
                            <span style={{color:'#6366f1'}}>{d.opened} 👁</span>
                            <span style={{color:'#8b5cf6'}}>{d.clicked} 🔗</span>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div style={{display:'flex',gap:'1rem',marginTop:'0.5rem',fontSize:'0.7rem',color:'#9ca3af'}}>
                      <span>■ Gesendet</span>
                      <span style={{color:'#6366f1'}}>■ Geöffnet</span>
                      <span style={{color:'#8b5cf6'}}>■ Geklickt</span>
                    </div>
                  </div>
                )}
              </div>
            )}

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

            {/* LinkedIn Publishing Pipeline */}
            {(() => {
              const published = posts.filter(p => p.is_published)
              const pending = posts.filter(p => p.publish_pending && !p.is_published)
              const drafts = posts.filter(p => !p.is_published && !p.publish_pending)
              const scored = posts.filter(p => p.verification_score != null)
              const postbar = scored.filter(p => p.verification_score >= 0.9)
              const nichtPostbar = scored.filter(p => p.verification_score < 0.9)
              return (
                <div className="card" style={{border:'1px solid #bae6fd',background:'linear-gradient(135deg,#f0f9ff 0%,#fff 100%)'}}>
                  <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.5rem'}}>
                    <h2 style={{margin:0,color:'#0c4a6e'}}>LinkedIn Publishing-Pipeline</h2>
                    <div style={{display:'flex',alignItems:'center',gap:'0.5rem'}}>
                      <span style={{fontSize:'0.7rem',color:'#6b7280',display:'flex',alignItems:'center',gap:'0.375rem'}}>Auto-Publisher <span style={{fontFamily:'monospace',fontWeight:600,color: cronCountdown.startsWith('0:') ? '#f59e0b' : '#6b7280',background:'#f3f4f6',padding:'1px 6px',borderRadius:'0.25rem',fontSize:'0.75rem'}}>⏱ {cronCountdown}</span></span>
                      <span style={{width:8,height:8,borderRadius:'50%',background:pending.length > 0 ? '#f59e0b' : '#22c55e',display:'inline-block'}} />
                    </div>
                  </div>
                  <div className="stats-grid" style={{marginTop:'0.75rem'}}>
                    <div className="stat-card"><div className="stat-val">{posts.length}</div><div className="stat-lbl">Posts gesamt</div></div>
                    <div className="stat-card" style={pending.length > 0 ? {borderColor:'#f59e0b',background:'#fffbeb'} : {}}><div className="stat-val">{pending.length}</div><div className="stat-lbl">In Warteschlange</div></div>
                    <div className="stat-card" style={published.length > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{published.length}</div><div className="stat-lbl">Veröffentlicht</div></div>
                    <div className="stat-card"><div className="stat-val">{drafts.length}</div><div className="stat-lbl">Entwürfe</div></div>
                    <div className="stat-card" style={postbar.length > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{postbar.length}</div><div className="stat-lbl">Postbar (≥90%)</div></div>
                    <div className="stat-card" style={nichtPostbar.length > 0 ? {borderColor:'#ef4444'} : {}}><div className="stat-val">{nichtPostbar.length}</div><div className="stat-lbl">Nicht postbar</div></div>
                  </div>
                  {/* Post detail list */}
                  <div style={{marginTop:'1rem',display:'flex',flexDirection:'column',gap:'0.5rem'}}>
                    {posts.map(p => {
                      const status = p.is_published ? 'published' : p.publish_pending ? 'pending' : 'draft'
                      const colors = { published: {bg:'#f0fdf4',border:'#bbf7d0',badge:'#22c55e',label:'Veröffentlicht'}, pending: {bg:'#fffbeb',border:'#fde68a',badge:'#f59e0b',label:'Warteschlange'}, draft: {bg:'#f9fafb',border:'#e5e7eb',badge:'#9ca3af',label:'Entwurf'} }
                      const c = colors[status]
                      const score = p.verification_score != null ? Math.round(p.verification_score * 100) : null
                      const scoreColor = score != null ? (score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444') : '#9ca3af'
                      return (
                        <div key={p.id} style={{display:'flex',alignItems:'center',gap:'0.75rem',padding:'0.6rem 0.75rem',background:c.bg,border:`1px solid ${c.border}`,borderRadius:'0.5rem',fontSize:'0.85rem'}}>
                          <span style={{width:8,height:8,borderRadius:'50%',background:c.badge,flexShrink:0}} />
                          <div style={{flex:1,minWidth:0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.content?.substring(0, 80)}…</div>
                          <div style={{display:'flex',alignItems:'center',gap:'0.5rem',flexShrink:0}}>
                            {score != null && <span style={{fontSize:'0.7rem',fontWeight:600,color:scoreColor}}>{score}%</span>}
                            <span className={`badge ${status === 'published' ? 'badge-green' : status === 'pending' ? 'badge-yellow' : ''}`} style={{fontSize:'0.65rem'}}>{c.label}</span>
                            <span style={{fontSize:'0.7rem',color:'#6b7280',whiteSpace:'nowrap'}}>{p.published_at ? new Date(p.published_at).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : p.created_date ? new Date(p.created_date).toLocaleString('de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}) : ''}</span>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                  {/* Cron info */}
                  <div style={{marginTop:'0.75rem',paddingTop:'0.75rem',borderTop:'1px solid #e0f2fe',display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.5rem'}}>
                    <div style={{fontSize:'0.75rem',color:'#6b7280'}}>
                      Automatische Veröffentlichung via Cron (stündlich, Minute :50) als <strong>Harpocrates Solutions GmbH</strong>
                    </div>
                    <div style={{fontSize:'0.7rem',color:'#9ca3af',display:'flex',alignItems:'center',gap:'0.375rem'}}>
                      Nächster Lauf in <span style={{fontFamily:'monospace',fontWeight:600,color:cronCountdown.startsWith('0:') ? '#f59e0b' : '#6b7280'}}>{cronCountdown}</span>
                      <span style={{color:'#d1d5db'}}>·</span>
                      {(() => { const now = new Date(); const next = new Date(now); next.setMinutes(50, 0, 0); if (now.getMinutes() >= 50) next.setHours(next.getHours() + 1); return next.toLocaleString('de-DE', {hour:'2-digit',minute:'2-digit'}) })()} Uhr
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* LinkedIn Post Analytics */}
            <div className="card">
              <h2>LinkedIn Post-Statistiken</h2>
              {!linkedinAnalytics?.data?.length && !linkedinAnalytics?.summary?.has_token && (
                <div className="empty-cta">
                  <p style={{color:'#6b7280'}}>Noch keine veröffentlichten LinkedIn-Posts oder kein LinkedIn-Token konfiguriert.</p>
                  <p className="sub">Nach der Veröffentlichung eines Posts werden hier Impressionen, Klicks, Likes und Kommentare angezeigt.</p>
                </div>
              )}
              {linkedinAnalytics?.summary?.total_posts > 0 && (
                <>
                  <div className="stats-grid">
                    <div className="stat-card"><div className="stat-val">{linkedinAnalytics.summary.total_posts}</div><div className="stat-lbl">Posts gesamt</div></div>
                    <div className="stat-card" style={{borderColor:'#0a66c2'}}><div className="stat-val">{linkedinAnalytics.summary.total_impressions?.toLocaleString('de-DE') || 0}</div><div className="stat-lbl">Impressionen</div></div>
                    <div className="stat-card" style={{borderColor:'#0a66c2'}}><div className="stat-val">{linkedinAnalytics.summary.total_clicks || 0}</div><div className="stat-lbl">Klicks</div></div>
                    <div className="stat-card" style={{borderColor:'#22c55e'}}><div className="stat-val">{linkedinAnalytics.summary.total_likes || 0}</div><div className="stat-lbl">Likes</div></div>
                    <div className="stat-card"><div className="stat-val">{linkedinAnalytics.summary.total_comments || 0}</div><div className="stat-lbl">Kommentare</div></div>
                    <div className="stat-card"><div className="stat-val">{linkedinAnalytics.summary.total_shares || 0}</div><div className="stat-lbl">Shares</div></div>
                  </div>
                  {linkedinAnalytics.data?.length > 0 && (
                    <div style={{marginTop:'1rem'}}>
                      <table style={{width:'100%',borderCollapse:'collapse',fontSize:'0.85rem'}}>
                        <thead>
                          <tr style={{borderBottom:'2px solid #e5e7eb',textAlign:'left'}}>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600}}>Post</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Datum</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Impressionen</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Klicks</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Likes</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Kommentare</th>
                            <th style={{padding:'0.5rem',color:'#6b7280',fontWeight:600,textAlign:'center'}}>Shares</th>
                          </tr>
                        </thead>
                        <tbody>
                          {linkedinAnalytics.data.map(p => (
                            <tr key={p.id} style={{borderBottom:'1px solid #f3f4f6'}}>
                              <td style={{padding:'0.5rem 0.5rem',maxWidth:'300px',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.content}</td>
                              <td style={{padding:'0.5rem',textAlign:'center',whiteSpace:'nowrap',color:'#6b7280'}}>{p.published_at?.split('T')[0] || '—'}</td>
                              {p.stats ? (
                                <>
                                  <td style={{padding:'0.5rem',textAlign:'center',fontWeight:500}}>{p.stats.impressionCount?.toLocaleString('de-DE') || 0}</td>
                                  <td style={{padding:'0.5rem',textAlign:'center',fontWeight:500}}>{p.stats.clickCount || 0}</td>
                                  <td style={{padding:'0.5rem',textAlign:'center',fontWeight:500}}>{p.stats.likeCount || 0}</td>
                                  <td style={{padding:'0.5rem',textAlign:'center',fontWeight:500}}>{p.stats.commentCount || 0}</td>
                                  <td style={{padding:'0.5rem',textAlign:'center',fontWeight:500}}>{p.stats.shareCount || 0}</td>
                                </>
                              ) : (
                                <td colSpan={5} style={{padding:'0.5rem',textAlign:'center',color:'#9ca3af',fontSize:'0.8rem'}}>{p.linkedin_post_id ? 'Statistiken werden geladen...' : 'Keine Post-ID'}</td>
                              )}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {!linkedinAnalytics.summary.has_token && linkedinAnalytics.summary.total_posts > 0 && (
                    <div style={{marginTop:'0.75rem',padding:'0.5rem 0.75rem',background:'#fffbeb',border:'1px solid #fde68a',borderRadius:'0.375rem',fontSize:'0.8rem',color:'#92400e'}}>
                      Hinweis: Detaillierte Statistiken erfordern einen LinkedIn-Access-Token. Bitte in den Einstellungen konfigurieren.
                    </div>
                  )}
                </>
              )}
            </div>

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
                      {/* Follow-Up / Reset / Resend buttons */}
                      <div style={{marginTop:'0.75rem',paddingTop:'0.75rem',borderTop:'1px solid #e5e7eb',display:'flex',justifyContent:'flex-end',gap:'0.5rem',flexWrap:'wrap'}}>
                        {em.follow_up_subject && !em.date_follow_up_sent && (
                          <button className="btn btn-primary btn-sm" style={{fontSize:'0.75rem'}} disabled={loading} onClick={(e) => { e.stopPropagation(); sendFollowUp(em.id) }}>✉ Follow-Up senden</button>
                        )}
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

            {/* Activity Log / Audit Trail */}
            <div className="card">
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'0.75rem'}}>
                <div>
                  <h2 style={{margin:0}}>Aktivitätsprotokoll</h2>
                  <p className="sub" style={{margin:'0.25rem 0 0'}}>Letzte Aktionen im System (Versand, Imports, Änderungen)</p>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={loadActivityLog} disabled={loading}>Aktualisieren</button>
              </div>
              {activityLog.length === 0 && <p className="sub">Noch keine Aktivitäten erfasst.</p>}
              {activityLog.length > 0 && (
                <div style={{maxHeight:'400px',overflowY:'auto'}}>
                  <table className="data-table" style={{fontSize:'0.8rem'}}>
                    <thead>
                      <tr><th style={{width:'140px'}}>Zeitpunkt</th><th style={{width:'100px'}}>Aktion</th><th style={{width:'80px'}}>Typ</th><th>Details</th></tr>
                    </thead>
                    <tbody>
                      {activityLog.map(a => {
                        const actionLabels = {
                          email_sent: '✉️ Gesendet', email_drafted: '✏️ Entwurf', email_approved: '✅ Freigegeben',
                          user_invited: '👤 Eingeladen', company_added: '🏢 Unternehmen', lead_created: '👥 Kontakt',
                          bounce_detected: '⚠️ Bounce', reply_detected: '📨 Antwort', unsubscribe: '🚫 Abmeldung',
                          follow_up_sent: '🔁 Follow-Up', batch_send: '📧 Batch',
                        }
                        const entityLabels = { lead: 'Kontakt', company: 'Unternehmen', email: 'E-Mail', user: 'Benutzer', campaign: 'Kampagne' }
                        return (
                          <tr key={a.id}>
                            <td style={{fontFamily:'monospace',fontSize:'0.7rem',color:'#6b7280',whiteSpace:'nowrap'}}>
                              {a.created_at ? new Date(a.created_at).toLocaleString('de-DE', {day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—'}
                            </td>
                            <td><span style={{fontSize:'0.75rem'}}>{actionLabels[a.action] || a.action}</span></td>
                            <td><span className="badge" style={{fontSize:'0.6rem'}}>{entityLabels[a.entity_type] || a.entity_type}</span></td>
                            <td style={{color:'#374151',maxWidth:'400px',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{a.details}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══ SETTINGS ════════════════════════════════ */}
        {section === 'settings' && (
          <div key="settings">
            <h1 className="page-title">Einstellungen</h1>
            <p className="page-desc">Integrationen und Konfiguration</p>

            <div className="card">
              <h2>Konto</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Dein Benutzerkonto und Google-Anbindung</p>
              <div style={{display:'flex',alignItems:'center',gap:'0.75rem',flexWrap:'wrap',marginBottom:'0.75rem'}}>
                {authStatus?.avatar_url && <img src={authStatus.avatar_url} alt="" style={{width:'36px',height:'36px',borderRadius:'50%'}} />}
                <div>
                  <strong>{authStatus?.name || authStatus?.email}</strong>
                  <span className={`badge ${authStatus?.role === 'admin' ? 'badge-blue' : 'badge-gray'}`} style={{marginLeft:'0.5rem'}}>{authStatus?.role === 'admin' ? 'Admin' : 'Benutzer'}</span>
                  <div className="sub">{authStatus?.email}</div>
                </div>
                <button className="btn btn-secondary btn-sm" style={{marginLeft:'auto'}} onClick={handleLogout}>Abmelden</button>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:'0.5rem'}}>
                <span style={{color:'#22c55e',fontSize:'0.9rem'}}>●</span>
                <span className="sub">Google verbunden — Gmail-Prüfung aktiv, E-Mail-Versand über Hostinger SMTP</span>
              </div>
            </div>

            <div className="card">
              <h2>Absender & SMTP</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>E-Mail-Versand über Hostinger SMTP</p>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:'0.75rem',maxWidth:'700px'}}>
                <div className="form-group"><label>Name</label><input value="Martin Foerster" disabled style={{background:'#f9fafb'}} /></div>
                <div className="form-group"><label>Absender</label><input value="mf@harpocrates-corp.com" disabled style={{background:'#f9fafb'}} /></div>
                <div className="form-group"><label>Reply-To</label><input value="martin.foerster@gmail.com" disabled style={{background:'#f9fafb'}} /></div>
              </div>
              <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginTop:'0.5rem'}}>
                <span style={{color:'#22c55e',fontSize:'0.9rem'}}>●</span>
                <span className="sub">Hostinger SMTP (smtp.hostinger.com:465/SSL) — Konfiguration serverseitig verwaltet</span>
              </div>
            </div>

            <div className="card">
              <h2>LinkedIn-Integration</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Zugangsdaten für die direkte Veröffentlichung auf der Harpocrates LinkedIn-Seite.</p>
              {linkedinSettings.has_token
                ? <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'0.75rem',flexWrap:'wrap'}}>
                    <span style={{color:'#22c55e',fontSize:'1.1rem'}}>●</span>
                    <span>Access Token hinterlegt</span>
                    {linkedinSettings.org_id && <span className="badge badge-blue">Org: {linkedinSettings.org_id}</span>}
                    {linkedinSettings.person_urn && <span className="badge badge-green">Person: {linkedinSettings.person_urn}</span>}
                  </div>
                : <div style={{display:'flex',alignItems:'center',gap:'0.5rem',marginBottom:'0.75rem'}}>
                    <span style={{color:'#ef4444',fontSize:'1.1rem'}}>●</span>
                    <span>Nicht konfiguriert — bitte Access Token eintragen</span>
                  </div>}
              <form onSubmit={saveLinkedinSettings}>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:'0.75rem',maxWidth:'800px'}}>
                  <div className="form-group">
                    <label>Access Token</label>
                    <input name="linkedin_access_token" type="password" placeholder={linkedinSettings.has_token ? '••••••• (gespeichert)' : 'Bearer Token einfügen'} />
                  </div>
                  <div className="form-group">
                    <label>Organization ID</label>
                    <input name="linkedin_org_id" defaultValue={linkedinSettings.org_id} placeholder="z.B. 42109305" />
                  </div>
                  <div className="form-group">
                    <label>Person URN</label>
                    <input name="linkedin_person_urn" defaultValue={linkedinSettings.person_urn} placeholder="z.B. 4pSJ9zyosC" />
                  </div>
                </div>
                <button type="submit" className="btn btn-primary btn-sm" style={{marginTop:'0.5rem'}} disabled={loading}>Speichern</button>
              </form>
              <p className="sub" style={{fontSize:'0.65rem',marginTop:'0.5rem'}}>Posting-Strategie: Versucht zuerst als Organisation (w_organization_social), dann als Person (w_member_social). Person URN als Fallback eintragen.</p>
            </div>

            {/* ── Phase 2: Advanced Features ── */}
            <div className="card">
              <h2>Erweiterte Funktionen</h2>
              <p className="sub" style={{marginBottom:'0.75rem'}}>Warmup, Sender Pool, Tracking, Team-Verwaltung, A/B Tests</p>
              <Phase2Panel fetchJson={fetchJson} showSuccess={showSuccess} setError={setError} startLoading={startLoading} stopLoading={stopLoading} loading={loading} authStatus={authStatus} />
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

