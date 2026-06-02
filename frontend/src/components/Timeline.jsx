export default function Timeline({ itinerary }) {
  if (!itinerary) {
    return null
  }

  return (
    <section className="timeline surface-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Detailed itinerary</p>
          <h2>{itinerary.title}</h2>
        </div>
        <p>{itinerary.overview}</p>
      </div>

      <div className="neighborhood-grid">
        {itinerary.neighborhood_guidance.map((item) => (
          <article className="mini-card neighborhood-card" key={`${item.city}-${item.recommended_area}`}>
            <p className="eyebrow">{item.city}</p>
            <strong>{item.recommended_area}</strong>
            <p>{item.why}</p>
          </article>
        ))}
      </div>

      <div className="timeline-list">
        {itinerary.days.map((day) => (
          <article className="timeline-day" key={day.id}>
            <div className="timeline-marker">
              <span>Day {day.day_number}</span>
              <strong>{day.city}</strong>
            </div>
            <div className="timeline-content">
              <h3>{day.theme}</h3>
              <dl className="day-blocks">
                <div className="day-block">
                  <dt>Morning</dt>
                  <dd>{day.morning}</dd>
                </div>
                <div className="day-block">
                  <dt>Afternoon</dt>
                  <dd>{day.afternoon}</dd>
                </div>
                <div className="day-block">
                  <dt>Evening</dt>
                  <dd>{day.evening}</dd>
                </div>
              </dl>
              <div className="day-notes">
                <p className="note-line">{day.logistics_note}</p>
                <p className="note-line">{day.flexibility_note}</p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
