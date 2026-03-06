import { useState, useEffect, useCallback, useRef } from 'react'

const API = '/api'

function App() {
  const [section, setSection] = useState('search')
  const [stats, setStats] = useState(null)
  const [companies, setCompanies] = useState([])
  const [leads, setLeads] = useState([])
  const [posts, setPosts] = useState([])
  const [addressBook, setAddressBook] = useState([])
  const [sentEmails, setSentEmails] = useState([])
  const [analyticsSummary, setAnalyticsSummary] = useState(null)
  const [authStatus, setAuthStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingMsg, setLoadingMsg] = useState('')
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [abFilter, setAbFilter] = useState('all')
  const [analyticsExpanded, setAnalyticsExpanded] = useState({})
  const [checkingReplies, setCheckingReplies] = useState(false)
  const [replyCheckResult, setReplyCheckResult] = useState(null)

  // Campaign wizard state
  const [campStep, setCampStep] = useState(1) // 1=select, 2=draft+edit, 3=approve, 4=send
  const [campSelected, setCampSelected] = useState(new Set()) // selected address book entry IDs
  const [campLeads, setCampLeads] = useState([]) // leads created for this campaign
  const [campActiveLeadId, setCampActiveLeadId] = useState(null) // selected lead for email preview
  const [campDraftSubject, setCampDraftSubject] = useState('')
  const [campDraftBody, setCampDraftBody] = useState('')
  const [campSendSelected, setCampSendSelected] = useState(new Set()) // step 4: which to send
  const [campDrafting, setCampDrafting] = useState(false) // drafting in progress

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

  const startLoading = (msg) => { setLoading(true); setLoadingMsg(msg || 'Wird verarbeitet...') }
  const stopLoading = () => { setLoading(false); setLoadingMsg('') }

  const loadDashboard = useCallback(async () => { try { const r = await fetchJson(`${API}/data/dashboard`); setStats(r.data) } catch {} }, [])
  const loadCompanies = useCallback(async () => { try { const r = await fetchJson(`${API}/data/companies`); setCompanies(r.data || []) } catch {} }, [])
  const loadLeads = useCallback(async () => { try { const r = await fetchJson(`${API}/data/leads`); setLeads(r.data || []) } catch {} }, [])
  const loadPosts = useCallback(async () => { try { const r = await fetchJson(`${API}/data/social-posts`); setPosts(r.data || []) } catch {} }, [])
  const loadAddressBook = useCallback(async () => { try { const r = await fetchJson(`${API}/data/address-book`); setAddressBook(r.data || []) } catch {} }, [])
  const loadSentEmails = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/sent-emails`); setSentEmails(r.data || []) } catch {} }, [])
  const loadAnalyticsSummary = useCallback(async () => { try { const r = await fetchJson(`${API}/analytics/summary`); setAnalyticsSummary(r.data || null) } catch {} }, [])
  const loadAuthStatus = useCallback(async () => { try { const r = await fetchJson(`${API}/auth/status`); setAuthStatus(r) } catch {} }, [])

  useEffect(() => { loadDashboard(); loadAuthStatus() }, [loadDashboard, loadAuthStatus])
  useEffect(() => {
    setError(''); setSuccessMsg('')
    if (section === 'search') { loadCompanies(); loadLeads() }
    else if (section === 'addressbook') { loadAddressBook() }
    else if (section === 'campaign') { loadAddressBook(); loadLeads() }
    else if (section === 'social') { loadPosts() }
    else if (section === 'analytics') { loadSentEmails(); loadAnalyticsSummary() }
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

  // ─── Analytics Actions ─────────────────────────────────
  const checkReplies = async () => {
    setCheckingReplies(true); setReplyCheckResult(null); setError('')
    try {
      const r = await fetchJson(`${API}/analytics/check-replies`, { method: 'POST' })
      setReplyCheckResult(r)
      showSuccess(`Prüfung abgeschlossen: ${r.replies || 0} Antworten, ${r.unsubscribes || 0} Abmeldungen, ${r.bounces || 0} Bounces`)
      await loadSentEmails()
      await loadAnalyticsSummary()
    } catch (e) { setError(e.message) }
    setCheckingReplies(false)
  }
  const toggleAnalyticsRow = (id) => setAnalyticsExpanded(prev => ({ ...prev, [id]: !prev[id] }))

  // ─── Actions ────────────────────────────────────────────
  const findCompanies = async () => {
    if (!selIndustries.length || !selRegions.length) { setError('Bitte mindestens eine Branche und eine Region auswählen.'); return }
    startLoading('Unternehmen werden gesucht...'); setError('')
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
    stopLoading()
  }

  const findContacts = async (companyId) => {
    startLoading('Kontakte werden gesucht...'); setError('')
    try { const r = await fetchJson(`${API}/prospecting/find-contacts/${companyId}`, { method: 'POST' }); showSuccess(`${r.total || 0} Kontakte`); await loadLeads() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const findAllContacts = async () => {
    startLoading('Alle Kontakte werden gesucht...'); setError('')
    try { const r = await fetchJson(`${API}/prospecting/find-contacts-all`, { method: 'POST' }); showSuccess(`${r.total_new || 0} neue Kontakte`); await loadLeads() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const verifyEmail = async (leadId) => {
    startLoading('E-Mail wird verifiziert...'); setError('')
    try { const r = await fetchJson(`${API}/prospecting/verify-email/${leadId}`, { method: 'POST' }); showSuccess(`Verifiziert: ${r.data?.email || 'OK'}`); await loadLeads() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const verifyAllEmails = async () => {
    startLoading('E-Mails werden verifiziert...'); setError('')
    try { const r = await fetchJson(`${API}/prospecting/verify-all`, { method: 'POST' }); showSuccess(`${r.verified || 0}/${r.total || 0} verifiziert`); await loadLeads() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const addToAddressBook = async (leadId) => {
    startLoading('Wird ins Adressbuch übernommen...'); setError('')
    try { await fetchJson(`${API}/data/address-book/from-lead/${leadId}`, { method: 'POST' }); showSuccess('Ins Adressbuch übernommen'); await loadAddressBook() }
    catch (e) { setError(e.message) } stopLoading()
  }
  const addAllVerifiedToAddressBook = async () => {
    startLoading('Verifizierte Kontakte werden ins Adressbuch übernommen...'); setError('')
    const verified = leads.filter(l => l.email_verified)
    let added = 0
    for (const l of verified) {
      try { await fetchJson(`${API}/data/address-book/from-lead/${l.id}`, { method: 'POST' }); added++ } catch {}
    }
    showSuccess(`${added} Kontakte ins Adressbuch übernommen`)
    await loadAddressBook()
    stopLoading()
  }
  const removeFromAddressBook = async (entryId) => {
    try { await fetchJson(`${API}/data/address-book/${entryId}`, { method: 'DELETE' }); await loadAddressBook() }
    catch (e) { setError(e.message) }
  }
  const setContactStatus = async (entryId, newStatus) => {
    startLoading(newStatus === 'blocked' ? 'Kontakt wird gesperrt...' : 'Kontakt wird freigeschaltet...'); setError('')
    try {
      await fetchJson(`${API}/data/address-book/${entryId}/status`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contact_status: newStatus }) })
      showSuccess(newStatus === 'blocked' ? 'Kontakt gesperrt' : 'Kontakt freigeschaltet')
      await loadAddressBook()
    } catch (e) { setError(e.message) }
    stopLoading()
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
  const exportCSV = (type) => window.open(`${API}/data/${type}/export`, '_blank')

  // Analytics actions
  const checkReplies = async () => {
    startLoading('Gmail wird auf Antworten geprüft...'); setError('')
    try {
      const r = await fetchJson(`${API}/analytics/check-replies`, { method: 'POST' })
      const parts = []
      if (r.replies > 0) parts.push(`${r.replies} Antwort${r.replies > 1 ? 'en' : ''}`)
      if (r.unsubscribes > 0) parts.push(`${r.unsubscribes} Abmeldung${r.unsubscribes > 1 ? 'en' : ''}`)
      if (r.bounces > 0) parts.push(`${r.bounces} Bounce${r.bounces > 1 ? 's' : ''}`)
      if (parts.length > 0) showSuccess(`Gefunden: ${parts.join(', ')}`)
      else showSuccess('Keine neuen Reaktionen gefunden.')
      await loadSentEmails(); await loadAnalyticsSummary()
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const [analyticsExpanded, setAnalyticsExpanded] = useState(null) // expanded email ID

  const renderPostContent = (text) => {
    if (!text) return ''
    const escaped = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const withLinks = escaped.replace(
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

    // Import selected address book contacts as leads
    const selectedContacts = activeContacts.filter(a => campSelected.has(a.id))
    const newLeadIds = []

    for (const contact of selectedContacts) {
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
      showSuccess(`${r.sent || 0} gesendet${r.failed ? `, ${r.failed} fehlgeschlagen` : ''}${r.skipped ? `, ${r.skipped} übersprungen` : ''}`)
      // Reload
      const leadsResp = await fetchJson(`${API}/data/leads`)
      const allLeads = leadsResp.data || []
      setCampLeads(allLeads.filter(l => campLeads.some(cl => cl.id === l.id)))
    } catch (e) { setError(e.message) }
    stopLoading()
  }

  const menuItems = [
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
          <div key={s.num} className={`wizard-step ${campStep === s.num ? 'active' : ''} ${campStep > s.num ? 'done' : ''}`}>
            <div className="wizard-num">{campStep > s.num ? '✓' : s.num}</div>
            <span className="wizard-label">{s.label}</span>
            {i < steps.length - 1 && <div className="wizard-line" />}
          </div>
        ))}
      </div>
    )
  }

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
        {loading && <div className="msg msg-loading"><span className="spinner" />{loadingMsg || 'Wird verarbeitet...'}</div>}

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
                          {l.email && !l.email_verified && <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => verifyEmail(l.id)}>Verifizieren</button>}
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

        {/* ═══ KAMPAGNE (Wizard) ═══════════════════════ */}
        {section === 'campaign' && (
          <div key="campaign">
            <h1 className="page-title">E-Mail-Kampagne</h1>
            <p className="page-desc">Kontakte auswählen → Personalisierte E-Mails erstellen → Freigeben → Versenden</p>

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
                  <p className="empty">Keine nutzbaren Kontakte im Adressbuch. Bitte zuerst über die Suche Kontakte verifizieren und ins Adressbuch übernehmen.</p>
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
                      <button className="btn btn-primary" disabled={loading || campSelected.size === 0} onClick={campGoToStep2}>
                        Weiter — Entwürfe erstellen
                      </button>
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
          </div>
        )}

        {/* ═══ LINKEDIN ════════════════════════════════ */}
        {section === 'social' && (
          <div key="social">
            <h1 className="page-title">LinkedIn</h1>
            <div className="card">
              <h2>Post generieren</h2>
              <div style={{display:'flex',gap:'0.5rem',alignItems:'end',flexWrap:'wrap'}}>
                <div className="form-group" style={{flex:1,minWidth:'150px'}}><label>Thema</label>
                  <select id="postTopic"><option value="Regulatory Update">Regulatory Update</option><option value="Compliance Tip">Compliance Tip</option><option value="Industry Insight">Industry Insight</option><option value="Product Feature">Product Feature</option><option value="Thought Leadership">Thought Leadership</option><option value="Case Study">Case Study</option></select>
                </div>
                <button className="btn btn-primary" disabled={loading} onClick={() => generatePost(document.getElementById('postTopic').value, 'LinkedIn')}>Generieren</button>
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
                      <button className="btn btn-ghost btn-sm" onClick={() => copyPost(p.id, p.content)}>{p.is_copied ? 'Erneut kopieren' : 'Kopieren'}</button>
                      <button className="btn btn-ghost btn-sm" style={{color:'#ef4444'}} onClick={() => deletePost(p.id)}>×</button>
                    </div>
                  </div>
                  <div className="post-content" dangerouslySetInnerHTML={{__html: renderPostContent(p.content)}} />
                </div>
              ))}{posts.length === 0 && <p className="empty">Noch keine Posts.</p>}
            </div>
          </div>
        )}

        {/* ═══ ANALYTICS ═════════════════════════════════ */}
        {section === 'analytics' && (
          <div key="analytics">
            <h1 className="page-title">Analytics</h1>
            <p className="page-desc">Übersicht aller versendeten E-Mails, Antworten und Kampagnen-Performance</p>

            {/* Summary Stats */}
            <div className="card">
              <h2>Übersicht</h2>
              <div className="stats-grid">
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_sent || 0}</div><div className="stat-lbl">Gesendet</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.total_delivered || 0}</div><div className="stat-lbl">Zugestellt</div></div>
                <div className="stat-card" style={analyticsSummary?.total_bounced > 0 ? {borderColor:'#ef4444'} : {}}><div className="stat-val">{analyticsSummary?.total_bounced || 0}</div><div className="stat-lbl">Bounced</div></div>
                <div className="stat-card" style={analyticsSummary?.total_replied > 0 ? {borderColor:'#22c55e'} : {}}><div className="stat-val">{analyticsSummary?.total_replied || 0}</div><div className="stat-lbl">Antworten</div></div>
                <div className="stat-card" style={analyticsSummary?.total_unsubscribed > 0 ? {borderColor:'#f59e0b'} : {}}><div className="stat-val">{analyticsSummary?.total_unsubscribed || 0}</div><div className="stat-lbl">Abgemeldet</div></div>
                <div className="stat-card"><div className="stat-val">{analyticsSummary?.reply_rate || 0}%</div><div className="stat-lbl">Antwort-Rate</div></div>
              </div>
            </div>

            {/* Check Replies Button */}
            <div className="card">
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',flexWrap:'wrap',gap:'0.75rem'}}>
                <div>
                  <h2 style={{margin:0}}>Gmail-Antworten prüfen</h2>
                  <p className="sub" style={{margin:'0.25rem 0 0'}}>Durchsucht Gmail nach Antworten, Abmeldungen und Bounces</p>
                </div>
                <button className="btn btn-primary" disabled={checkingReplies} onClick={checkReplies}>
                  {checkingReplies ? <><span className="spinner" style={{width:'14px',height:'14px',marginRight:'0.5rem'}} />Wird geprüft...</> : 'Antworten prüfen'}
                </button>
              </div>
              {replyCheckResult && replyCheckResult.details && replyCheckResult.details.length > 0 && (
                <div style={{marginTop:'1rem',padding:'0.75rem',background:'#f0fdf4',borderRadius:'0.5rem',border:'1px solid #bbf7d0'}}>
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

            {/* Sent Emails List */}
            <div className="card">
              <h2>Versendete E-Mails ({sentEmails.length})</h2>
              {sentEmails.length === 0 && <p className="empty">Noch keine E-Mails versendet.</p>}
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
