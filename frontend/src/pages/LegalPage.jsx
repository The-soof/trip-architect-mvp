import { Link } from 'react-router-dom'

const CONTENT = {
  privacy: {
    eyebrow: 'Privacy',
    title: 'Privacy policy',
    paragraphs: [
      'Trip Architect stores account details, saved trips, and booking selections so travelers can reopen and refine their plans later.',
      'Planning inputs are used to generate route options and itinerary details. Sensitive payment details are not stored in this MVP.',
      'If you need data removed, contact support and include the email address attached to your workspace.',
    ],
  },
  terms: {
    eyebrow: 'Terms',
    title: 'Terms of service',
    paragraphs: [
      'Trip Architect provides planning guidance, estimated budgets, and booking discovery links. Travelers should verify final availability and pricing before purchasing.',
      'Accounts are intended for lawful personal travel planning and internal testing of the product.',
      'The service may evolve while the MVP is being refined, including changes to trip generation behavior and saved workspace features.',
    ],
  },
}

export default function LegalPage({ type }) {
  const content = CONTENT[type]

  return (
    <main className="landing-shell legal-shell">
      <header className="landing-header">
        <Link className="brandmark" to="/">
          <span className="brandmark-dot" />
          <span>
            Trip Architect
            <small>Travel planning workspace</small>
          </span>
        </Link>
        <Link className="ghost-button" to="/">
          Return home
        </Link>
      </header>

      <section className="surface-card legal-card">
        <p className="eyebrow">{content.eyebrow}</p>
        <h1>{content.title}</h1>
        {content.paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </section>
    </main>
  )
}
