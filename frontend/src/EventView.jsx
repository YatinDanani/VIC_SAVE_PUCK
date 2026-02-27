import { useState, useEffect } from 'react'
import { api } from './api'

const TYPE_COLORS = {
  promo: '#fbbf24',
  early_bird: '#4ade80',
  scheduling: '#38bdf8',
  event: '#a78bfa',
}
const TYPE_ICONS = {
  promo: '🎫',
  early_bird: '🌅',
  scheduling: '📅',
  event: '🎪',
}

export default function EventView() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.eventRecommendations()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: 40 }}>
      <div style={{
        width: 18, height: 18, border: '2px solid rgba(56,189,248,0.2)',
        borderTop: '2px solid #38bdf8', borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }}/>
      <span style={{ color: 'var(--ice-dim)', fontSize: 13 }}>Loading recommendations...</span>
    </div>
  )

  if (error) return (
    <div style={{ color: '#f87171', padding: 20 }}>Error: {error}</div>
  )

  const recommendations = data?.recommendations || []
  const aiStrategy = data?.ai_strategy
  const aiAvailable = data?.ai_available

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontFamily: 'var(--font-disp)', fontSize: 20, fontWeight: 800, letterSpacing: '1px', marginBottom: 4 }}>
          Event & Promo Optimizer
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          Data-driven recommendations for promotions, events, and scheduling optimization
        </div>
      </div>

      {!aiAvailable && (
        <div style={{
          background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.2)',
          borderRadius: 10, padding: '12px 16px', marginBottom: 16,
          display: 'flex', alignItems: 'center', gap: 10,
          fontSize: 12, color: '#fbbf24',
        }}>
          <span style={{ fontSize: 16 }}>⚠️</span>
          AI strategy synthesis unavailable — showing rule-based recommendations only.
          Set ANTHROPIC_API_KEY to enable AI insights.
        </div>
      )}

      {/* Recommendation cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: 14, marginBottom: 24 }}>
        {recommendations.map((r, i) => {
          const color = TYPE_COLORS[r.type] || '#38bdf8'
          const icon = TYPE_ICONS[r.type] || '📋'
          return (
            <div key={i} style={{
              background: 'var(--bg-card)', border: '1px solid var(--border)',
              borderRadius: 14, padding: 18, position: 'relative', overflow: 'hidden',
            }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg,transparent,${color},transparent)` }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 20 }}>{icon}</span>
                  <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: '1.5px',
                    textTransform: 'uppercase', color,
                    padding: '2px 8px', borderRadius: 4,
                    background: `${color}15`, border: `1px solid ${color}30`,
                  }}>
                    {r.type}
                  </span>
                </div>
                <div style={{
                  fontFamily: 'var(--font-disp)', fontSize: 18, fontWeight: 800, color,
                }}>
                  {Math.round(r.confidence * 100)}%
                </div>
              </div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
                {r.description}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>
                {r.expected_impact}
              </div>
              <div style={{
                fontSize: 11, color: 'var(--text-muted)', padding: '8px 10px',
                background: 'rgba(255,255,255,0.02)', borderRadius: 6,
              }}>
                {r.rationale}
              </div>
            </div>
          )
        })}
      </div>

      {recommendations.length === 0 && (
        <div style={{ color: 'var(--text-muted)', padding: 20, textAlign: 'center' }}>
          No recommendations available. Ensure the backend has loaded game data.
        </div>
      )}

      {/* AI strategy panel */}
      {aiStrategy && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid rgba(56,189,248,0.15)',
          borderRadius: 14, padding: 20,
        }}>
          <div style={{
            fontFamily: 'var(--font-disp)', fontSize: 11, fontWeight: 700,
            letterSpacing: '2.5px', textTransform: 'uppercase',
            color: 'var(--ice-dim)', marginBottom: 14,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: 14 }}>🤖</span>
            AI Strategy Summary
          </div>
          <div style={{
            fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.8,
            whiteSpace: 'pre-wrap',
          }}>
            {aiStrategy}
          </div>
        </div>
      )}
    </div>
  )
}
