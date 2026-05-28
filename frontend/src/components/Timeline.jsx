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
          <article className="mini-card" key={`${item.city}-${item.recommended_area}`}>
            <strong>{item.city}</strong>
            <span>{item.recommended_area}</span>
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
              <p><strong>Morning:</strong> {day.morning}</p>
              <p><strong>Afternoon:</strong> {day.afternoon}</p>
              <p><strong>Evening:</strong> {day.evening}</p>
              <p className="note-line">{day.logistics_note}</p>
              <p className="note-line">{day.flexibility_note}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}

