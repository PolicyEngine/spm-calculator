import { useState, useMemo } from 'react'
import spmConfig from '../public/data/spm_config.json'

// PolicyEngine logo URL
const LOGO_URL = "https://raw.githubusercontent.com/PolicyEngine/policyengine-app/master/src/images/logos/policyengine/teal.png"

// Extract data from config
const { baseThresholds, states, costLevels, methodology } = spmConfig

// Calculate equivalence scale
function calculateEquivalenceScale(adults, children) {
  if (adults === 0 && children === 0) return 0

  const { firstAdult, additionalAdults, children: childWeight, referenceFamily } = methodology.equivalenceScale
  const adultScale = adults >= 1 ? firstAdult + additionalAdults * Math.max(adults - 1, 0) : 0
  const childScale = childWeight * children
  const rawScale = adultScale + childScale

  return rawScale / referenceFamily
}

// Format currency
function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0
  }).format(value)
}

function App() {
  // Form state
  const [year, setYear] = useState('2024')
  const [numAdults, setNumAdults] = useState(2)
  const [numChildren, setNumChildren] = useState(2)
  const [tenure, setTenure] = useState('renter')
  const [locationType, setLocationType] = useState('preset')
  const [costLevel, setCostLevel] = useState('national_average')
  const [selectedState, setSelectedState] = useState('CA')
  const [customGeoadj, setCustomGeoadj] = useState(1.0)

  // Calculate values
  const base = baseThresholds[year][tenure]
  const equivScale = calculateEquivalenceScale(numAdults, numChildren)

  const geoadj = useMemo(() => {
    if (locationType === 'preset') {
      return costLevels[costLevel].geoadj
    } else if (locationType === 'state') {
      return states[selectedState]?.geoadj || 1.0
    } else {
      return customGeoadj
    }
  }, [locationType, costLevel, selectedState, customGeoadj])

  const threshold = base * equivScale * geoadj
  const monthly = threshold / 12

  // Raw scale for display
  const rawScale = equivScale * methodology.equivalenceScale.referenceFamily
  const adultContrib = numAdults >= 1
    ? methodology.equivalenceScale.firstAdult + methodology.equivalenceScale.additionalAdults * Math.max(numAdults - 1, 0)
    : 0
  const childContrib = methodology.equivalenceScale.children * numChildren

  // Tenure display names
  const tenureNames = {
    renter: 'Renter',
    owner_with_mortgage: 'Owner with mortgage',
    owner_without_mortgage: 'Owner without mortgage'
  }

  // Cost level description
  const getCostDescription = () => {
    if (geoadj > 1) return 'above'
    if (geoadj < 1) return 'below'
    return 'average'
  }

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <img src={LOGO_URL} alt="PolicyEngine" />
        <h1>SPM Threshold Calculator</h1>
      </header>

      {/* Intro */}
      <p style={{ marginBottom: 24 }}>
        Calculate your <strong>Supplemental Poverty Measure (SPM) threshold</strong> based on your
        household characteristics. The SPM is used by the U.S. Census Bureau to measure poverty
        more comprehensively than the official poverty measure.
      </p>

      <div className="card">
        <strong>Formula:</strong> threshold = base_threshold × equivalence_scale × geographic_adjustment
      </div>

      {/* Main content */}
      <div className="grid grid-2" style={{ alignItems: 'start' }}>
        {/* Left: Inputs */}
        <div>
          <section className="section">
            <h2 className="section-title">Your Household</h2>

            {/* Year */}
            <div className="form-group">
              <label htmlFor="year">Year</label>
              <select id="year" value={year} onChange={e => setYear(e.target.value)}>
                <option value="2024">2024</option>
                <option value="2023">2023</option>
                <option value="2022">2022</option>
              </select>
              <p className="help-text">The year for which to calculate the threshold</p>
            </div>

            {/* Family composition */}
            <h3 style={{ fontSize: 16, marginBottom: 16, marginTop: 24 }}>Family Composition</h3>
            <div className="input-row">
              <div className="form-group">
                <label htmlFor="adults">Adults (18+)</label>
                <input
                  type="number"
                  id="adults"
                  min="0"
                  max="10"
                  value={numAdults}
                  onChange={e => setNumAdults(parseInt(e.target.value) || 0)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="children">Children (under 18)</label>
                <input
                  type="number"
                  id="children"
                  min="0"
                  max="15"
                  value={numChildren}
                  onChange={e => setNumChildren(parseInt(e.target.value) || 0)}
                />
              </div>
            </div>

            {/* Tenure */}
            <h3 style={{ fontSize: 16, marginBottom: 16, marginTop: 24 }}>Housing Tenure</h3>
            <div className="radio-group">
              {Object.entries(tenureNames).map(([key, name]) => (
                <label key={key} className={`radio-option ${tenure === key ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="tenure"
                    value={key}
                    checked={tenure === key}
                    onChange={e => setTenure(e.target.value)}
                  />
                  {name}
                </label>
              ))}
            </div>

            {/* Location */}
            <h3 style={{ fontSize: 16, marginBottom: 16, marginTop: 24 }}>Location</h3>
            <div className="form-group">
              <label htmlFor="locationType">Location type</label>
              <select id="locationType" value={locationType} onChange={e => setLocationType(e.target.value)}>
                <option value="preset">Cost level preset</option>
                <option value="state">Select state</option>
                <option value="custom">Custom GEOADJ</option>
              </select>
            </div>

            {locationType === 'preset' && (
              <div className="form-group">
                <label htmlFor="costLevel">Cost level</label>
                <select id="costLevel" value={costLevel} onChange={e => setCostLevel(e.target.value)}>
                  {Object.entries(costLevels).map(([key, { label, geoadj }]) => (
                    <option key={key} value={key}>{label} ({geoadj.toFixed(2)})</option>
                  ))}
                </select>
              </div>
            )}

            {locationType === 'state' && (
              <div className="form-group">
                <label htmlFor="state">State</label>
                <select id="state" value={selectedState} onChange={e => setSelectedState(e.target.value)}>
                  {Object.entries(states)
                    .sort((a, b) => a[1].name.localeCompare(b[1].name))
                    .map(([code, { name, geoadj }]) => (
                      <option key={code} value={code}>{name} ({geoadj.toFixed(2)})</option>
                    ))}
                </select>
              </div>
            )}

            {locationType === 'custom' && (
              <div className="form-group">
                <label htmlFor="customGeoadj">Custom GEOADJ ({customGeoadj.toFixed(2)})</label>
                <input
                  type="range"
                  id="customGeoadj"
                  min="0.70"
                  max="1.50"
                  step="0.01"
                  value={customGeoadj}
                  onChange={e => setCustomGeoadj(parseFloat(e.target.value))}
                  style={{ width: '100%' }}
                />
                <p className="help-text">GEOADJ ranges from ~0.84 (low-cost) to ~1.27 (high-cost)</p>
              </div>
            )}
          </section>
        </div>

        {/* Right: Results */}
        <div>
          <section className="section">
            <h2 className="section-title">Your SPM Threshold</h2>

            <div className="card card-highlight">
              <div className="result">
                <p className="result-label">SPM Threshold ({year})</p>
                <p className="result-value">{formatCurrency(threshold)}</p>
                <p className="result-description">
                  For a household with <strong>{numAdults} adult{numAdults !== 1 ? 's' : ''}</strong> and{' '}
                  <strong>{numChildren} child{numChildren !== 1 ? 'ren' : ''}</strong> who are{' '}
                  <strong>{tenureNames[tenure].toLowerCase()}s</strong> in a{' '}
                  <strong>{getCostDescription()}-cost area</strong>.
                </p>
              </div>
            </div>

            <div className="monthly-card">
              <p className="result-label">Monthly Equivalent</p>
              <p className="monthly-value">{formatCurrency(monthly)}</p>
            </div>
          </section>
        </div>
      </div>

      {/* Calculation breakdown */}
      <section className="section">
        <h2 className="section-title">How It's Calculated</h2>

        <h3 className="step-header">Step 1: Base Threshold</h3>
        <p>
          The base threshold is set by the BLS based on Consumer Expenditure Survey data.
          For {year}, the base thresholds for a reference family (2 adults, 2 children) are:
        </p>
        <table>
          <thead>
            <tr>
              <th>Tenure Type</th>
              <th>Base Threshold</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(tenureNames).map(([key, name]) => (
              <tr key={key} style={tenure === key ? { backgroundColor: 'var(--teal-50)' } : {}}>
                <td>{name}</td>
                <td>{formatCurrency(baseThresholds[year][key])}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p><strong>Your base threshold ({tenureNames[tenure]}):</strong> {formatCurrency(base)}</p>

        <h3 className="step-header">Step 2: Equivalence Scale</h3>
        <p>The equivalence scale adjusts for family size using the three-parameter formula:</p>
        <ul style={{ marginLeft: 24, marginBottom: 16 }}>
          <li>First adult: <strong>1.0</strong></li>
          <li>Additional adults: <strong>+0.5 each</strong></li>
          <li>Children: <strong>+0.3 each</strong></li>
        </ul>
        <p>Your household:</p>
        <ul style={{ marginLeft: 24, marginBottom: 16 }}>
          <li>Adults: {numAdults} → 1.0 + {(0.5 * Math.max(numAdults - 1, 0)).toFixed(1)} = <strong>{adultContrib.toFixed(1)}</strong></li>
          <li>Children: {numChildren} × 0.3 = <strong>{childContrib.toFixed(1)}</strong></li>
          <li><strong>Raw scale: {rawScale.toFixed(2)}</strong></li>
        </ul>
        <p>Normalized to reference family (2A2C = 2.1):</p>
        <p><strong>Equivalence scale: {rawScale.toFixed(2)} ÷ 2.1 = {equivScale.toFixed(3)}</strong></p>

        <h3 className="step-header">Step 3: Geographic Adjustment (GEOADJ)</h3>
        <p>GEOADJ adjusts for local housing costs using the formula:</p>
        <div className="code-block" style={{ marginBottom: 16 }}>
          GEOADJ = (local median rent / national median rent) × 0.492 + 0.508
        </div>
        <p>Where 0.492 is the housing share of the SPM threshold for renters.</p>
        <ul style={{ marginLeft: 24, marginBottom: 16 }}>
          <li>GEOADJ ranges from ~0.84 (West Virginia) to ~1.27 (Hawaii)</li>
          <li>National average: 1.00</li>
        </ul>
        <p><strong>Your GEOADJ: {geoadj.toFixed(2)}</strong></p>

        <h3 className="step-header">Step 4: Final Calculation</h3>
        <div className="code-block">
          Threshold = Base × Equivalence Scale × GEOADJ<br />
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= {formatCurrency(base)} × {equivScale.toFixed(3)} × {geoadj.toFixed(2)}<br />
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= <strong>{formatCurrency(threshold)}</strong>
        </div>
      </section>

      {/* Comparison table */}
      <section className="section">
        <h2 className="section-title">Comparison</h2>
        <p>
          Thresholds for different scenarios with {numAdults} adult{numAdults !== 1 ? 's' : ''} and{' '}
          {numChildren} child{numChildren !== 1 ? 'ren' : ''}:
        </p>
        <table>
          <thead>
            <tr>
              <th>Tenure</th>
              <th>Low-cost (0.84)</th>
              <th>Average (1.00)</th>
              <th>High-cost (1.20)</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(tenureNames).map(([key, name]) => (
              <tr key={key}>
                <td>{name}</td>
                <td>{formatCurrency(baseThresholds[year][key] * equivScale * 0.84)}</td>
                <td>{formatCurrency(baseThresholds[year][key] * equivScale * 1.00)}</td>
                <td>{formatCurrency(baseThresholds[year][key] * equivScale * 1.20)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Resources */}
      <section className="section">
        <h2 className="section-title">Resources</h2>
        <ul style={{ marginLeft: 24 }}>
          <li>
            <a href="https://www.bls.gov/pir/spm/spm_thresholds_2024.htm" target="_blank" rel="noopener noreferrer">
              BLS SPM Thresholds
            </a> - Official threshold values
          </li>
          <li>
            <a href="https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html" target="_blank" rel="noopener noreferrer">
              Census SPM Methodology
            </a> - How SPM is calculated
          </li>
          <li>
            <a href="https://github.com/PolicyEngine/spm-calculator" target="_blank" rel="noopener noreferrer">
              spm-calculator on GitHub
            </a> - Source code for this tool
          </li>
        </ul>
      </section>

      {/* Footer */}
      <footer className="footer">
        <img src={LOGO_URL} alt="PolicyEngine" />
        <p>
          Built by <a href="https://policyengine.org">PolicyEngine</a> using the spm-calculator package.
        </p>
      </footer>
    </div>
  )
}

export default App
