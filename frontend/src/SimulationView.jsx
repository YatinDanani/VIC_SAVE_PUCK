import { useState, useEffect, useRef, useCallback } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from './api'

const STATUS_COLORS = { green: '#4ade80', yellow: '#fbbf24', red: '#ef4444' }
const STATUS_EMOJI = { green: '🟢', yellow: '🟡', red: '🔴' }

function TrafficLightGrid({ stands }) {
  if (!stands || stands.length === 0) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 10 }}>
      {stands.map(s => (
        <div key={s.stand} style={{
          background: `${STATUS_COLORS[s.status]}10`,
          border: `1px solid ${STATUS_COLORS[s.status]}40`,
          borderRadius: 10, padding: '12px 14px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>{s.stand}</span>
            <span>{STATUS_EMOJI[s.status]}</span>
          </div>
          <div style={{ fontFamily: 'var(--font-disp)', fontSize: 22, fontWeight: 800, color: STATUS_COLORS[s.status] }}>
            {(s.drift_pct * 100).toFixed(0)}%
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
            F:{s.forecast_qty} A:{s.actual_qty} · {s.trend}
          </div>
        </div>
      ))}
    </div>
  )
}

function AlertFeed({ alerts }) {
  const feedRef = useRef(null)
  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [alerts])

  if (!alerts || alerts.length === 0) return (
    <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 16 }}>
      No AI alerts yet — waiting for significant drift...
    </div>
  )

  return (
    <div ref={feedRef} style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
      {alerts.map((a, i) => (
        <div key={i} style={{
          background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
          borderRadius: 8, padding: '10px 14px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '1px', textTransform: 'uppercase',
              color: a.cause === 'noise' ? 'var(--text-muted)' : '#fbbf24',
            }}>
              {a.cause.replace('_', ' ')}
            </span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              {Math.round(a.confidence * 100)}% conf
            </span>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{a.alert_text}</div>
        </div>
      ))}
    </div>
  )
}

export default function SimulationView() {
  const [scenarios, setScenarios] = useState([])
  const [selectedScenario, setSelectedScenario] = useState('normal')
  const [speed, setSpeed] = useState(120)
  const [running, setRunning] = useState(false)
  const [gameInfo, setGameInfo] = useState(null)
  const [trafficLight, setTrafficLight] = useState(null)
  const [driftHistory, setDriftHistory] = useState([])
  const [alerts, setAlerts] = useState([])
  const [postGame, setPostGame] = useState(null)
  const [complete, setComplete] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    api.scenarios().then(d => setScenarios(d.scenarios || [])).catch(() => {})
  }, [])

  const handleStart = useCallback(() => {
    setRunning(true)
    setComplete(false)
    setGameInfo(null)
    setTrafficLight(null)
    setDriftHistory([])
    setAlerts([])
    setPostGame(null)

    const conn = api.connectSimulation(
      { scenario: selectedScenario, speed, skip_ai: false },
      (msg) => {
        if (msg.type === 'game_info') {
          setGameInfo(msg.game)
        } else if (msg.type === 'window_update') {
          setTrafficLight(msg.traffic_light)
          setDriftHistory(prev => [...prev, {
            window: msg.time_window,
            drift: Math.round(msg.cumulative_drift * 100),
          }])
          if (msg.ai_alert) {
            setAlerts(prev => [...prev, msg.ai_alert])
          }
        } else if (msg.type === 'complete') {
          setRunning(false)
          setComplete(true)
          setPostGame(msg)
        } else if (msg.type === 'error') {
          setRunning(false)
        } else if (msg.type === 'closed') {
          setRunning(false)
        }
      }
    )
    wsRef.current = conn
  }, [selectedScenario, speed])

  const handleStop = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.stop()
      wsRef.current.close()
    }
    setRunning(false)
  }, [])

  const selectedMeta = scenarios.find(s => s.key === selectedScenario)

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-disp)', fontSize: 20, fontWeight: 800, letterSpacing: '1px', marginBottom: 4 }}>
          Game Simulation
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Replay real games with configurable scenarios — watch drift detection and AI reasoning in real-time
        </div>
      </div>

      {/* Controls */}
      <div style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        borderRadius: 14, padding: 20, marginBottom: 20,
        display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap',
      }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 10, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>
            Scenario
          </div>
          <select
            value={selectedScenario}
            onChange={e => setSelectedScenario(e.target.value)}
            disabled={running}
            style={{
              background: 'rgba(255,255,255,0.045)', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8, color: 'var(--text)', padding: '10px 13px', width: '100%', fontSize: 13,
            }}
          >
            {scenarios.map(s => (
              <option key={s.key} value={s.key} style={{ background: '#0d1525' }}>{s.name}</option>
            ))}
          </select>
          {selectedMeta && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              {selectedMeta.description}
            </div>
          )}
        </div>

        <div style={{ minWidth: 140 }}>
          <div style={{ fontSize: 10, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>
            Speed ({speed}x)
          </div>
          <input
            type="range" min={10} max={500} step={10} value={speed}
            onChange={e => {
              const v = parseInt(e.target.value)
              setSpeed(v)
              if (wsRef.current && running) wsRef.current.setSpeed(v)
            }}
            style={{ width: '100%', accentColor: 'var(--ice)' }}
          />
        </div>

        <div>
          {!running ? (
            <button onClick={handleStart} style={{
              background: 'linear-gradient(135deg,#013974,#1a6bc4)',
              border: 'none', borderRadius: 10, color: 'white',
              fontFamily: 'var(--font-disp)', fontSize: 15, fontWeight: 800,
              letterSpacing: '1px', textTransform: 'uppercase', padding: '12px 28px',
              cursor: 'pointer',
            }}>
              Start
            </button>
          ) : (
            <button onClick={handleStop} style={{
              background: 'rgba(210,4,14,0.2)',
              border: '1px solid rgba(210,4,14,0.4)',
              borderRadius: 10, color: '#ef4444',
              fontFamily: 'var(--font-disp)', fontSize: 15, fontWeight: 800,
              letterSpacing: '1px', textTransform: 'uppercase', padding: '12px 28px',
              cursor: 'pointer',
            }}>
              Stop
            </button>
          )}
        </div>
      </div>

      {/* Game info */}
      {gameInfo && (
        <div style={{
          background: 'linear-gradient(135deg,#0a1422,#0c1830)',
          border: '1px solid rgba(26,107,196,0.12)', borderRadius: 14,
          padding: '16px 20px', marginBottom: 20,
          display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'center',
        }}>
          <div>
            <div style={{ fontFamily: 'var(--font-disp)', fontSize: 20, fontWeight: 800, color: 'var(--text)' }}>
              vs {gameInfo.opponent}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
              {gameInfo.date} · {gameInfo.attendance?.toLocaleString()} fans · {gameInfo.archetype}
            </div>
          </div>
          {running && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '6px 14px', borderRadius: 20,
              background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.3)',
            }}>
              <div style={{
                width: 8, height: 8, borderRadius: '50%', background: '#4ade80',
                animation: 'rinkPulse 1s infinite',
              }}/>
              <span style={{ fontSize: 11, color: '#4ade80', fontWeight: 600 }}>LIVE</span>
            </div>
          )}
          {complete && (
            <div style={{
              padding: '6px 14px', borderRadius: 20, fontSize: 11, fontWeight: 600,
              background: 'rgba(26,107,196,0.1)', border: '1px solid rgba(26,107,196,0.3)',
              color: 'var(--ice)',
            }}>
              COMPLETE
            </div>
          )}
        </div>
      )}

      {/* Main grid */}
      {(running || complete) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          {/* Traffic lights */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 18 }}>
            <div style={{
              fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
              letterSpacing: '2.5px', textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.55)', marginBottom: 14,
            }}>
              Stand Status
            </div>
            <TrafficLightGrid stands={trafficLight?.stands || []} />
          </div>

          {/* Drift chart */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 18 }}>
            <div style={{
              fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
              letterSpacing: '2.5px', textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.55)', marginBottom: 14,
            }}>
              Cumulative Drift
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={driftHistory}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                <XAxis dataKey="window" tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} axisLine={false} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} axisLine={false} unit="%" />
                <Tooltip
                  contentStyle={{ background: '#0d1525', border: '1px solid rgba(26,107,196,0.2)', borderRadius: 8, fontSize: 12 }}
                  labelFormatter={v => `T+${v}min`}
                  formatter={v => [`${v}%`, 'Drift']}
                />
                <Line type="monotone" dataKey="drift" stroke="#1a6bc4" strokeWidth={2} dot={false} />
                {/* Reference lines at ±15% */}
                <Line type="monotone" dataKey={() => 15} stroke="rgba(74,222,128,0.3)" strokeDasharray="5 5" dot={false} />
                <Line type="monotone" dataKey={() => -15} stroke="rgba(74,222,128,0.3)" strokeDasharray="5 5" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* AI Alerts */}
      {(running || complete) && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 18, marginBottom: 20 }}>
          <div style={{
            fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
            letterSpacing: '2.5px', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.55)', marginBottom: 14,
          }}>
            AI Alerts
          </div>
          <AlertFeed alerts={alerts} />
        </div>
      )}

      {/* Post-game report */}
      {complete && postGame && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 20 }}>
          <div style={{
            fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
            letterSpacing: '2.5px', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.55)', marginBottom: 14,
          }}>
            Post-Game Report
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 }}>
            {[
              { label: 'Total Actual', value: postGame.summary?.total_actual?.toLocaleString() || '—' },
              { label: 'Total Forecast', value: postGame.summary?.total_forecast?.toLocaleString() || '—' },
              { label: 'Cumulative Drift', value: postGame.summary?.cumulative_drift || '—' },
              { label: 'AI Alerts', value: postGame.total_ai_alerts || 0 },
            ].map(s => (
              <div key={s.label} style={{
                background: 'rgba(255,255,255,0.03)', borderRadius: 8, padding: '12px 14px',
              }}>
                <div style={{ fontFamily: 'var(--font-disp)', fontSize: 22, fontWeight: 700, color: 'var(--ice)' }}>
                  {s.value}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{s.label}</div>
              </div>
            ))}
          </div>
          {postGame.post_game_report && (
            <div style={{
              background: 'rgba(255,255,255,0.02)', borderRadius: 10, padding: 16,
              fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.7, whiteSpace: 'pre-wrap',
            }}>
              {postGame.post_game_report}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
