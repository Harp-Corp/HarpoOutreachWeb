// Phase2Sections.jsx — Warmup, Sender Pool, Tracking, Users, A/B Tests
// Imported and rendered from App.jsx inside settings section

import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export function Phase2Panel({ fetchJson, showSuccess, setError, startLoading, stopLoading, loading, authStatus }) {
  const isAdmin = authStatus?.role === 'admin'
  const [tab, setTab] = useState('warmup')
  const [warmupAccounts, setWarmupAccounts] = useState([])
  const [senderPool, setSenderPool] = useState({ senders: [], capacity: {} })
  const [trackingDashboard, setTrackingDashboard] = useState(null)
  const [users, setUsers] = useState([])
  const [activityLog, setActivityLog] = useState([])
  const [abTests, setAbTests] = useState([])
  const [showAddForm, setShowAddForm] = useState(false)

  const loadWarmup = useCallback(async () => { try { const r = await fetchJson(`${API}/warmup/accounts`); setWarmupAccounts(r.data || []) } catch {} }, [fetchJson])
  const loadPool = useCallback(async () => { try { const r = await fetchJson(`${API}/sender-pool`); setSenderPool(r.data || { senders: [], capacity: {} }) } catch {} }, [fetchJson])
  const loadTracking = useCallback(async () => { try { const r = await fetchJson(`${API}/tracking/dashboard`); setTrackingDashboard(r.data || null) } catch {} }, [fetchJson])
  const loadUsers = useCallback(async () => { try { const r = await fetchJson(`${API}/auth/users`); setUsers(r.data || []) } catch {} }, [fetchJson])
  const loadActivity = useCallback(async () => { try { const r = await fetchJson(`${API}/activity-log?limit=20`); setActivityLog(r.data || []) } catch {} }, [fetchJson])
  const loadABTests = useCallback(async () => { try { const r = await fetchJson(`${API}/ab-tests`); setAbTests(r.data || []) } catch {} }, [fetchJson])

  useEffect(() => {
    if (tab === 'warmup') loadWarmup()
    else if (tab === 'senders') loadPool()
    else if (tab === 'tracking') loadTracking()
    else if (tab === 'users') { loadUsers(); loadActivity() }
    else if (tab === 'abtests') loadABTests()
  }, [tab, loadWarmup, loadPool, loadTracking, loadUsers, loadActivity, loadABTests])

  const tabs = [
    { id: 'warmup', label: '🔥 Warmup', desc: 'Email-Aufwärmung' },
    { id: 'senders', label: '🔄 Sender Pool', desc: 'Inbox Rotation' },
    { id: 'tracking', label: '📈 Tracking', desc: 'Opens & Clicks' },
    { id: 'users', label: '👥 Team', desc: 'Multi-User' },
    { id: 'abtests', label: '🧪 A/B Tests', desc: 'Varianten testen' },
  ]

  // Add warmup account
  const addWarmupAccount = async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    try {
      startLoading('Account wird hinzugefügt...')
      await fetchJson(`${API}/warmup/accounts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: fd.get('email'),
          smtp_user: fd.get('smtp_user') || fd.get('email'),
          smtp_password: fd.get('smtp_password'),
          max_daily_limit: parseInt(fd.get('max_daily_limit') || '50'),
          display_name: fd.get('display_name') || 'Martin Foerster',
          reply_to_email: fd.get('reply_to_email') || 'martin.foerster@gmail.com',
        })
      })
      showSuccess('Warmup-Account hinzugefügt und Warmup gestartet')
      setShowAddForm(false)
      loadWarmup()
    } catch (err) { setError(err.message) }
    finally { stopLoading() }
  }

  // Add sender to pool
  const addSender = async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    try {
      startLoading('Sender wird hinzugefügt...')
      await fetchJson(`${API}/sender-pool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: fd.get('email'),
          smtp_user: fd.get('smtp_user') || fd.get('email'),
          smtp_password: fd.get('smtp_password'),
          daily_limit: parseInt(fd.get('daily_limit') || '30'),
          display_name: fd.get('display_name') || 'Martin Foerster',
          reply_to: fd.get('reply_to') || 'martin.foerster@gmail.com',
        })
      })
      showSuccess('Sender zum Pool hinzugefügt')
      setShowAddForm(false)
      loadPool()
    } catch (err) { setError(err.message) }
    finally { stopLoading() }
  }

  // Invite user
  const inviteUser = async (e) => {
    e.preventDefault()
    const fd = new FormData(e.target)
    const pw = fd.get('password') || ''
    if (pw && pw.length < 8) { setError('Passwort muss mindestens 8 Zeichen lang sein.'); return }
    try {
      startLoading('Einladung wird gesendet...')
      await fetchJson(`${API}/auth/users/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: fd.get('email'),
          name: fd.get('name'),
          role: fd.get('role') || 'user',
          password: pw,
        })
      })
      showSuccess(pw ? 'Benutzer eingeladen (mit Passwort-Login)' : 'Benutzer eingeladen (Google-Login)')
      setShowAddForm(false)
      loadUsers()
    } catch (err) { setError(err.message) }
    finally { stopLoading() }
  }

  // Admin set password for a user
  const setUserPassword = async (userId) => {
    const pw = prompt('Neues Passwort eingeben (mind. 8 Zeichen):')
    if (!pw) return
    if (pw.length < 8) { setError('Passwort muss mindestens 8 Zeichen lang sein.'); return }
    try {
      startLoading('Passwort wird gesetzt...')
      await fetchJson(`${API}/auth/users/${userId}/set-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pw })
      })
      showSuccess('Passwort gesetzt')
      loadUsers()
    } catch (err) { setError(err.message) }
    finally { stopLoading() }
  }

  // Delete warmup account
  const deleteWarmupAccount = async (id) => {
    if (!confirm('Account wirklich entfernen?')) return
    try { await fetchJson(`${API}/warmup/accounts/${id}`, { method: 'DELETE' }); loadWarmup() } catch {}
  }

  // Delete sender
  const deleteSender = async (id) => {
    if (!confirm('Sender wirklich entfernen?')) return
    try { await fetchJson(`${API}/sender-pool/${id}`, { method: 'DELETE' }); loadPool() } catch {}
  }

  // Deactivate user
  const deactivateUser = async (id) => {
    if (!confirm('Benutzer wirklich deaktivieren?')) return
    try { await fetchJson(`${API}/auth/users/${id}`, { method: 'DELETE' }); loadUsers() } catch {}
  }

  const warmupProgress = (day, complete) => {
    if (complete) return 100
    return Math.min(100, Math.round((day / 22) * 100))
  }

  return (
    <div>
      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {tabs.map(t => (
          <button key={t.id} className={`btn ${tab === t.id ? 'btn-primary' : 'btn-ghost'} btn-sm`}
            onClick={() => { setTab(t.id); setShowAddForm(false) }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Warmup Tab ── */}
      {tab === 'warmup' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h2 style={{ margin: 0 }}>Email-Warmup</h2>
              <p className="sub">Neue Absender-Adressen werden schrittweise aufgewärmt (5→10→20→35→50 Emails/Tag über 22 Tage)</p>
            </div>
            <button className="btn btn-primary btn-sm" onClick={() => setShowAddForm(!showAddForm)}>+ Account</button>
          </div>

          {showAddForm && (
            <div className="card" style={{ marginBottom: '1rem', background: '#f9fafb' }}>
              <form onSubmit={addWarmupAccount}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div className="form-group"><label>E-Mail-Adresse</label><input name="email" required placeholder="sender@harpocrates-corp.com" /></div>
                  <div className="form-group"><label>SMTP User</label><input name="smtp_user" placeholder="= E-Mail" /></div>
                  <div className="form-group"><label>SMTP Passwort</label><input name="smtp_password" type="password" required /></div>
                  <div className="form-group"><label>Max. Tageslimit</label><input name="max_daily_limit" type="number" defaultValue="50" /></div>
                  <div className="form-group"><label>Anzeigename</label><input name="display_name" defaultValue="Martin Foerster" /></div>
                  <div className="form-group"><label>Reply-To</label><input name="reply_to_email" defaultValue="martin.foerster@gmail.com" /></div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>Hinzufügen & Warmup starten</button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAddForm(false)}>Abbrechen</button>
                </div>
              </form>
            </div>
          )}

          {warmupAccounts.length === 0 && !showAddForm && (
            <div className="card"><p className="sub" style={{ textAlign: 'center', padding: '2rem 0' }}>Noch keine Warmup-Accounts. Füge einen Absender hinzu, um das Aufwärmen zu starten.</p></div>
          )}

          {warmupAccounts.map(a => (
            <div key={a.id} className="card" style={{ marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong>{a.email}</strong>
                  {a.display_name && <span className="sub" style={{ marginLeft: '0.5rem' }}>({a.display_name})</span>}
                  {a.is_primary && <span className="badge badge-blue" style={{ marginLeft: '0.5rem' }}>Primär</span>}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className={`badge ${a.warmup_complete ? 'badge-green' : 'badge-yellow'}`}>
                    {a.warmup_complete ? 'Aufgewärmt' : `Tag ${a.warmup_day}/22`}
                  </span>
                  <span className={`badge ${a.is_active ? 'badge-green' : 'badge-red'}`}>
                    {a.is_active ? 'Aktiv' : 'Pausiert'}
                  </span>
                  <button className="btn btn-ghost btn-sm" onClick={() => deleteWarmupAccount(a.id)} title="Entfernen">✕</button>
                </div>
              </div>
              {/* Progress bar */}
              <div style={{ marginTop: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#6b7280', marginBottom: '0.25rem' }}>
                  <span>Warmup-Fortschritt</span>
                  <span>{a.emails_sent_today}/{a.daily_limit} heute gesendet · {a.remaining_today} verbleibend</span>
                </div>
                <div style={{ height: '6px', background: '#e5e7eb', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${warmupProgress(a.warmup_day, a.warmup_complete)}%`, background: a.warmup_complete ? '#22c55e' : '#f59e0b', borderRadius: '3px', transition: 'width 0.3s' }} />
                </div>
                <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.5rem', fontSize: '0.7rem', color: '#9ca3af' }}>
                  <span>Reputation: {a.reputation_score}/100</span>
                  <span>Limit: {a.daily_limit}/{a.max_daily_limit}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Sender Pool Tab ── */}
      {tab === 'senders' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h2 style={{ margin: 0 }}>Sender Pool</h2>
              <p className="sub">Verteile E-Mails automatisch über mehrere Absender (Inbox Rotation)</p>
            </div>
            <button className="btn btn-primary btn-sm" onClick={() => setShowAddForm(!showAddForm)}>+ Sender</button>
          </div>

          {/* Capacity overview */}
          {senderPool.capacity && senderPool.capacity.active_senders > 0 && (
            <div className="card" style={{ marginBottom: '1rem', background: '#f0fdf4' }}>
              <div style={{ display: 'flex', gap: '2rem', fontSize: '0.875rem' }}>
                <div><strong>{senderPool.capacity.active_senders}</strong> <span className="sub">Aktive Sender</span></div>
                <div><strong>{senderPool.capacity.total_daily_limit}</strong> <span className="sub">Tages-Kapazität</span></div>
                <div><strong>{senderPool.capacity.total_sent_today}</strong> <span className="sub">Heute gesendet</span></div>
                <div><strong>{senderPool.capacity.remaining_today}</strong> <span className="sub">Verbleibend</span></div>
              </div>
            </div>
          )}

          {showAddForm && (
            <div className="card" style={{ marginBottom: '1rem', background: '#f9fafb' }}>
              <form onSubmit={addSender}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div className="form-group"><label>E-Mail-Adresse</label><input name="email" required placeholder="sender2@harpocrates-corp.com" /></div>
                  <div className="form-group"><label>SMTP User</label><input name="smtp_user" placeholder="= E-Mail" /></div>
                  <div className="form-group"><label>SMTP Passwort</label><input name="smtp_password" type="password" required /></div>
                  <div className="form-group"><label>Tageslimit</label><input name="daily_limit" type="number" defaultValue="30" /></div>
                  <div className="form-group"><label>Anzeigename</label><input name="display_name" defaultValue="Martin Foerster" /></div>
                  <div className="form-group"><label>Reply-To</label><input name="reply_to" defaultValue="martin.foerster@gmail.com" /></div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>Hinzufügen</button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAddForm(false)}>Abbrechen</button>
                </div>
              </form>
            </div>
          )}

          {(senderPool.senders || []).length === 0 && !showAddForm && (
            <div className="card"><p className="sub" style={{ textAlign: 'center', padding: '2rem 0' }}>Kein Sender im Pool. Füge Absender-Adressen hinzu, um Inbox Rotation zu nutzen.</p></div>
          )}

          {(senderPool.senders || []).map(s => (
            <div key={s.id} className="card" style={{ marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <strong>{s.email}</strong>
                  <span className="sub" style={{ marginLeft: '0.5rem' }}>({s.display_name})</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className={`badge ${s.health_status === 'healthy' ? 'badge-green' : s.health_status === 'throttled' ? 'badge-yellow' : 'badge-red'}`}>
                    {s.health_status === 'healthy' ? 'Gesund' : s.health_status === 'throttled' ? 'Gedrosselt' : 'Problem'}
                  </span>
                  <span className="sub">{s.emails_sent_today}/{s.daily_limit}</span>
                  {s.bounce_rate > 0 && <span className="badge badge-red">Bounce: {s.bounce_rate}%</span>}
                  <button className="btn btn-ghost btn-sm" onClick={() => deleteSender(s.id)} title="Entfernen">✕</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Tracking Tab ── */}
      {tab === 'tracking' && (
        <div>
          <h2>Open/Click Tracking</h2>
          <p className="sub">Öffnungs- und Klickraten deiner E-Mails in Echtzeit</p>

          {trackingDashboard && trackingDashboard.overview ? (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="card" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#1a365d' }}>{trackingDashboard.overview.total_sent}</div>
                  <div className="sub">Gesendet</div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#22c55e' }}>{trackingDashboard.overview.open_rate}%</div>
                  <div className="sub">Öffnungsrate</div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: '#3b82f6' }}>{trackingDashboard.overview.click_rate}%</div>
                  <div className="sub">Klickrate</div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 700, color: trackingDashboard.overview.bounce_rate > 5 ? '#ef4444' : '#6b7280' }}>{trackingDashboard.overview.bounce_rate}%</div>
                  <div className="sub">Bounce-Rate</div>
                </div>
              </div>

              {/* Daily breakdown */}
              {Object.keys(trackingDashboard.daily || {}).length > 0 && (
                <div className="card">
                  <h3 style={{ marginBottom: '0.75rem' }}>Tagesübersicht</h3>
                  <table className="data-table">
                    <thead><tr><th>Datum</th><th>Gesendet</th><th>Geöffnet</th><th>Geklickt</th></tr></thead>
                    <tbody>
                      {Object.entries(trackingDashboard.daily).map(([day, d]) => (
                        <tr key={day}>
                          <td>{day}</td>
                          <td>{d.sent}</td>
                          <td>{d.opened}</td>
                          <td>{d.clicked}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <div className="card"><p className="sub" style={{ textAlign: 'center', padding: '2rem 0' }}>Noch keine Tracking-Daten. Daten erscheinen, sobald E-Mails mit Tracking versendet werden.</p></div>
          )}
        </div>
      )}

      {/* ── Users Tab ── */}
      {tab === 'users' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <div>
              <h2 style={{ margin: 0 }}>Team-Verwaltung</h2>
              <p className="sub">Bis zu 10 Benutzer können die Plattform nutzen</p>
            </div>
            {isAdmin && <button className="btn btn-primary btn-sm" onClick={() => setShowAddForm(!showAddForm)}>+ Einladen</button>}
          </div>
          {!isAdmin && <div className="card" style={{ marginBottom: '1rem', background: '#f0f9ff', border: '1px solid #bae6fd' }}><p className="sub" style={{textAlign:'center',padding:'0.5rem 0'}}>Nur Administratoren können Benutzer verwalten.</p></div>}

          {showAddForm && (
            <div className="card" style={{ marginBottom: '1rem', background: '#f9fafb' }}>
              <form onSubmit={inviteUser}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div className="form-group"><label>E-Mail</label><input name="email" required placeholder="user@firma.de" /></div>
                  <div className="form-group"><label>Name</label><input name="name" placeholder="Max Mustermann" /></div>
                  <div className="form-group">
                    <label>Passwort (optional)</label>
                    <input name="password" type="password" placeholder="Leer = nur Google-Login" minLength={8} />
                  </div>
                  <div className="form-group">
                    <label>Rolle</label>
                    <select name="role"><option value="user">Benutzer</option><option value="admin">Admin</option></select>
                  </div>
                </div>
                <p className="sub" style={{ margin: '0.5rem 0' }}>Mit Passwort: Nutzer kann sich per E-Mail/Passwort anmelden (kein Google nötig). Ohne Passwort: Nutzer meldet sich über Google an.</p>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={loading}>Einladen</button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAddForm(false)}>Abbrechen</button>
                </div>
              </form>
            </div>
          )}

          <div className="card" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h3>Benutzer ({users.length}/10)</h3>
            </div>
            {users.length === 0 && <p className="sub">Noch keine Benutzer angelegt.</p>}
            {users.map(u => (
              <div key={u.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid #f3f4f6' }}>
                <div>
                  <strong>{u.name || u.email}</strong>
                  <span className="sub" style={{ marginLeft: '0.5rem' }}>{u.email}</span>
                  <span className={`badge ${u.role === 'admin' ? 'badge-blue' : 'badge-gray'}`} style={{ marginLeft: '0.5rem' }}>{u.role === 'admin' ? 'Admin' : 'Benutzer'}</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  {u.last_login && <span className="sub" style={{ fontSize: '0.7rem' }}>Letzter Login: {new Date(u.last_login).toLocaleDateString('de-DE')}</span>}
                  {u.has_password && <span className="badge badge-gray" title="E-Mail/Passwort-Login">PW</span>}
                  {u.has_google && <span className="badge badge-blue" title="Google-Login">G</span>}
                  <span className={`badge ${u.is_active ? 'badge-green' : 'badge-red'}`}>{u.is_active ? 'Aktiv' : 'Inaktiv'}</span>
                  {isAdmin && <button className="btn btn-ghost btn-sm" onClick={() => setUserPassword(u.id)} title="Passwort setzen">🔑</button>}
                  {isAdmin && <button className="btn btn-ghost btn-sm" onClick={() => deactivateUser(u.id)} title="Deaktivieren">✕</button>}
                </div>
              </div>
            ))}
          </div>

          {/* Activity Log */}
          <div className="card">
            <h3>Aktivitätsprotokoll</h3>
            {activityLog.length === 0 && <p className="sub">Noch keine Aktivitäten.</p>}
            {activityLog.map(a => (
              <div key={a.id} style={{ display: 'flex', gap: '0.75rem', padding: '0.4rem 0', borderBottom: '1px solid #f3f4f6', fontSize: '0.8125rem' }}>
                <span className="sub" style={{ minWidth: '120px' }}>{a.created_at ? new Date(a.created_at).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''}</span>
                <span style={{ color: '#6b7280' }}>{a.user_email}</span>
                <span>{a.details}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── A/B Tests Tab ── */}
      {tab === 'abtests' && (
        <div>
          <h2>A/B Tests</h2>
          <p className="sub">Teste verschiedene Betreffzeilen und E-Mail-Inhalte gegeneinander</p>

          {abTests.length === 0 ? (
            <div className="card"><p className="sub" style={{ textAlign: 'center', padding: '2rem 0' }}>Noch keine A/B-Tests. Erstelle einen Test, um verschiedene E-Mail-Varianten zu vergleichen.</p></div>
          ) : (
            abTests.map(t => (
              <div key={t.id} className="card" style={{ marginBottom: '0.75rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                  <strong>{t.name}</strong>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <span className={`badge ${t.status === 'running' ? 'badge-yellow' : t.status === 'completed' ? 'badge-green' : 'badge-gray'}`}>
                      {t.status === 'running' ? 'Läuft' : t.status === 'completed' ? 'Abgeschlossen' : 'Entwurf'}
                    </span>
                    {t.winner && <span className="badge badge-green">Gewinner: Variante {t.winner}</span>}
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  <div style={{ padding: '0.75rem', background: '#f9fafb', borderRadius: '6px', border: t.winner === 'A' ? '2px solid #22c55e' : '1px solid #e5e7eb' }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Variante A</div>
                    <div className="sub" style={{ marginBottom: '0.5rem' }}>{t.variant_a.subject || '(kein Betreff)'}</div>
                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem' }}>
                      <span>Gesendet: {t.variant_a.sent}</span>
                      <span>Öffnungen: {t.variant_a.opens} ({t.variant_a.open_rate}%)</span>
                      <span>Klicks: {t.variant_a.clicks}</span>
                    </div>
                  </div>
                  <div style={{ padding: '0.75rem', background: '#f9fafb', borderRadius: '6px', border: t.winner === 'B' ? '2px solid #22c55e' : '1px solid #e5e7eb' }}>
                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Variante B</div>
                    <div className="sub" style={{ marginBottom: '0.5rem' }}>{t.variant_b.subject || '(kein Betreff)'}</div>
                    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem' }}>
                      <span>Gesendet: {t.variant_b.sent}</span>
                      <span>Öffnungen: {t.variant_b.opens} ({t.variant_b.open_rate}%)</span>
                      <span>Klicks: {t.variant_b.clicks}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
