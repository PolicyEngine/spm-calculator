import { useState, useMemo } from 'react'
import spmConfig from '../public/data/spm_config.json'

// PolicyEngine logo URL
const LOGO_URL = "https://raw.githubusercontent.com/PolicyEngine/policyengine-app/master/src/images/logos/policyengine/teal.png"

// Extract data from config
const { baseThresholds, states, costLevels, methodology, forecast } = spmConfig
const LATEST_PUBLISHED_YEAR = forecast.latestPublishedYear

// Get all available years sorted
const availableYears = Object.keys(baseThresholds).sort((a, b) => parseInt(b) - parseInt(a))

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

// Check if a year is forecasted
function isForecast(year) {
  return parseInt(year) > LATEST_PUBLISHED_YEAR
}

// Component card with expandable details
function CalculationCard({ icon, title, value, subtitle, color, details, isExpanded, onToggle }) {
  return (
    <div className="calc-card" style={{ borderTopColor: color }}>
      <div className="calc-card-header">
        <span className="calc-card-icon">{icon}</span>
        <span className="calc-card-title">{title}</span>
      </div>
      <div className="calc-card-value" style={{ color }}>{value}</div>
      <div className="calc-card-subtitle">{subtitle}</div>
      {details && (
        <>
          <button className="calc-card-toggle" onClick={onToggle}>
            {isExpanded ? '− Hide details' : '+ Show details'}
          </button>
          {isExpanded && <div className="calc-card-details">{details}</div>}
        </>
      )}
    </div>
  )
}

function App() {
  // Form state
  const currentYear = new Date().getFullYear()
  const defaultYear = availableYears.includes(String(currentYear)) ? String(currentYear) : String(LATEST_PUBLISHED_YEAR)

  const [year, setYear] = useState(defaultYear)
  const [numAdults, setNumAdults] = useState(2)
  const [numChildren, setNumChildren] = useState(2)
  const [tenure, setTenure] = useState('renter')
  const [locationType, setLocationType] = useState('preset')
  const [costLevel, setCostLevel] = useState('national_average')
  const [selectedState, setSelectedState] = useState('CA')
  const [customGeoadj, setCustomGeoadj] = useState(1.0)

  // Expanded state for detail cards
  const [expandedCard, setExpandedCard] = useState(null)

  // Calculate values
  const base = baseThresholds[year][tenure]
  const equivScale = calculateEquivalenceScale(numAdults, numChildren)
  const isForecasted = isForecast(year)
  const rawScale = equivScale * methodology.equivalenceScale.referenceFamily

  const geoadj = useMemo(() => {
    if (locationType === 'preset') return costLevels[costLevel].geoadj
    if (locationType === 'state') return states[selectedState]?.geoadj || 1.0
    return customGeoadj
  }, [locationType, costLevel, selectedState, customGeoadj])

  const threshold = base * equivScale * geoadj
  const monthly = threshold / 12
  const referenceThreshold = base * 1.0 * 1.0 // Reference family, national average
  const percentOfReference = (threshold / referenceThreshold * 100).toFixed(0)

  // Get CE Survey years that feed into a given threshold year
  // BLS uses 5-year rolling data with 2-year lag (e.g., 2024 thresholds use 2018-2022 CE data)
  const getCESurveyYears = (thresholdYear) => {
    const endYear = parseInt(thresholdYear) - 2
    return Array.from({ length: 5 }, (_, i) => endYear - 4 + i)
  }
  const ceSurveyYears = getCESurveyYears(year)

  // Tenure display names
  const tenureNames = {
    renter: 'Renter',
    owner_with_mortgage: 'Owner with mortgage',
    owner_without_mortgage: 'Owner without mortgage'
  }

  const tenureShortNames = {
    renter: 'Renter',
    owner_with_mortgage: 'Mortgage',
    owner_without_mortgage: 'No mortgage'
  }

  // Get location description
  const getLocationName = () => {
    if (locationType === 'preset') return costLevels[costLevel].label
    if (locationType === 'state') return states[selectedState]?.name
    return `Custom (${customGeoadj.toFixed(2)})`
  }

  return (
    <div className="container">
      {/* Header */}
      <header className="header">
        <img src={LOGO_URL} alt="PolicyEngine" />
        <h1>SPM Threshold Calculator</h1>
      </header>

      {/* Two-column layout */}
      <div className="main-grid">
        {/* Left: Inputs */}
        <div className="inputs-panel">
          <h2 className="panel-title">Your Household</h2>

          {/* Year */}
          <div className="form-group">
            <label>Year</label>
            <select value={year} onChange={e => setYear(e.target.value)}>
              {availableYears.map(y => (
                <option key={y} value={y}>
                  {y} {parseInt(y) > LATEST_PUBLISHED_YEAR ? '(forecast)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Family - compact inline */}
          <div className="form-group">
            <label>Family</label>
            <div className="inline-inputs">
              <div className="inline-input">
                <input
                  type="number"
                  min="0"
                  max="10"
                  value={numAdults}
                  onChange={e => setNumAdults(parseInt(e.target.value) || 0)}
                />
                <span>adults</span>
              </div>
              <div className="inline-input">
                <input
                  type="number"
                  min="0"
                  max="15"
                  value={numChildren}
                  onChange={e => setNumChildren(parseInt(e.target.value) || 0)}
                />
                <span>children</span>
              </div>
            </div>
          </div>

          {/* Tenure - horizontal chips */}
          <div className="form-group">
            <label>Housing</label>
            <div className="chip-group">
              {Object.entries(tenureShortNames).map(([key, name]) => (
                <button
                  key={key}
                  className={`chip ${tenure === key ? 'selected' : ''}`}
                  onClick={() => setTenure(key)}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          {/* Location */}
          <div className="form-group">
            <label>Location</label>
            <div className="chip-group" style={{ marginBottom: 12 }}>
              <button
                className={`chip ${locationType === 'preset' ? 'selected' : ''}`}
                onClick={() => setLocationType('preset')}
              >
                Cost level
              </button>
              <button
                className={`chip ${locationType === 'state' ? 'selected' : ''}`}
                onClick={() => setLocationType('state')}
              >
                State
              </button>
              <button
                className={`chip ${locationType === 'custom' ? 'selected' : ''}`}
                onClick={() => setLocationType('custom')}
              >
                Custom
              </button>
            </div>

            {locationType === 'preset' && (
              <select value={costLevel} onChange={e => setCostLevel(e.target.value)}>
                {Object.entries(costLevels).map(([key, { label }]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            )}

            {locationType === 'state' && (
              <select value={selectedState} onChange={e => setSelectedState(e.target.value)}>
                {Object.entries(states)
                  .sort((a, b) => a[1].name.localeCompare(b[1].name))
                  .map(([code, { name }]) => (
                    <option key={code} value={code}>{name}</option>
                  ))}
              </select>
            )}

            {locationType === 'custom' && (
              <div className="slider-container">
                <input
                  type="range"
                  min="0.70"
                  max="1.50"
                  step="0.01"
                  value={customGeoadj}
                  onChange={e => setCustomGeoadj(parseFloat(e.target.value))}
                />
                <span className="slider-value">{customGeoadj.toFixed(2)}</span>
              </div>
            )}
          </div>
        </div>

        {/* Right: Results */}
        <div className="results-panel">
          {/* Main result */}
          <div className="result-hero">
            {isForecasted && <span className="forecast-badge">FORECAST</span>}
            <div className="result-label">Your {year} SPM Threshold</div>
            <div className="result-amount">{formatCurrency(threshold)}</div>
            <div className="result-monthly">{formatCurrency(monthly)}/month</div>
            <div className="result-year-note">
              Used with {parseInt(year) - 1} income (March {year} CPS ASEC)
            </div>
          </div>

          {/* Visual formula */}
          <div className="formula-visual">
            <div className="formula-component">
              <div className="formula-value">{formatCurrency(base)}</div>
              <div className="formula-label">Base</div>
            </div>
            <div className="formula-operator">×</div>
            <div className="formula-component">
              <div className="formula-value">{equivScale.toFixed(2)}</div>
              <div className="formula-label">Family size</div>
            </div>
            <div className="formula-operator">×</div>
            <div className="formula-component">
              <div className="formula-value">{geoadj.toFixed(2)}</div>
              <div className="formula-label">Location</div>
            </div>
            <div className="formula-operator">=</div>
            <div className="formula-component formula-result">
              <div className="formula-value">{formatCurrency(threshold)}</div>
              <div className="formula-label">Threshold</div>
            </div>
          </div>

          {/* Comparison bar */}
          <div className="comparison-section">
            <div className="comparison-label">
              Compared to reference family (2 adults, 2 children, national average):
            </div>
            <div className="comparison-bar-container">
              {(() => {
                const maxValue = Math.max(threshold, referenceThreshold)
                const thresholdPct = (threshold / maxValue) * 100
                const refPct = (referenceThreshold / maxValue) * 100
                return (
                  <>
                    <div className="comparison-bar-bg">
                      <div
                        className="comparison-bar-fill"
                        style={{ width: `${thresholdPct}%` }}
                      />
                      <div
                        className="comparison-bar-marker"
                        style={{ left: `${refPct}%` }}
                        title="Reference family threshold"
                      />
                    </div>
                    <div className="comparison-values">
                      <span>{formatCurrency(threshold)}</span>
                      <span className="comparison-ref">Reference: {formatCurrency(referenceThreshold)}</span>
                    </div>
                  </>
                )
              })()}
            </div>
            <div className="comparison-percent">
              {percentOfReference > 100
                ? `${percentOfReference - 100}% above reference`
                : percentOfReference < 100
                  ? `${100 - percentOfReference}% below reference`
                  : 'Same as reference'}
            </div>
          </div>
        </div>
      </div>

      {/* Expandable explanation cards */}
      <div className="explanation-section">
        <h2 className="section-title">How It's Calculated</h2>

        <div className="calc-cards">
          <CalculationCard
            icon="🏠"
            title="Base Threshold"
            value={formatCurrency(base)}
            subtitle={`${tenureNames[tenure]}, ${year}${isForecasted ? ' (forecast)' : ''}`}
            color="var(--teal-500)"
            isExpanded={expandedCard === 'base'}
            onToggle={() => setExpandedCard(expandedCard === 'base' ? null : 'base')}
            details={
              <div>
                <p>
                  The base comes from the <strong>Consumer Expenditure Survey</strong> —
                  what families actually spend on essentials (food, clothing, shelter, utilities).
                </p>
                <p style={{ marginTop: 12 }}>
                  BLS uses 5 rolling years of data with a 2-year lag, calculating <strong>83% of median</strong> spending
                  for families with children. The {year} threshold uses CE data from {ceSurveyYears[0]}–{ceSurveyYears[4]}:
                </p>
                <div className="ce-years-grid">
                  {ceSurveyYears.map(ceYear => {
                    const hasData = baseThresholds[String(ceYear)]
                    const isActual = ceYear <= LATEST_PUBLISHED_YEAR
                    return (
                      <div key={ceYear} className={`ce-year-item ${isActual ? 'actual' : 'forecast'}`}>
                        <span className="ce-year">{ceYear}</span>
                        <span className={`ce-badge ${isActual ? 'actual' : 'forecast'}`}>
                          {isActual ? 'Actual' : 'Forecast'}
                        </span>
                      </div>
                    )
                  })}
                </div>
                <p style={{ marginTop: 16, marginBottom: 8 }}>
                  <strong>Historical thresholds</strong> (by tenure type):
                </p>
                <table className="mini-table history-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Renter</th>
                      <th>Mortgage</th>
                      <th>No mortgage</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...Array(5)].map((_, i) => {
                      const histYear = String(parseInt(year) - i)
                      const data = baseThresholds[histYear]
                      const isHistForecast = parseInt(histYear) > LATEST_PUBLISHED_YEAR
                      return data ? (
                        <tr key={histYear} className={histYear === year ? 'current-row' : ''}>
                          <td className="year-cell">{histYear}</td>
                          <td>{formatCurrency(data.renter)}</td>
                          <td>{formatCurrency(data.owner_with_mortgage)}</td>
                          <td>{formatCurrency(data.owner_without_mortgage)}</td>
                          <td>
                            <span className={`table-badge ${isHistForecast ? 'forecast' : 'actual'}`}>
                              {isHistForecast ? 'F' : 'A'}
                            </span>
                          </td>
                        </tr>
                      ) : null
                    })}
                  </tbody>
                </table>
                {isForecasted && (
                  <p className="forecast-note">
                    F = Forecast. {year} is forecasted using {LATEST_PUBLISHED_YEAR} data + {((forecast.cpiProjections[year] || 0.02) * 100).toFixed(1)}% projected inflation.
                  </p>
                )}
              </div>
            }
          />

          <CalculationCard
            icon="👨‍👩‍👧‍👦"
            title="Family Size Adjustment"
            value={`×${equivScale.toFixed(2)}`}
            subtitle={`${numAdults} adult${numAdults !== 1 ? 's' : ''}, ${numChildren} child${numChildren !== 1 ? 'ren' : ''}`}
            color="var(--blue-700)"
            isExpanded={expandedCard === 'family'}
            onToggle={() => setExpandedCard(expandedCard === 'family' ? null : 'family')}
            details={
              <div>
                <p>
                  Larger families need more resources. The SPM uses a <strong>three-parameter scale</strong>:
                </p>
                <div className="scale-visual">
                  <div className="scale-item">
                    <span className="scale-icon">👤</span>
                    <span>First adult = 1.0</span>
                  </div>
                  <div className="scale-item">
                    <span className="scale-icon">👤</span>
                    <span>Each additional adult = +0.5</span>
                  </div>
                  <div className="scale-item">
                    <span className="scale-icon">👶</span>
                    <span>Each child = +0.3</span>
                  </div>
                </div>
                <div className="scale-calculation">
                  <p>Your family: {numAdults > 0 ? '1.0' : '0'}{numAdults > 1 ? ` + ${(0.5 * (numAdults - 1)).toFixed(1)}` : ''}{numChildren > 0 ? ` + ${(0.3 * numChildren).toFixed(1)}` : ''} = <strong>{rawScale.toFixed(1)}</strong></p>
                  <p>Normalized (÷ 2.1 reference): <strong>{equivScale.toFixed(3)}</strong></p>
                </div>
              </div>
            }
          />

          <CalculationCard
            icon="📍"
            title="Location Adjustment"
            value={`×${geoadj.toFixed(2)}`}
            subtitle={getLocationName()}
            color="var(--error)"
            isExpanded={expandedCard === 'location'}
            onToggle={() => setExpandedCard(expandedCard === 'location' ? null : 'location')}
            details={
              <div>
                <p>
                  Housing costs vary dramatically by location. The <strong>GEOADJ</strong> factor
                  adjusts based on local vs. national median rent.
                </p>
                <div className="geoadj-scale">
                  <div className="geoadj-bar">
                    <span style={{ left: '0%' }}>0.84</span>
                    <span style={{ left: '50%' }}>1.00</span>
                    <span style={{ left: '100%' }}>1.27</span>
                    <div
                      className="geoadj-marker"
                      style={{ left: `${((geoadj - 0.84) / (1.27 - 0.84)) * 100}%` }}
                    />
                  </div>
                  <div className="geoadj-labels">
                    <span>West Virginia</span>
                    <span>National avg</span>
                    <span>Hawaii</span>
                  </div>
                </div>
                <p className="geoadj-formula">
                  GEOADJ = (local rent ÷ national rent) × 0.492 + 0.508
                </p>
              </div>
            }
          />
        </div>
      </div>

      {/* Quick comparison table */}
      <div className="comparison-table-section">
        <h2 className="section-title">Compare Scenarios</h2>
        <p className="section-subtitle">
          How thresholds vary for {numAdults} adult{numAdults !== 1 ? 's' : ''} and {numChildren} child{numChildren !== 1 ? 'ren' : ''}
        </p>
        <div className="comparison-table-wrapper">
          <table className="comparison-table">
            <thead>
              <tr>
                <th></th>
                <th>Low-cost<br/><span className="th-sub">GEOADJ 0.84</span></th>
                <th>Average<br/><span className="th-sub">GEOADJ 1.00</span></th>
                <th>High-cost<br/><span className="th-sub">GEOADJ 1.20</span></th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(tenureShortNames).map(([key, name]) => (
                <tr key={key} className={tenure === key ? 'highlight-row' : ''}>
                  <td className="tenure-cell">{name}</td>
                  <td>{formatCurrency(baseThresholds[year][key] * equivScale * 0.84)}</td>
                  <td>{formatCurrency(baseThresholds[year][key] * equivScale * 1.00)}</td>
                  <td>{formatCurrency(baseThresholds[year][key] * equivScale * 1.20)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Resources */}
      <div className="resources-section">
        <h2 className="section-title">Learn More</h2>
        <div className="resource-links">
          <a href="https://www.bls.gov/pir/spm/spm_thresholds_2024.htm" target="_blank" rel="noopener noreferrer">
            BLS Thresholds →
          </a>
          <a href="https://www.bls.gov/cex/pumd.htm" target="_blank" rel="noopener noreferrer">
            CE Survey Data →
          </a>
          <a href="https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html" target="_blank" rel="noopener noreferrer">
            Census SPM →
          </a>
          <a href="https://github.com/PolicyEngine/spm-calculator" target="_blank" rel="noopener noreferrer">
            GitHub →
          </a>
        </div>
      </div>

      {/* Footer */}
      <footer className="footer">
        <img src={LOGO_URL} alt="PolicyEngine" />
        <p>Built by <a href="https://policyengine.org">PolicyEngine</a></p>
      </footer>
    </div>
  )
}

export default App
