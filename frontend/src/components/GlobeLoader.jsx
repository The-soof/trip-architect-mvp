import { useEffect, useRef, useState } from 'react'

// Faithful port of the "Globe Loader" design (Globe Loader.html).
// d3 + topojson-client are loaded once from CDN and cached, exactly as the
// original standalone design did, so no build-time dependency is required.

const SCRIPTS = [
  'https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js',
  'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js',
]
const ATLAS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json'

let scriptsPromise = null
let atlasPromise = null

// Generic, on-brand travel tips shown at the bottom of the full-screen loaders
// to fill the longer wait. Kept tasteful (no jokes) to match the product tone.
const TRAVEL_TIPS = [
  'Mid-week flights are often cheaper than weekend departures.',
  'Pack a portable charger for long transit days.',
  'Keep an offline photo of your passport in case you misplace it.',
  'Booking stays near transit can cut your daily travel time.',
  'Carry-on only? Roll clothes to save space and avoid wrinkles.',
  'Tell your bank your travel dates so your card does not get frozen.',
  'Early-morning sightseeing beats the crowds and the midday heat.',
  'Keep a little local currency on hand for taxis and small vendors.',
]

const MESSAGE_INTERVAL = 4000
const TIP_INTERVAL = 7000

// Cycle an index through `length` items every `delay` ms while `enabled`.
function useRotatingIndex(length, delay, enabled) {
  const [index, setIndex] = useState(0)
  useEffect(() => {
    setIndex(0)
    if (!enabled || length <= 1) {
      return undefined
    }
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % length)
    }, delay)
    return () => window.clearInterval(id)
  }, [length, delay, enabled])
  return index
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`)
    if (existing) {
      if (existing.dataset.loaded === 'true') {
        resolve()
        return
      }
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', reject)
      return
    }
    const el = document.createElement('script')
    el.src = src
    el.async = true
    el.addEventListener('load', () => {
      el.dataset.loaded = 'true'
      resolve()
    })
    el.addEventListener('error', reject)
    document.head.appendChild(el)
  })
}

function ensureScripts() {
  if (!scriptsPromise) {
    // d3 must be present before topojson reads it; load sequentially.
    scriptsPromise = SCRIPTS.reduce(
      (chain, src) => chain.then(() => loadScript(src)),
      Promise.resolve(),
    )
  }
  return scriptsPromise
}

function ensureAtlas() {
  if (!atlasPromise) {
    atlasPromise = ensureScripts()
      .then(() => fetch(ATLAS_URL))
      .then((r) => r.json())
      .then((topo) => ({
        land: window.topojson.feature(topo, topo.objects.countries),
        borders: window.topojson.mesh(topo, topo.objects.countries),
      }))
  }
  return atlasPromise
}

export default function GlobeLoader({
  fullscreen = false,
  className = '',
  title = '',
  messages = [],
  showTips = false,
}) {
  const canvasRef = useRef(null)
  const messageIndex = useRotatingIndex(messages.length, MESSAGE_INTERVAL, messages.length > 1)
  const tipIndex = useRotatingIndex(TRAVEL_TIPS.length, TIP_INTERVAL, showTips)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || typeof canvas.getContext !== 'function') {
      return undefined
    }
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      return undefined
    }

    let rafId = 0
    let cancelled = false

    const SIZE = 320
    const CX = SIZE / 2
    const CY = SIZE / 2
    const R = 120 // globe radius
    const INK = '7, 18, 38' // app navy ink

    const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1))
    canvas.width = SIZE * dpr
    canvas.height = SIZE * dpr
    ctx.scale(dpr, dpr)
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'

    const ink = (a) => `rgba(${INK},${a})`

    let projection = null
    let path = null
    let graticule = null
    let land = null
    let borders = null

    // ---- Commercial airliner (top view, nose at +x) ----
    function traceAirliner(c) {
      c.beginPath()
      c.moveTo(13, 0)
      c.lineTo(9, 1.0); c.lineTo(0, 1.9); c.lineTo(-10, 1.7)
      c.lineTo(-13, 1.0); c.lineTo(-14, 0)
      c.lineTo(-13, -1.0); c.lineTo(-10, -1.7); c.lineTo(0, -1.9); c.lineTo(9, -1.0)
      c.closePath()
      c.moveTo(2, 1.5); c.lineTo(-9, 10); c.lineTo(-11.5, 9.8); c.lineTo(-4.5, 1.5); c.closePath()
      c.moveTo(2, -1.5); c.lineTo(-9, -10); c.lineTo(-11.5, -9.8); c.lineTo(-4.5, -1.5); c.closePath()
      c.moveTo(-10, 1.2); c.lineTo(-15.5, 4.6); c.lineTo(-16.5, 4.4); c.lineTo(-12.5, 1.2); c.closePath()
      c.moveTo(-10, -1.2); c.lineTo(-15.5, -4.6); c.lineTo(-16.5, -4.4); c.lineTo(-12.5, -1.2); c.closePath()
      c.moveTo(-2, 4.0); c.lineTo(-5.6, 4.4); c.lineTo(-5.6, 5.6); c.lineTo(-2, 5.2); c.closePath()
      c.moveTo(-2, -4.0); c.lineTo(-5.6, -4.4); c.lineTo(-5.6, -5.6); c.lineTo(-2, -5.2); c.closePath()
    }

    // ---- Tilted orbit (top-right <-> bottom-left), continuous ----
    const ORX = 138, ORY = 60
    const TILT = -40 * Math.PI / 180
    const cosT = Math.cos(TILT), sinT = Math.sin(TILT)
    const PERIOD = 9
    const PLANE_S = 1.15

    function orbitAt(t) {
      const th = (t / PERIOD) * Math.PI * 2
      const lx = ORX * Math.cos(th), ly = ORY * Math.sin(th)
      const dlx = -ORX * Math.sin(th), dly = ORY * Math.cos(th)
      return {
        x: CX + lx * cosT - ly * sinT,
        y: CY + lx * sinT + ly * cosT,
        angle: Math.atan2(dlx * sinT + dly * cosT, dlx * cosT - dly * sinT),
        behind: Math.sin(th) < 0,
      }
    }

    function drawPlane(p, alpha) {
      ctx.save()
      ctx.translate(p.x, p.y)
      ctx.rotate(p.angle)
      ctx.scale(PLANE_S, PLANE_S)
      traceAirliner(ctx)
      ctx.fillStyle = ink(alpha)
      ctx.fill()
      ctx.restore()
    }

    function drawOrbitPath(front) {
      ctx.save()
      ctx.setLineDash([0.5, 6])
      ctx.lineWidth = 1.6
      ctx.strokeStyle = ink(0.16)
      ctx.beginPath()
      ctx.ellipse(CX, CY, ORX, ORY, TILT, front ? 0 : Math.PI, front ? Math.PI : Math.PI * 2)
      ctx.stroke()
      ctx.restore()
    }

    function render(ms) {
      if (cancelled) {
        return
      }
      const t = ms / 1000
      ctx.clearRect(0, 0, SIZE, SIZE)

      projection.rotate([t * 18, -18, 0])
      const p = orbitAt(t)

      drawOrbitPath(false)
      if (p.behind) drawPlane(p, 0.34)

      ctx.save()
      ctx.shadowColor = 'rgba(7,18,38,0.16)'
      ctx.shadowBlur = 24
      ctx.shadowOffsetY = 14
      ctx.beginPath()
      ctx.arc(CX, CY, R, 0, Math.PI * 2)
      ctx.fillStyle = ink(0.05)
      ctx.fill()
      ctx.restore()

      ctx.save()
      ctx.beginPath()
      ctx.arc(CX, CY, R, 0, Math.PI * 2)
      ctx.clip()

      ctx.beginPath()
      path(graticule)
      ctx.strokeStyle = ink(0.1)
      ctx.lineWidth = 0.6
      ctx.stroke()

      if (land) {
        ctx.beginPath()
        path(land)
        ctx.fillStyle = ink(0.14)
        ctx.fill()
        ctx.beginPath()
        path(borders)
        ctx.strokeStyle = ink(0.6)
        ctx.lineWidth = 0.6
        ctx.stroke()
      }

      const sheen = ctx.createRadialGradient(CX - 40, CY - 46, 6, CX - 18, CY - 18, R * 1.5)
      sheen.addColorStop(0, 'rgba(255,255,255,0.42)')
      sheen.addColorStop(0.4, 'rgba(255,255,255,0.06)')
      sheen.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.fillStyle = sheen
      ctx.fillRect(CX - R, CY - R, R * 2, R * 2)
      ctx.restore()

      ctx.beginPath()
      ctx.arc(CX, CY, R, 0, Math.PI * 2)
      ctx.strokeStyle = ink(0.85)
      ctx.lineWidth = 1.2
      ctx.stroke()

      drawOrbitPath(true)
      if (!p.behind) drawPlane(p, 0.92)

      rafId = window.requestAnimationFrame(render)
    }

    ensureScripts()
      .then(() => {
        if (cancelled) {
          return
        }
        const d3 = window.d3
        projection = d3.geoOrthographic().scale(R).translate([CX, CY]).clipAngle(90)
        path = d3.geoPath(projection, ctx)
        graticule = d3.geoGraticule10()
        rafId = window.requestAnimationFrame(render)
        // Country outlines stream in once the atlas resolves.
        ensureAtlas()
          .then((data) => {
            if (cancelled) {
              return
            }
            land = data.land
            borders = data.borders
          })
          .catch(() => {})
      })
      .catch(() => {})

    return () => {
      cancelled = true
      if (rafId) {
        window.cancelAnimationFrame(rafId)
      }
    }
  }, [])

  return (
    <div
      className={`globe-loader${fullscreen ? ' globe-loader-fullscreen' : ''}${className ? ` ${className}` : ''}`}
    >
      {title || messages.length ? (
        <div className="globe-loader-copy">
          {title ? <p className="globe-loader-title">{title}</p> : null}
          {messages.length ? (
            <p aria-live="polite" className="globe-loader-sub" key={messageIndex}>
              {messages[messageIndex % messages.length]}
            </p>
          ) : null}
        </div>
      ) : null}

      <div aria-label="Loading" className="globe-loader-stage" role="img">
        <canvas height="320" ref={canvasRef} width="320" />
      </div>

      {showTips ? (
        <p className="globe-loader-tip" key={tipIndex}>
          <span className="globe-loader-tip-label">Tip</span>
          {TRAVEL_TIPS[tipIndex % TRAVEL_TIPS.length]}
        </p>
      ) : null}
    </div>
  )
}
