import { useState, useEffect, useRef, useCallback } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis,
  Radar, AreaChart, Area
} from 'recharts'
import { api } from './api'
import SimulationView from './SimulationView'
import BacktestView from './BacktestView'
import EventView from './EventView'

// ─── CONSTANTS ────────────────────────────────────────────────────────────────
const OUTCOME_META = {
  win:     { label: '🏆 Royals Win',     color: '#4ade80', effect: '+15–18% alcohol, +6–8% food' },
  loss:    { label: '😤 Royals Loss',    color: '#f87171', effect: '−10–12% alcohol, −3–5% food' },
  close:   { label: '⚔️  Close Game',    color: '#fbbf24', effect: '+3–6% across all categories' },
  unknown: { label: '❓ Unknown',         color: '#94a3b8', effect: 'No outcome adjustment applied' },
}
const CAT_COLOR = {
  Beer: '#38bdf8', Alcohol: '#818cf8', Food: '#fb923c',
  Snack: '#a3e635', NA_Bev: '#22d3ee', Sweets: '#f472b6',
}
const STAND_ACCENT = ['#fbbf24','#94a3b8','#cd7f32','#38bdf8','#a78bfa','#4ade80']
const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
const ARCH_COLORS = { beer_crowd: '#fbbf24', family: '#a78bfa', mixed: '#38bdf8' }
const PERISH_COLORS = { shelf_stable: '#4ade80', medium_hold: '#fbbf24', short_life: '#f87171' }

// ─── SMALL COMPONENTS ─────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10 }}>
      <div style={{
        width:18, height:18, border:'2px solid rgba(56,189,248,0.2)',
        borderTop:'2px solid #38bdf8', borderRadius:'50%',
        animation:'spin 0.7s linear infinite',
      }}/>
      <span style={{ color:'var(--ice-dim)', fontSize:13 }}>Computing forecast…</span>
    </div>
  )
}

function ConfBadge({ level }) {
  const cfg = {
    high:   { bg:'rgba(74,222,128,0.1)',  border:'rgba(74,222,128,0.25)',  color:'#4ade80' },
    medium: { bg:'rgba(251,191,36,0.1)',  border:'rgba(251,191,36,0.25)',  color:'#fbbf24' },
    low:    { bg:'rgba(248,113,113,0.1)', border:'rgba(248,113,113,0.25)', color:'#f87171' },
  }[level] || {}
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', gap:4,
      padding:'2px 8px', borderRadius:20, fontSize:10, fontWeight:600,
      letterSpacing:'0.5px', textTransform:'uppercase',
      background:cfg.bg, border:`1px solid ${cfg.border}`, color:cfg.color,
    }}>
      <span style={{ width:5, height:5, borderRadius:'50%', background:cfg.color, boxShadow:`0 0 4px ${cfg.color}` }}/>
      {level}
    </span>
  )
}

function PerishDot({ tier }) {
  const color = PERISH_COLORS[tier] || '#94a3b8'
  const label = tier === 'shelf_stable' ? 'Shelf' : tier === 'medium_hold' ? 'Med' : 'Fresh'
  return (
    <span title={`${tier} — prep ${tier === 'shelf_stable' ? '95' : tier === 'medium_hold' ? '85' : '75'}%`} style={{
      display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: 9, color,
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      {label}
    </span>
  )
}

function IceBar({ value, max, color = 'var(--ice)', height = 5 }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div style={{ height, background:'rgba(255,255,255,0.06)', borderRadius:3, overflow:'hidden', position:'relative' }}>
      <div style={{
        position:'absolute', left:0, top:0, height:'100%',
        width:`${pct}%`,
        background:`linear-gradient(90deg, ${color}66, ${color})`,
        borderRadius:3,
        transition:'width 0.9s cubic-bezier(.4,0,.2,1)',
      }}/>
    </div>
  )
}

function StatCard({ icon, label, value, sub, color = 'var(--ice)', delay = 0 }) {
  return (
    <div className={`score-pop delay-${delay}`} style={{
      background:'var(--bg-card)', border:'1px solid var(--border)',
      borderRadius:12, padding:'18px 20px', flex:1, minWidth:130,
      position:'relative', overflow:'hidden',
    }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:2, background:`linear-gradient(90deg,transparent,${color},transparent)` }}/>
      <div style={{ fontSize:20, marginBottom:6 }}>{icon}</div>
      <div style={{ fontFamily:'var(--font-disp)', fontSize:28, fontWeight:700, color, lineHeight:1 }}>{value}</div>
      <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:4, letterSpacing:'0.3px' }}>{label}</div>
      {sub && <div style={{ fontSize:10, color:'rgba(255,255,255,0.22)', marginTop:3 }}>{sub}</div>}
    </div>
  )
}

function SectionHeader({ children }) {
  return (
    <div style={{
      fontFamily:'var(--font-disp)', fontSize:11, fontWeight:700,
      letterSpacing:'2.5px', textTransform:'uppercase',
      color:'rgba(255,255,255,0.35)', marginBottom:16,
    }}>{children}</div>
  )
}

function InputLabel({ children }) {
  return (
    <div style={{ fontSize:10, letterSpacing:'1.5px', textTransform:'uppercase', color:'var(--text-muted)', marginBottom:6, fontWeight:600 }}>
      {children}
    </div>
  )
}

const inputStyle = {
  background:'rgba(255,255,255,0.045)', border:'1px solid rgba(255,255,255,0.1)',
  borderRadius:8, color:'var(--text)', padding:'10px 13px', width:'100%',
  fontSize:13, transition:'border-color 0.2s, background 0.2s',
}

// ─── STAND CARD ───────────────────────────────────────────────────────────────

function StandCard({ stand, accent, index }) {
  const maxQty = Math.max(...stand.items.map(i => i.predicted), 1)
  return (
    <div className={`fade-up delay-${index + 1}`} style={{
      background:'var(--bg-card)', border:'1px solid var(--border)',
      borderRadius:14, padding:18, display:'flex', flexDirection:'column', gap:12,
      position:'relative', overflow:'hidden',
      transition:'border-color 0.2s, transform 0.2s',
    }}
    onMouseEnter={e => { e.currentTarget.style.borderColor = accent + '44'; e.currentTarget.style.transform = 'translateY(-2px)' }}
    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.transform = 'none' }}
    >
      <div style={{ position:'absolute', top:0, left:0, right:0, height:2, background:`linear-gradient(90deg,transparent,${accent},transparent)` }}/>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div>
          <div style={{ fontFamily:'var(--font-disp)', fontSize:15, fontWeight:800, letterSpacing:'0.5px', color:'var(--text)' }}>
            {stand.name.toUpperCase()}
          </div>
          <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:2 }}>
            {stand.volume_share_pct}% of venue volume
          </div>
        </div>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontFamily:'var(--font-disp)', fontSize:26, fontWeight:800, color:accent, lineHeight:1 }}>
            {stand.total_predicted.toLocaleString()}
          </div>
          <div style={{ fontSize:9, color:'var(--text-muted)', marginTop:2 }}>total items</div>
        </div>
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:9 }}>
        {stand.items.slice(0, 6).map(item => (
          <div key={item.item}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
              <span style={{ fontSize:12, color:'var(--text-dim)', display:'flex', alignItems:'center', gap:5 }}>
                {item.emoji} {item.item}
              </span>
              <span style={{ fontFamily:'var(--font-disp)', fontSize:14, fontWeight:700, color:'var(--text)', whiteSpace:'nowrap' }}>
                {item.predicted}&nbsp;
                <span style={{ fontSize:10, color:'var(--text-muted)', fontWeight:400 }}>({item.low}–{item.high})</span>
              </span>
            </div>
            <IceBar value={item.predicted} max={maxQty} color={accent} />
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── TIMELINE ─────────────────────────────────────────────────────────────────

function Timeline({ timeline }) {
  const maxItems = Math.max(...timeline.map(t => t.items))
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      {timeline.map((slot, i) => (
        <div key={slot.label} className={`slide-in delay-${i + 1}`} style={{
          display:'flex', alignItems:'center', gap:14,
          padding:'12px 16px',
          background: slot.is_rush ? 'rgba(251,191,36,0.05)' : 'var(--bg-card)',
          border: `1px solid ${slot.is_rush ? 'rgba(251,191,36,0.2)' : 'var(--border)'}`,
          borderRadius:10, position:'relative', overflow:'hidden',
        }}>
          {slot.is_rush && (
            <div style={{ position:'absolute', top:0, left:0, right:0, height:2, background:'linear-gradient(90deg,transparent,#fbbf24,transparent)' }}/>
          )}
          <div style={{ minWidth:52, textAlign:'right' }}>
            <div style={{ fontFamily:'var(--font-disp)', fontSize:18, fontWeight:700, color: slot.is_rush ? 'var(--gold)' : 'var(--ice)' }}>
              {slot.clock_time}
            </div>
          </div>
          <div style={{ minWidth:110 }}>
            <div style={{ fontSize:12, fontWeight:600, color:'var(--text-dim)' }}>{slot.label}</div>
            {slot.is_rush && (
              <div style={{ fontSize:9, color:'var(--gold)', letterSpacing:'1px', marginTop:1 }}>⚡ RUSH WINDOW</div>
            )}
          </div>
          <div style={{ flex:1 }}>
            <IceBar value={slot.items} max={maxItems} color={slot.is_rush ? '#fbbf24' : '#38bdf8'} height={7} />
          </div>
          <div style={{ minWidth:80, textAlign:'right' }}>
            <div style={{ fontFamily:'var(--font-disp)', fontSize:20, fontWeight:700, color:'var(--text)' }}>
              {slot.items.toLocaleString()}
            </div>
            <div style={{ fontSize:9, color:'var(--text-muted)' }}>{slot.share_pct}% of game</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── CUSTOM TOOLTIP ───────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background:'#0d1e33', border:'1px solid rgba(56,189,248,0.2)',
      borderRadius:8, padding:'10px 14px', fontSize:12, color:'var(--text)',
    }}>
      <div style={{ fontFamily:'var(--font-disp)', fontWeight:700, marginBottom:4 }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || 'var(--ice)', display:'flex', justifyContent:'space-between', gap:16 }}>
          <span>{p.name}</span>
          <span style={{ fontWeight:600 }}>{Number(p.value).toLocaleString()}</span>
        </div>
      ))}
    </div>
  )
}

// ─── TABS ─────────────────────────────────────────────────────────────────────

function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display:'flex', borderBottom:'1px solid var(--border)', marginBottom:24 }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          background:'none', border:'none', borderBottom:`2px solid ${active === t ? 'var(--ice)' : 'transparent'}`,
          color: active === t ? 'var(--ice)' : 'var(--text-muted)',
          fontFamily:'var(--font-disp)', fontSize:13, fontWeight:700,
          letterSpacing:'1px', textTransform:'uppercase', padding:'10px 18px',
          cursor:'pointer', transition:'color 0.2s, border-color 0.2s',
        }}>
          {t}
        </button>
      ))}
    </div>
  )
}

// ─── FORM ─────────────────────────────────────────────────────────────────────

function GameForm({ teams, onSubmit, loading }) {
  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({
    opponent: 'Kamloops Blazers',
    game_date: today,
    day_of_week: 'Friday',
    puck_drop: '19:05',
    attendance: 3200,
    predicted_outcome: 'unknown',
    home_support_pct: 70,
  })

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleDateChange = (val) => {
    const d = new Date(val + 'T12:00:00')
    set('game_date', val)
    set('day_of_week', DAYS[d.getDay() === 0 ? 6 : d.getDay() - 1] || 'Friday')
  }

  const handleSubmit = (e) => { e.preventDefault(); onSubmit(form) }

  const focusStyle = { borderColor:'rgba(56,189,248,0.55)', background:'rgba(56,189,248,0.05)' }
  const addFocus = e => Object.assign(e.target.style, focusStyle)
  const remFocus = e => Object.assign(e.target.style, { borderColor:'rgba(255,255,255,0.1)', background:'rgba(255,255,255,0.045)' })

  return (
    <form onSubmit={handleSubmit}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(195px,1fr))', gap:16 }}>
        <div>
          <InputLabel>Opponent</InputLabel>
          <select style={inputStyle} value={form.opponent} onChange={e => set('opponent', e.target.value)}
            onFocus={addFocus} onBlur={remFocus}>
            {(teams.length ? teams : ['Kamloops Blazers']).map(t => <option key={t} style={{background:'#0d1e2c'}}>{t}</option>)}
          </select>
        </div>
        <div>
          <InputLabel>Game Date</InputLabel>
          <input type="date" style={inputStyle} value={form.game_date}
            onChange={e => handleDateChange(e.target.value)} onFocus={addFocus} onBlur={remFocus}/>
        </div>
        <div>
          <InputLabel>Day of Week</InputLabel>
          <select style={inputStyle} value={form.day_of_week} onChange={e => set('day_of_week', e.target.value)}
            onFocus={addFocus} onBlur={remFocus}>
            {DAYS.map(d => <option key={d} style={{background:'#0d1e2c'}}>{d}</option>)}
          </select>
        </div>
        <div>
          <InputLabel>Puck Drop</InputLabel>
          <input type="time" style={inputStyle} value={form.puck_drop}
            onChange={e => set('puck_drop', e.target.value)} onFocus={addFocus} onBlur={remFocus}/>
        </div>
        <div>
          <InputLabel>Expected Attendance</InputLabel>
          <input type="number" style={inputStyle} min={500} max={7500} step={50}
            value={form.attendance} onChange={e => set('attendance', parseInt(e.target.value) || 3000)}
            onFocus={addFocus} onBlur={remFocus}/>
        </div>
        <div>
          <InputLabel>Predicted Outcome</InputLabel>
          <select style={inputStyle} value={form.predicted_outcome}
            onChange={e => set('predicted_outcome', e.target.value)} onFocus={addFocus} onBlur={remFocus}>
            {Object.entries(OUTCOME_META).map(([v, m]) => (
              <option key={v} value={v} style={{background:'#0d1e2c'}}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Home support slider */}
      <div style={{ marginTop:20 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
          <InputLabel>Home Fan Support</InputLabel>
          <div style={{ display:'flex', gap:16 }}>
            <span style={{ fontSize:11, color:'#f87171' }}>
              {form.opponent.split(' ').pop()}: {100 - form.home_support_pct}%
            </span>
            <span style={{ fontSize:11, color:'var(--ice)' }}>
              Royals: {form.home_support_pct}%
            </span>
          </div>
        </div>
        <div style={{ position:'relative', padding:'4px 0' }}>
          <div style={{ display:'flex', height:6, borderRadius:3, overflow:'hidden', marginBottom:8 }}>
            <div style={{ width:`${100-form.home_support_pct}%`, background:'rgba(248,113,113,0.4)', transition:'width 0.2s' }}/>
            <div style={{ width:`${form.home_support_pct}%`, background:'rgba(56,189,248,0.4)', transition:'width 0.2s' }}/>
          </div>
          <input type="range" min={10} max={95} step={5} value={form.home_support_pct}
            onChange={e => set('home_support_pct', parseInt(e.target.value))}
            style={{ width:'100%', accentColor:'var(--ice)', cursor:'pointer' }}/>
        </div>
        <div style={{ fontSize:11, color:'var(--text-muted)', marginTop:4 }}>
          Heavy home crowd (+) boosts overall demand · Away majority reduces alcohol sales
        </div>
      </div>

      {form.predicted_outcome !== 'unknown' && (
        <div style={{
          marginTop:16, padding:'8px 14px', borderRadius:8, fontSize:12,
          background:`${OUTCOME_META[form.predicted_outcome]?.color}12`,
          border:`1px solid ${OUTCOME_META[form.predicted_outcome]?.color}30`,
          color: OUTCOME_META[form.predicted_outcome]?.color,
          display:'flex', alignItems:'center', gap:8,
        }}>
          <span style={{ fontSize:16 }}>{OUTCOME_META[form.predicted_outcome]?.label.split(' ')[0]}</span>
          <span>{OUTCOME_META[form.predicted_outcome]?.effect}</span>
        </div>
      )}

      <div style={{ marginTop:24 }}>
        <button type="submit" disabled={loading} style={{
          background: loading ? 'rgba(56,189,248,0.2)' : 'linear-gradient(135deg,#0369a1,#0ea5e9)',
          border:'none', borderRadius:10, color:'white',
          fontFamily:'var(--font-disp)', fontSize:17, fontWeight:800,
          letterSpacing:'1px', textTransform:'uppercase', padding:'14px 36px',
          cursor: loading ? 'not-allowed' : 'pointer',
          transition:'all 0.2s', opacity: loading ? 0.7 : 1,
        }}
        onMouseEnter={e => { if (!loading) { e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='0 8px 28px rgba(14,165,233,0.35)' }}}
        onMouseLeave={e => { e.currentTarget.style.transform='none'; e.currentTarget.style.boxShadow='none' }}>
          {loading ? '⚙️  Computing…' : '🏒 Generate Game Brief'}
        </button>
      </div>
    </form>
  )
}

// ─── RESULTS ──────────────────────────────────────────────────────────────────

function Results({ data }) {
  const [tab, setTab] = useState('Overview')
  const { meta, summary, modifiers, items, stands, timeline, watchlist, engine, prep_targets } = data
  const archetype = meta?.archetype || engine?.archetype

  const radarData = ['Cans of Beer','Bottle Pop','Popcorn','Water','Cider & Coolers','Fries'].map(name => {
    const found = items.find(i => i.item === name)
    return { subject: name.split(' ')[0], value: found ? Math.round(found.predicted / 10) : 0 }
  })

  const topBarData = [...items].sort((a, b) => b.predicted - a.predicted).slice(0, 9).map(i => ({
    name: i.emoji + ' ' + i.item.replace(' & ',' &\n'),
    predicted: i.predicted, low: i.low, high: i.high,
    fill: CAT_COLOR[i.category] || '#38bdf8',
  }))

  const timelineChartData = timeline.map(t => ({
    name: t.label.replace('Intermission ', 'Int.'),
    items: t.items,
    fill: t.is_rush ? '#fbbf24' : '#38bdf8',
  }))

  const outcomeColor = OUTCOME_META[meta.predicted_outcome]?.color || '#94a3b8'

  return (
    <div>
      {/* Scoreboard */}
      <div className="fade-up" style={{
        background:'linear-gradient(135deg,#0a1829 0%,#0d2040 100%)',
        border:'1px solid rgba(56,189,248,0.12)', borderRadius:16,
        padding:'22px 26px', marginBottom:24,
      }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', flexWrap:'wrap', gap:16 }}>
          <div>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:4 }}>
              <div style={{ fontSize:10, color:'var(--ice-dim)', letterSpacing:'3px', textTransform:'uppercase' }}>
                Game Brief · {meta.game_date}
              </div>
              {archetype && (
                <span style={{
                  fontSize:10, fontWeight:700, letterSpacing:'1px', textTransform:'uppercase',
                  padding:'2px 10px', borderRadius:20,
                  background:`${ARCH_COLORS[archetype] || '#38bdf8'}20`,
                  border:`1px solid ${ARCH_COLORS[archetype] || '#38bdf8'}40`,
                  color: ARCH_COLORS[archetype] || '#38bdf8',
                }}>
                  {archetype.replace('_', ' ')}
                </span>
              )}
            </div>
            <div style={{ fontFamily:'var(--font-disp)', fontSize:26, fontWeight:800, color:'var(--text)', lineHeight:1.1 }}>
              Victoria Royals vs. {meta.opponent}
            </div>
            <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:6, display:'flex', gap:14, flexWrap:'wrap' }}>
              <span>📅 {meta.day_of_week}</span>
              <span>🕐 Puck Drop {meta.puck_drop}</span>
              <span>👥 {meta.attendance.toLocaleString()} expected</span>
              <span style={{ color: outcomeColor }}>
                {OUTCOME_META[meta.predicted_outcome]?.label}
              </span>
            </div>
          </div>
        </div>

        <div style={{ display:'flex', gap:12, marginTop:20, flexWrap:'wrap' }}>
          <StatCard icon="📦" label="Items Forecast" value={summary.total_predicted.toLocaleString()}
            sub={`${summary.total_low.toLocaleString()}–${summary.total_high.toLocaleString()} range`} color="var(--ice)" delay={1}/>
          <StatCard icon="👤" label="Per Fan" value={summary.items_per_fan}
            sub="avg items per guest" color="var(--purple)" delay={2}/>
          <StatCard icon="📅" label="Day Boost"
            value={`${modifiers.day_of_week.multiplier.toFixed(2)}×`}
            sub={`${meta.day_of_week} multiplier`} color="var(--gold)" delay={3}/>
          <StatCard icon="🎯" label="Model R²" value={summary.r_squared}
            sub={`${summary.games_in_model} games trained`} color="var(--green)" delay={4}/>
          <StatCard icon="👥" label="Home Support"
            value={`${meta.home_support_pct}%`}
            sub={`Modifier: ${modifiers.home_support.multiplier.toFixed(3)}×`}
            color="var(--ice)" delay={5}/>
        </div>
      </div>

      {/* Watchlist */}
      {watchlist.length > 0 && (
        <div className="fade-up delay-1" style={{
          background:'rgba(248,113,113,0.06)', border:'1px solid rgba(248,113,113,0.2)',
          borderRadius:12, padding:'14px 18px', marginBottom:20,
          display:'flex', gap:12, alignItems:'flex-start',
        }}>
          <div style={{ fontSize:18 }}>⚠️</div>
          <div>
            <div style={{ fontSize:11, color:'#f87171', letterSpacing:'2px', textTransform:'uppercase', marginBottom:4, fontWeight:600 }}>
              Watchlist — Monitor Live
            </div>
            <div style={{ fontSize:13, color:'var(--text-dim)' }}>
              {watchlist.map(i => `${i.emoji} ${i.item} (${i.variance_pct}% variance)`).join('  ·  ')}
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <Tabs tabs={['Overview','By Stand','Timeline','All Items']} active={tab} onChange={setTab} />

      {/* ── OVERVIEW ── */}
      {tab === 'Overview' && (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:20 }}>
          <div className="fade-in" style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, padding:20 }}>
            <SectionHeader>Top Items Forecast</SectionHeader>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={topBarData} layout="vertical" margin={{ left:8, right:24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" horizontal={false}/>
                <XAxis type="number" tick={{ fill:'rgba(255,255,255,0.3)', fontSize:10 }} axisLine={false} tickLine={false}/>
                <YAxis type="category" dataKey="name" tick={{ fill:'rgba(255,255,255,0.55)', fontSize:10 }} axisLine={false} tickLine={false} width={100}/>
                <Tooltip content={<ChartTooltip/>}/>
                <Bar dataKey="low"       fill="rgba(56,189,248,0.12)" radius={[0,3,3,0]} name="Low"/>
                <Bar dataKey="predicted" fill="rgba(56,189,248,0.75)" radius={[0,3,3,0]} name="Forecast"/>
                <Bar dataKey="high"      fill="rgba(56,189,248,0.18)" radius={[0,3,3,0]} name="High"/>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
            <div className="fade-in delay-1" style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, padding:20, flex:1 }}>
              <SectionHeader>Category Mix</SectionHeader>
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="rgba(255,255,255,0.07)"/>
                  <PolarAngleAxis dataKey="subject" tick={{ fill:'rgba(255,255,255,0.45)', fontSize:10 }}/>
                  <Radar name="Forecast" dataKey="value" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.12} strokeWidth={2}/>
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div className="fade-in delay-2" style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, padding:20 }}>
              <SectionHeader>Demand By Period</SectionHeader>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={timelineChartData} margin={{ left:0, right:0 }}>
                  <XAxis dataKey="name" tick={{ fill:'rgba(255,255,255,0.4)', fontSize:9 }} axisLine={false} tickLine={false}/>
                  <YAxis hide/>
                  <Tooltip content={<ChartTooltip/>}/>
                  <Bar dataKey="items" radius={[4,4,0,0]} name="Items">
                    {timelineChartData.map((entry, i) => (
                      <rect key={i} fill={entry.fill}/>
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* ── BY STAND ── */}
      {tab === 'By Stand' && (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(300px,1fr))', gap:16 }}>
          {stands.map((stand, i) => (
            <StandCard key={stand.name} stand={stand} accent={STAND_ACCENT[i] || '#38bdf8'} index={i}/>
          ))}
        </div>
      )}

      {/* ── TIMELINE ── */}
      {tab === 'Timeline' && (
        <div>
          <div className="fade-in" style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, padding:20, marginBottom:20 }}>
            <SectionHeader>Sales Volume by Game Period</SectionHeader>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={timelineChartData} margin={{ left:0, right:16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false}/>
                <XAxis dataKey="name" tick={{ fill:'rgba(255,255,255,0.45)', fontSize:11 }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fill:'rgba(255,255,255,0.3)', fontSize:10 }} axisLine={false} tickLine={false}/>
                <Tooltip content={<ChartTooltip/>}/>
                <Bar dataKey="items" radius={[5,5,0,0]} name="Items"
                  fill="#38bdf8"
                  label={{ position:'top', fill:'rgba(255,255,255,0.35)', fontSize:10 }}/>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Timeline timeline={timeline}/>
        </div>
      )}

      {/* ── ALL ITEMS ── */}
      {tab === 'All Items' && (
        <div className="fade-in" style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, overflow:'hidden' }}>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead>
              <tr style={{ borderBottom:'1px solid var(--border)' }}>
                {['Item','Category','Tier','Low','Forecast','Prep Qty','High','Variance','Confidence'].map(h => (
                  <th key={h} style={{ padding:'11px 16px', textAlign:'left', fontSize:10, color:'var(--text-muted)', letterSpacing:'1.5px', textTransform:'uppercase', fontWeight:600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => (
                <tr key={item.item} style={{
                  borderBottom:'1px solid rgba(255,255,255,0.03)',
                  background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                  transition:'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background='rgba(56,189,248,0.05)'}
                onMouseLeave={e => e.currentTarget.style.background= i%2===0 ? 'transparent' : 'rgba(255,255,255,0.012)'}>
                  <td style={{ padding:'10px 16px', fontSize:13 }}>{item.emoji} {item.item}</td>
                  <td style={{ padding:'10px 16px' }}>
                    <span style={{ fontSize:11, padding:'2px 8px', borderRadius:4, background:`${CAT_COLOR[item.category] || '#38bdf8'}18`, color:CAT_COLOR[item.category] || '#38bdf8' }}>
                      {item.category.replace('_',' ')}
                    </span>
                  </td>
                  <td style={{ padding:'10px 16px' }}>
                    <PerishDot tier={item.perishability || 'medium_hold'} />
                  </td>
                  <td style={{ padding:'10px 16px', fontFamily:'var(--font-disp)', fontSize:13, color:'var(--text-muted)' }}>{item.low.toLocaleString()}</td>
                  <td style={{ padding:'10px 16px', fontFamily:'var(--font-disp)', fontSize:17, fontWeight:700, color:'var(--ice)' }}>{item.predicted.toLocaleString()}</td>
                  <td style={{ padding:'10px 16px', fontFamily:'var(--font-disp)', fontSize:14, fontWeight:600, color:'var(--green)' }}>{item.prep_qty?.toLocaleString() || '—'}</td>
                  <td style={{ padding:'10px 16px', fontFamily:'var(--font-disp)', fontSize:13, color:'var(--text-muted)' }}>{item.high.toLocaleString()}</td>
                  <td style={{ padding:'10px 16px', fontSize:12, color:'var(--text-dim)' }}>±{item.variance_pct}%</td>
                  <td style={{ padding:'10px 16px' }}><ConfBadge level={item.confidence}/></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop:18, display:'flex', justifyContent:'space-between', fontSize:10, color:'var(--text-muted)', flexWrap:'wrap', gap:8 }}>
        <span>
          🟢 High = &lt;20% variance &nbsp;·&nbsp;
          🟡 Medium = 20–45% &nbsp;·&nbsp;
          🔴 Low = &gt;45% — monitor live
        </span>
        <span>Trained on {summary.games_in_model} SOFMC games · Attendance R²={summary.r_squared}</span>
      </div>
    </div>
  )
}

// ─── HISTORY PANEL ────────────────────────────────────────────────────────────

function HistoryPanel({ data }) {
  if (!data) return <div className="skeleton" style={{ height:120, borderRadius:14 }}/>
  const dowChartData = Object.entries(data.dow_multipliers).map(([day, mult]) => ({
    name: day.slice(0,3), mult: parseFloat((mult * 100).toFixed(1))
  }))
  return (
    <div className="fade-in" style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(170px,1fr))', gap:12 }}>
        {[
          { icon:'🗂️',  label:'Transactions',    value: data.total_transactions.toLocaleString() },
          { icon:'🏒',  label:'Games Analysed',  value: data.total_games },
          { icon:'📈',  label:'Attendance Corr', value: `R²=${data.r_squared}` },
          { icon:'📅',  label:'Seasons',         value: data.seasons.join(' + ') },
        ].map(s => (
          <div key={s.label} style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:10, padding:'14px 16px' }}>
            <div style={{ fontSize:18, marginBottom:4 }}>{s.icon}</div>
            <div style={{ fontFamily:'var(--font-disp)', fontSize:22, fontWeight:700, color:'var(--ice)' }}>{s.value}</div>
            <div style={{ fontSize:10, color:'var(--text-muted)' }}>{s.label}</div>
          </div>
        ))}
      </div>

      <div style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:14, padding:20 }}>
        <SectionHeader>Day-of-Week Multipliers</SectionHeader>
        <ResponsiveContainer width="100%" height={120}>
          <BarChart data={dowChartData} margin={{ left:0, right:0 }}>
            <XAxis dataKey="name" tick={{ fill:'rgba(255,255,255,0.45)', fontSize:11 }} axisLine={false} tickLine={false}/>
            <YAxis hide domain={[70, 130]}/>
            <Tooltip content={<ChartTooltip/>} formatter={v => [`${v}%`,'Index']}/>
            <Bar dataKey="mult" fill="#38bdf8" fillOpacity={0.7} radius={[4,4,0,0]} name="Index"
              label={{ position:'top', fill:'rgba(255,255,255,0.35)', fontSize:9, formatter:v => v+'%' }}/>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
        {[data.best_game, data.worst_game].map((g, i) => (
          <div key={i} style={{ background:'var(--bg-card)', border:`1px solid ${i===0 ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)'}`, borderRadius:10, padding:16 }}>
            <div style={{ fontSize:10, color: i===0 ? 'var(--green)' : 'var(--red)', letterSpacing:'1.5px', textTransform:'uppercase', marginBottom:6, fontWeight:600 }}>
              {i===0 ? '🔥 Biggest Game' : '📉 Quietest Game'}
            </div>
            <div style={{ fontFamily:'var(--font-disp)', fontSize:18, fontWeight:700, color:'var(--text)' }}>{g.opponent || g.date}</div>
            <div style={{ fontSize:12, color:'var(--text-muted)', marginTop:4 }}>
              {g.attendance.toLocaleString()} fans · {g.items_sold.toLocaleString()} items sold
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── APP ROOT ─────────────────────────────────────────────────────────────────

export default function App() {
  const [teams,   setTeams]   = useState([])
  const [history, setHistory] = useState(null)
  const [result,  setResult]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const [view,    setView]    = useState('forecast')
  const resultRef = useRef(null)

  useEffect(() => {
    api.teams().then(d => setTeams(d.teams)).catch(() => {})
    api.history().then(setHistory).catch(() => {})
  }, [])

  const handleForecast = useCallback(async (form) => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.forecast(form)
      setResult(data)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior:'smooth', block:'start' }), 120)
    } catch (e) {
      setError(e.message || 'Could not reach the backend. Is the Python server running?')
    } finally {
      setLoading(false)
    }
  }, [])

  const NAV_ITEMS = [
    ['forecast',   '🏒 Forecast'],
    ['simulation', '🎮 Simulation'],
    ['validation', '📊 Validation'],
    ['events',     '🎫 Events'],
    ['history',    '📋 History'],
  ]

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg)', position:'relative', overflow:'hidden' }}>

      {/* Rink background */}
      <div style={{ position:'fixed', inset:0, pointerEvents:'none', zIndex:0, opacity:1, animation:'rinkPulse 7s ease-in-out infinite' }}>
        <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="50%" cy="50%" rx="46%" ry="42%" fill="none" stroke="rgba(56,189,248,0.55)" strokeWidth="1"/>
          <line x1="50%" y1="5%" x2="50%" y2="95%" stroke="rgba(56,189,248,0.35)" strokeWidth="0.7"/>
          <circle cx="50%" cy="50%" r="5.5%" fill="none" stroke="rgba(56,189,248,0.55)" strokeWidth="0.7"/>
          <circle cx="50%" cy="50%" r="0.8%" fill="rgba(56,189,248,0.3)"/>
          {[[26,34],[26,66],[74,34],[74,66]].map(([xn,yn],i) => (
            <g key={i}>
              <circle cx={`${xn}%`} cy={`${yn}%`} r="2.2%" fill="none" stroke="rgba(248,113,113,0.5)" strokeWidth="0.7"/>
              <line x1={`${xn-0.5}%`} x2={`${xn+0.5}%`} y1={`${yn}%`} y2={`${yn}%`} stroke="rgba(248,113,113,0.5)" strokeWidth="0.7"/>
              <line x1={`${xn}%`} x2={`${xn}%`} y1={`${yn-0.5}%`} y2={`${yn+0.5}%`} stroke="rgba(248,113,113,0.5)" strokeWidth="0.7"/>
            </g>
          ))}
          <line x1="20%" y1="5%" x2="20%" y2="95%" stroke="rgba(56,189,248,0.15)" strokeWidth="0.5"/>
          <line x1="80%" y1="5%" x2="80%" y2="95%" stroke="rgba(56,189,248,0.15)" strokeWidth="0.5"/>
        </svg>
      </div>

      <div style={{ position:'relative', zIndex:1, maxWidth:1120, margin:'0 auto', padding:'0 20px 80px' }}>

        {/* ── HEADER ── */}
        <header style={{ padding:'32px 0 24px', borderBottom:'1px solid var(--border)', marginBottom:32 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:16 }}>
            <div style={{ display:'flex', alignItems:'center', gap:16 }}>
              <div style={{
                width:52, height:52,
                background:'linear-gradient(135deg,#0c4a6e,#0ea5e9)',
                borderRadius:14, display:'flex', alignItems:'center', justifyContent:'center',
                fontSize:26, boxShadow:'0 6px 24px rgba(14,165,233,0.28)',
              }}>🏒</div>
              <div>
                <div style={{ fontFamily:'var(--font-disp)', fontSize:34, fontWeight:900, letterSpacing:'2.5px', color:'#f0f9ff', textTransform:'uppercase', lineHeight:1 }}>
                  PUCK PREP
                </div>
                <div style={{ fontSize:10, color:'rgba(56,189,248,0.65)', letterSpacing:'3px', textTransform:'uppercase', marginTop:3 }}>
                  Save-on-Foods Memorial Centre · F&B Intelligence
                </div>
              </div>
            </div>

            {/* Nav */}
            <nav style={{ display:'flex', gap:4, flexWrap:'wrap' }}>
              {NAV_ITEMS.map(([v, label]) => (
                <button key={v} onClick={() => setView(v)} style={{
                  background: view===v ? 'rgba(56,189,248,0.12)' : 'none',
                  border:`1px solid ${view===v ? 'rgba(56,189,248,0.3)' : 'var(--border)'}`,
                  borderRadius:8, color: view===v ? 'var(--ice)' : 'var(--text-muted)',
                  fontFamily:'var(--font-disp)', fontSize:12, fontWeight:700,
                  letterSpacing:'0.5px', padding:'8px 14px', cursor:'pointer',
                  transition:'all 0.2s', whiteSpace:'nowrap',
                }}>{label}</button>
              ))}
            </nav>
          </div>

          <div style={{ marginTop:12, fontSize:11, color:'var(--text-muted)', letterSpacing:'0.3px' }}>
            Powered by <strong style={{ color:'var(--ice-dim)' }}>239,717</strong> real transactions ·{' '}
            <strong style={{ color:'var(--ice-dim)' }}>69</strong> WHL home games ·{' '}
            Attendance → Sales R² = <strong style={{ color:'var(--green)' }}>0.948</strong>
          </div>
        </header>

        {/* ── FORECAST VIEW ── */}
        {view === 'forecast' && (
          <>
            <div style={{ background:'var(--bg-card)', border:'1px solid var(--border)', borderRadius:16, padding:28, marginBottom:32 }}>
              <SectionHeader>Game Setup</SectionHeader>
              <GameForm teams={teams} onSubmit={handleForecast} loading={loading}/>
            </div>

            {loading && (
              <div style={{ display:'flex', justifyContent:'center', padding:'32px 0' }}>
                <Spinner/>
              </div>
            )}

            {error && (
              <div style={{
                background:'rgba(248,113,113,0.07)', border:'1px solid rgba(248,113,113,0.25)',
                borderRadius:12, padding:'16px 20px', color:'#f87171', fontSize:13,
                display:'flex', alignItems:'center', gap:10, marginBottom:20,
              }}>
                <span style={{ fontSize:20 }}>⚠️</span>
                <div>
                  <strong>Backend Error</strong><br/>
                  {error}<br/>
                  <span style={{ fontSize:11, opacity:0.7, marginTop:4, display:'block' }}>
                    Make sure the Python backend is running: <code>cd backend && uvicorn main:app --reload</code>
                  </span>
                </div>
              </div>
            )}

            {result && !loading && (
              <div ref={resultRef}>
                <Results data={result}/>
              </div>
            )}
          </>
        )}

        {/* ── SIMULATION VIEW ── */}
        {view === 'simulation' && <SimulationView />}

        {/* ── VALIDATION VIEW ── */}
        {view === 'validation' && <BacktestView />}

        {/* ── EVENTS VIEW ── */}
        {view === 'events' && <EventView />}

        {/* ── HISTORY VIEW ── */}
        {view === 'history' && (
          <div>
            <div style={{ marginBottom:20 }}>
              <div style={{ fontFamily:'var(--font-disp)', fontSize:20, fontWeight:800, letterSpacing:'1px', marginBottom:4 }}>
                Historical Data Summary
              </div>
              <div style={{ fontSize:12, color:'var(--text-muted)' }}>
                Two full WHL seasons of F&B data from SOFMC — the foundation of every forecast
              </div>
            </div>
            <HistoryPanel data={history}/>
          </div>
        )}

      </div>
    </div>
  )
}
