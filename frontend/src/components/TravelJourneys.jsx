import { useMemo, useState } from 'react'
import { formatDuration, formatMoney, formatSegmentTime } from '../lib/format'

const MODE_META = {
  flight: { glyph: '✈️', label: 'Flight' },
  ferry: { glyph: '⛴️', label: 'Ferry' },
  train: { glyph: '🚆', label: 'Train' },
  car: { glyph: '🚗', label: 'Car' },
  transfer: { glyph: '🚕', label: 'Transfer' },
}

function modeMeta(mode) {
  return MODE_META[mode] || { glyph: '📍', label: mode }
}

function priceBand(min, max) {
  if (!min && !max) return null
  if (min === max) return formatMoney(min)
  return `${formatMoney(min)}–${formatMoney(max)}`
}

function Segment({ segment }) {
  const meta = modeMeta(segment.mode)
  const depart = formatSegmentTime(segment.depart_time)
  const arrive = formatSegmentTime(segment.arrive_time)
  return (
    <li className="segment-row">
      <span aria-hidden="true" className={`segment-icon segment-icon--${segment.mode}`} title={meta.label}>
        {meta.glyph}
      </span>
      <div className="segment-body">
        <div className="segment-headline">
          <strong className="segment-route">
            {segment.from_label} <span aria-hidden="true">&rarr;</span> {segment.to_label}
          </strong>
          {segment.deep_link ? (
            <a className="segment-link" href={segment.deep_link} rel="noreferrer" target="_blank">
              {meta.label === 'Flight' ? 'Find flight' : `Book ${meta.label.toLowerCase()}`} &#8599;
            </a>
          ) : null}
        </div>
        <p className="segment-meta">
          {depart ? (
            <span className="segment-time">
              {depart}
              {arrive ? ` – ${arrive}` : ''}
            </span>
          ) : (
            <span className="segment-time segment-time--soft">{meta.label}</span>
          )}
          {segment.provider ? <span className="segment-dot">&middot;</span> : null}
          {segment.provider ? <span>{segment.provider}</span> : null}
          {segment.price_estimate ? <span className="segment-dot">&middot;</span> : null}
          {segment.price_estimate ? <span>~{formatMoney(segment.price_estimate)}</span> : null}
        </p>
        {segment.note ? <p className="segment-note">{segment.note}</p> : null}
      </div>
    </li>
  )
}

function JourneyCard({ journey, expanded, onToggle, onSelect, isSelected, routeLocked, saving }) {
  const band = priceBand(journey.total_price_min, journey.total_price_max)
  const duration = formatDuration(journey.total_duration_minutes)
  const readOnly = routeLocked && !isSelected
  const tags = journey.tags || []

  return (
    <article
      className={`journey-card${journey.is_recommended ? ' journey-card--recommended' : ''}${
        isSelected ? ' journey-card--selected' : ''
      }${readOnly ? ' journey-card--readonly' : ''}`}
    >
      <button
        aria-expanded={expanded}
        className="journey-head"
        onClick={onToggle}
        type="button"
      >
        <span className="journey-head-main">
          <span className="journey-title-row">
            <strong className="journey-title">{journey.title}</strong>
            {journey.is_recommended ? <span className="journey-badge">Recommended</span> : null}
            {isSelected ? <span className="journey-badge journey-badge--selected">Selected</span> : null}
          </span>
          <span className="journey-summary">{journey.summary}</span>
          <span className="journey-stats">
            {band ? <span className="journey-stat journey-stat--price">{band}</span> : null}
            {duration ? <span className="journey-stat">{duration} travel</span> : null}
            <span className="journey-stat journey-stat--soft">
              {journey.segments.length} step{journey.segments.length === 1 ? '' : 's'}
            </span>
          </span>
        </span>
        <span aria-hidden="true" className={`journey-chevron${expanded ? ' is-open' : ''}`}>&#8964;</span>
      </button>

      {tags.length ? (
        <div className="journey-tags">
          {tags.map((tag) => (
            <span className="journey-tag" key={tag}>
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {expanded ? (
        <>
          <ol className="journey-segments">
            {[...journey.segments]
              .sort((a, b) => a.order_index - b.order_index)
              .map((segment) => (
                <Segment key={segment.id} segment={segment} />
              ))}
          </ol>
          <div className="journey-foot">
            {isSelected ? (
              <span className="status-pill status-confirmed">Selected journey</span>
            ) : routeLocked ? (
              <span className="muted-inline">Another journey is locked for this trip.</span>
            ) : (
              <button
                className="primary-button"
                disabled={saving}
                onClick={() => onSelect(journey.id)}
                type="button"
              >
                {saving ? 'Selecting…' : 'Select this journey'}
              </button>
            )}
          </div>
        </>
      ) : null}
    </article>
  )
}

export default function TravelJourneys({
  journeys,
  selectedJourneyId,
  routeLocked,
  onSelectJourney,
  bookingSavingKey,
}) {
  const sorted = useMemo(
    () => [...(journeys || [])].sort((a, b) => a.sort_order - b.sort_order),
    [journeys],
  )
  // Expand the recommended (or selected) journey by default; others collapsed.
  const defaultOpen = useMemo(() => {
    const target = sorted.find((j) => j.id === selectedJourneyId) || sorted.find((j) => j.is_recommended) || sorted[0]
    return target ? { [target.id]: true } : {}
  }, [sorted, selectedJourneyId])
  const [openMap, setOpenMap] = useState(defaultOpen)

  function toggle(id) {
    setOpenMap((prev) => ({ ...prev, [id]: !(id in prev ? prev[id] : defaultOpen[id]) }))
  }

  if (!sorted.length) {
    return (
      <section className="surface-card">
        <div className="section-header">
          <div>
            <p className="eyebrow">Travel</p>
            <h2>Getting there</h2>
          </div>
        </div>
        <article className="empty-state-card">
          <strong>Travel options are still being assembled.</strong>
          <p>Once the itinerary finishes building, door-to-door journeys will appear here.</p>
        </article>
      </section>
    )
  }

  return (
    <section className="surface-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Travel</p>
          <h2>Ways to make the trip</h2>
        </div>
        <p>
          Each journey is a complete door-to-door plan tuned to a different priority. Open one to see every
          step—flights, ferries, and transfers—with its own booking link.
        </p>
      </div>
      <div className="journey-list">
        {sorted.map((journey) => {
          const isOpen = journey.id in openMap ? openMap[journey.id] : Boolean(defaultOpen[journey.id])
          return (
            <JourneyCard
              expanded={isOpen}
              isSelected={journey.id === selectedJourneyId}
              journey={journey}
              key={journey.id}
              onSelect={(id) => onSelectJourney('journey', id, 'confirmed')}
              onToggle={() => toggle(journey.id)}
              routeLocked={routeLocked}
              saving={bookingSavingKey === `journey:${journey.id}`}
            />
          )
        })}
      </div>
    </section>
  )
}
