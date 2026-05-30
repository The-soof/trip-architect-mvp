import { formatMoney } from '../lib/format'

export default function OptionCard({
  option,
  onSelect,
  active,
  selecting,
  selectionDisabled = false,
  selectionLabel = '',
  selectionLocked = false,
}) {
  return (
    <article className={`option-card surface-card ${active ? 'selected' : ''} ${selectionDisabled ? 'muted' : ''} ${selectionLocked ? 'locked' : ''}`}>
      <div className="option-header">
        <div>
          <p className="eyebrow">Option</p>
          <h3>{option.name}</h3>
        </div>
        <span className="score-pill">{option.fit_score}/10 fit</span>
      </div>

      <p>{option.summary}</p>
      <p className="option-rationale">{option.rationale}</p>

      <div className="stop-list">
        {option.days_by_stop.map((stop) => (
          <div className="stop-chip" key={`${option.id}-${stop.city}`}>
            <strong>{stop.city}</strong>
            <span>{stop.nights} nights</span>
          </div>
        ))}
      </div>

      <div className="cost-bar">
        <div>
          <p className="eyebrow">Estimated total</p>
          <strong>
            {formatMoney(option.estimated_total_min)} - {formatMoney(option.estimated_total_max)}
          </strong>
        </div>
        <div>
          <p className="eyebrow">Pace</p>
          <strong>{option.pace_label}</strong>
        </div>
      </div>

      <div className="breakdown-grid">
        <div className="mini-stat">
          <span>Flights</span>
          <strong>
            {formatMoney(option.cost_breakdown.flights.min)} - {formatMoney(option.cost_breakdown.flights.max)}
          </strong>
        </div>
        <div className="mini-stat">
          <span>Lodging</span>
          <strong>
            {formatMoney(option.cost_breakdown.lodging.min)} - {formatMoney(option.cost_breakdown.lodging.max)}
          </strong>
        </div>
        <div className="mini-stat">
          <span>Local + activities</span>
          <strong>
            {formatMoney(option.cost_breakdown.local_transport.min + option.cost_breakdown.food_and_activities.min)} -{' '}
            {formatMoney(option.cost_breakdown.local_transport.max + option.cost_breakdown.food_and_activities.max)}
          </strong>
        </div>
      </div>

      <ul className="tradeoff-list">
        {option.tradeoffs.map((tradeoff) => (
          <li key={tradeoff}>{tradeoff}</li>
        ))}
      </ul>

      {option.warning_flags.length ? (
        <div className="warning-list">
          {option.warning_flags.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}

      <div className="assumption-list">
        {option.price_assumptions.map((assumption) => (
          <small key={assumption}>{assumption}</small>
        ))}
      </div>

      <button
        className="secondary-button"
        disabled={selecting || selectionDisabled}
        onClick={() => onSelect(option.id)}
        type="button"
      >
        {active && selectionLocked
          ? 'Locked in plan'
          : active
            ? 'Selected plan'
            : selecting
              ? 'Locking trip...'
              : selectionDisabled
                ? selectionLabel || 'Locked'
                : 'Choose this trip'}
      </button>
    </article>
  )
}
