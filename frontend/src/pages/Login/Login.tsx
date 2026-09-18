import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  HelpCircle,
  Lock,
  Mail,
  ShieldCheck,
} from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

interface PersonaAccount {
  title: string
  role: string
  org: string
  email: string
  password: string
  description: string
  badgeText: string
}

const EVAL_PERSONAS: PersonaAccount[] = [
  {
    title: 'System Administrator',
    role: 'admin',
    org: 'MoPNG / Central Governance',
    email: 'admin@mira.gov.in',
    password: 'Admin@123',
    description: 'System administration, user provisioning, CPSE cluster policy oversight',
    badgeText: 'ADMINISTRATOR',
  },
  {
    title: 'Data Steward',
    role: 'data_steward',
    org: 'CPCL / Refinery Master Data',
    email: 'steward@mira.gov.in',
    password: 'Steward@123',
    description: 'Material master batch ingestion, schedule/NB normalization, NMC generation',
    badgeText: 'DATA STEWARD',
  },
  {
    title: 'Material Reviewer',
    role: 'reviewer',
    org: 'IOCL / Technical Review',
    email: 'reviewer@mira.gov.in',
    password: 'Reviewer@123',
    description: 'Specification gate validation, candidate approval/rejection, critical check overrides',
    badgeText: 'REVIEWER',
  },
  {
    title: 'Compliance Auditor',
    role: 'auditor',
    org: 'Governance & Vigilance Wing',
    email: 'auditor@mira.gov.in',
    password: 'Auditor@123',
    description: 'Cryptographic audit log verification, compliance inspection, mapping export',
    badgeText: 'AUDITOR',
  },
]

export default function Login() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('steward@mira.gov.in')
  const [password, setPassword] = useState('Steward@123')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard'
  if (isAuthenticated) {
    return <Navigate to={from} replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password.trim()) {
      setError('Please enter your official CPSE / MIRA credentials to proceed.')
      return
    }

    try {
      setSubmitting(true)
      setError(null)
      await login({ email: email.trim(), password })
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid credentials. Please verify your email and password.')
    } finally {
      setSubmitting(false)
    }
  }

  const selectPersona = (p: PersonaAccount) => {
    setEmail(p.email)
    setPassword(p.password)
    setError(null)
  }

  return (
    <div className="login-screen-wrapper">
      <div className="login-card-container">
        {/* Brand Header */}
        <div className="login-brand-header">
          <div className="brand-mark login-brand-mark">M</div>
          <div className="login-brand-info">
            <div className="login-brand-title-row">
              <h1 className="login-brand-name">MIRA</h1>
              <span className="login-env-tag">CPSE Federation</span>
            </div>
            <p className="login-brand-desc">
              Material Intelligence & Harmonization Architecture
            </p>
          </div>
        </div>

        {/* Login Main Card */}
        <div className="login-surface-card">
          <div className="login-card-header">
            <div>
              <h2 className="login-card-title">Sign In</h2>
              <p className="login-card-subtitle">
                Access material standardization, matching and harmonization workspace
              </p>
            </div>
            <div className="login-security-pill" title="Protected with JWT & Encrypted Password Hashing">
              <ShieldCheck size={14} />
              <span>RBAC Protected</span>
            </div>
          </div>

          {error && (
            <div className="login-error-banner" role="alert">
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="login-form">
            <div className="login-input-group">
              <label htmlFor="login-email" className="login-label">
                Official Email Address
              </label>
              <div className="login-input-box">
                <Mail size={15} className="login-input-icon" />
                <input
                  id="login-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@cpse.gov.in"
                  required
                  autoComplete="username"
                  className="login-input"
                />
              </div>
            </div>

            <div className="login-input-group">
              <div className="login-label-row">
                <label htmlFor="login-password" className="login-label">
                  Workstation Password
                </label>
                <span className="login-hint">Default: [Role]@123</span>
              </div>
              <div className="login-input-box">
                <Lock size={15} className="login-input-icon" />
                <input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  autoComplete="current-password"
                  className="login-input"
                />
                <button
                  type="button"
                  className="login-password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="login-submit-btn"
              disabled={submitting}
            >
              {submitting ? (
                <>
                  <span className="login-btn-spinner" />
                  <span>Authenticating...</span>
                </>
              ) : (
                <>
                  <span>Sign In to Workstation</span>
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>

          {/* Persona Switcher Section */}
          <div className="login-personas-section">
            <div className="login-personas-header">
              <div className="login-personas-title">
                <HelpCircle size={13} />
                <span>Evaluation Roles</span>
              </div>
              <span className="login-personas-tip">Select a role profile to populate credentials</span>
            </div>

            <div className="login-personas-grid">
              {EVAL_PERSONAS.map((p) => {
                const isSelected = email === p.email
                return (
                  <button
                    key={p.email}
                    type="button"
                    className={`login-persona-item ${isSelected ? 'active' : ''}`}
                    onClick={() => selectPersona(p)}
                    title={p.description}
                  >
                    <div className="login-persona-top">
                      <span className={`login-role-badge role-${p.role}`}>
                        {p.badgeText}
                      </span>
                      {isSelected && (
                        <span className="login-selected-indicator">
                          <Check size={11} />
                        </span>
                      )}
                    </div>
                    <div className="login-persona-name">{p.title}</div>
                    <div className="login-persona-org">{p.org}</div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>


        {/* Footer */}
        <footer className="login-portal-footer">
          <p className="login-footer-orgs">
            MoPNG • IndianOil • Bharat Petroleum • CPCL • SAIL • NTPC • BHEL
          </p>
          <p className="login-footer-legal">
            MIRA Central Material Master Registry — All access and harmonization actions are cryptographically audited.
          </p>
        </footer>
      </div>
    </div>
  )
}

