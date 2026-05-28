import { useEffect, useState } from 'react'

const defaultForm = {
  origin: '',
  start_date: '',
  end_date: '',
  destination_candidates: '',
  trip_style: '',
  budget_range: 'Mid-range',
  traveler_count: 2,
  pace_preference: 'Balanced',
}

export default function IntakeForm({ onSubmit, submitting, initialValues, onClearPreset, showPresetBanner = false }) {
  const [form, setForm] = useState(defaultForm)

  useEffect(() => {
    if (!initialValues) {
      return
    }
    setForm({
      ...defaultForm,
      ...initialValues,
      destination_candidates: Array.isArray(initialValues.destination_candidates)
        ? initialValues.destination_candidates.join(', ')
        : initialValues.destination_candidates || '',
    })
  }, [initialValues])

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }))
  }

  function handleSubmit(event) {
    event.preventDefault()
    onSubmit({
      ...form,
      traveler_count: Number(form.traveler_count),
      destination_candidates: form.destination_candidates
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
    })
  }

  return (
    <form className="planner-form surface-card" onSubmit={handleSubmit}>
      {showPresetBanner ? (
        <div className="surface-subtle surface-inline">
          <div>
            <strong>Using a previous trip as a starting point</strong>
            <p>Edit any field before generating a fresh set of options.</p>
          </div>
          <button className="ghost-button" onClick={onClearPreset} type="button">
            Clear preset
          </button>
        </div>
      ) : null}
      <div className="form-grid">
        <label>
          Origin city or airport
          <input
            name="origin"
            onChange={(event) => updateField('origin', event.target.value)}
            placeholder="New York"
            required
            value={form.origin}
          />
        </label>

        <label>
          Start date
          <input
            name="start_date"
            onChange={(event) => updateField('start_date', event.target.value)}
            required
            type="date"
            value={form.start_date}
          />
        </label>

        <label>
          End date
          <input
            name="end_date"
            onChange={(event) => updateField('end_date', event.target.value)}
            required
            type="date"
            value={form.end_date}
          />
        </label>

        <label>
          Destinations
          <input
            name="destination_candidates"
            onChange={(event) => updateField('destination_candidates', event.target.value)}
            placeholder="Barcelona, Split, Budapest"
            required
            value={form.destination_candidates}
          />
        </label>

        <label>
          Budget
          <select value={form.budget_range} onChange={(event) => updateField('budget_range', event.target.value)}>
            <option>Budget</option>
            <option>Mid-range</option>
            <option>Luxury</option>
          </select>
        </label>

        <label>
          Travelers
          <input
            max="12"
            min="1"
            onChange={(event) => updateField('traveler_count', event.target.value)}
            type="number"
            value={form.traveler_count}
          />
        </label>

        <label>
          Pace
          <select value={form.pace_preference} onChange={(event) => updateField('pace_preference', event.target.value)}>
            <option>Slow</option>
            <option>Balanced</option>
            <option>Fast-paced</option>
          </select>
        </label>
      </div>

      <label>
        Trip style blurb
        <textarea
          name="trip_style"
          onChange={(event) => updateField('trip_style', event.target.value)}
          placeholder="Fun summer trip with great food, nightlife, water, and some relaxation."
          required
          rows="5"
          value={form.trip_style}
        />
      </label>

      <button className="primary-button" disabled={submitting} type="submit">
        {submitting ? 'Designing routes...' : 'Generate trip options'}
      </button>
    </form>
  )
}
