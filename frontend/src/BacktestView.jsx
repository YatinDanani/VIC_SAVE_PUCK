import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { api } from './api'

const ARCH_COLORS = { beer_crowd: '#fbbf24', family: '#A4ADB4', mixed: '#1a6bc4' }

export default function BacktestView() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.backtest()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 40 }}>
      <div style={{
        width: 18, height: 18, border: '2px solid rgba(26,107,196,0.2)',
        borderTop: '2px solid #1a6bc4', borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}/>
      <span style={{ color: 'var(--ice-dim)', fontSize: 13 }}>Loading backtest results...</span>
    </div>
  )

  if (error) return (
    <div style={{ color: '#ef4444', padding: 20 }}>Error loading backtest: {error}</div>
  )

  if (!data || !data.results || data.results.length === 0) return (
    <div style={{ color: 'var(--text-muted)', padding: 20 }}>No backtest results available.</div>
  )

  const { summary, results, archetype_breakdown } = data

  // Error distribution chart
  const bins = {}
  results.forEach(r => {
    const err = Math.round(r.volume_error * 100)
    const bucket = Math.round(err / 5) * 5
    const label = `${bucket}%`
    bins[label] = (bins[label] || 0) + 1
  })
  const errorDistData = Object.entries(bins)
    .map(([label, count]) => ({ label, count, pct: parseInt(label) }))
    .sort((a, b) => a.pct - b.pct)

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-disp)', fontSize: 20, fontWeight: 800, letterSpacing: '1px', marginBottom: 4 }}>
          Model Validation
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Leave-one-out cross-validation — each game predicted using only data from all other games
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { icon: '🎯', label: 'Games Validated', value: summary.total_games, color: 'var(--ice)' },
          { icon: '📊', label: 'Median Error', value: `${(summary.median_error * 100).toFixed(1)}%`, color: summary.median_error > 0 ? '#fbbf24' : 'var(--green)' },
          { icon: '✅', label: 'Within ±15%', value: `${summary.within_15pct}/${summary.total_games} (${Math.round(summary.within_15pct_rate * 100)}%)`, color: 'var(--green)' },
          { icon: '📉', label: 'Mean Abs Error', value: `${(summary.mean_abs_error * 100).toFixed(1)}%`, color: 'var(--purple)' },
          { icon: '🗑️', label: 'Total Waste', value: summary.total_waste_units?.toLocaleString() || '—', color: '#ef4444' },
          { icon: '📦', label: 'Total Stockout', value: summary.total_stockout_units?.toLocaleString() || '—', color: '#fbbf24' },
        ].map(s => (
          <div key={s.label} style={{
            background: 'var(--bg-card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '16px 18px',
          }}>
            <div style={{ fontSize: 20, marginBottom: 6 }}>{s.icon}</div>
            <div style={{ fontFamily: 'var(--font-disp)', fontSize: 24, fontWeight: 700, color: s.color, lineHeight: 1 }}>
              {s.value}
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Error distribution + archetype breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        {/* Error distribution */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 20 }}>
          <div style={{
            fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
            letterSpacing: '2.5px', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.55)', marginBottom: 14,
          }}>
            Error Distribution
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={errorDistData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: 'rgba(255,255,255,0.55)', fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: '#0d1525', border: '1px solid rgba(26,107,196,0.2)', borderRadius: 8, fontSize: 12, color: '#e2e8f0' }}
              />
              <Bar dataKey="count" name="Games" radius={[4, 4, 0, 0]}>
                {errorDistData.map((entry, i) => (
                  <rect key={i} fill={Math.abs(entry.pct) <= 15 ? '#4ade80' : Math.abs(entry.pct) <= 25 ? '#fbbf24' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Archetype breakdown */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: 20 }}>
          <div style={{
            fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
            letterSpacing: '2.5px', textTransform: 'uppercase',
            color: 'rgba(255,255,255,0.55)', marginBottom: 14,
          }}>
            By Archetype
          </div>
          {archetype_breakdown && Object.entries(archetype_breakdown).map(([arch, stats]) => (
            <div key={arch} style={{
              background: 'rgba(255,255,255,0.03)', borderRadius: 8,
              padding: '12px 14px', marginBottom: 8,
              borderLeft: `3px solid ${ARCH_COLORS[arch] || '#1a6bc4'}`,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <span style={{ fontFamily: 'var(--font-disp)', fontSize: 15, fontWeight: 700, color: ARCH_COLORS[arch] || '#1a6bc4' }}>
                    {arch.replace('_', ' ')}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>
                    {stats.count} games
                  </span>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-disp)', fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>
                    {(stats.median_error * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 9, color: 'var(--text-muted)' }}>median error</div>
                </div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                {stats.within_15pct}/{stats.count} within ±15% · Mean abs: {(stats.mean_abs_error * 100).toFixed(1)}%
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Per-game results table */}
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden' }}>
        <div style={{
          fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
          letterSpacing: '2.5px', textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.55)', padding: '16px 16px 0',
        }}>
          Per-Game Results
        </div>
        <div style={{ maxHeight: 400, overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Date', 'Opponent', 'Archetype', 'Attend.', 'Actual', 'Forecast', 'Error', 'Prep Cov.'].map(h => (
                  <th key={h} style={{
                    padding: '10px 12px', textAlign: 'left', fontSize: 9,
                    color: 'var(--text-muted)', letterSpacing: '1.5px',
                    textTransform: 'uppercase', fontWeight: 600, position: 'sticky', top: 0,
                    background: 'var(--bg-card)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.map((r, i) => {
                const absErr = Math.abs(r.volume_error)
                const errColor = absErr <= 0.15 ? '#4ade80' : absErr <= 0.25 ? '#fbbf24' : '#ef4444'
                return (
                  <tr key={i} style={{
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                    background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)',
                  }}>
                    <td style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-dim)' }}>{r.game_date}</td>
                    <td style={{ padding: '8px 12px', fontSize: 12 }}>{r.opponent}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={{
                        fontSize: 10, padding: '2px 8px', borderRadius: 4,
                        background: `${ARCH_COLORS[r.archetype] || '#1a6bc4'}18`,
                        color: ARCH_COLORS[r.archetype] || '#1a6bc4',
                      }}>
                        {r.archetype}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-disp)', fontSize: 12 }}>
                      {r.attendance?.toLocaleString()}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-disp)', fontSize: 12 }}>
                      {r.actual_total?.toLocaleString()}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-disp)', fontSize: 12 }}>
                      {r.forecast_total?.toLocaleString()}
                    </td>
                    <td style={{ padding: '8px 12px', fontFamily: 'var(--font-disp)', fontSize: 13, fontWeight: 700, color: errColor }}>
                      {r.volume_error_pct}
                    </td>
                    <td style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-dim)' }}>
                      {(r.prep_coverage * 100).toFixed(0)}%
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
