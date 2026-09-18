import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Edit2,
  Lock,
  Mail,
  Plus,
  RefreshCw,
  Search,
  Shield,
  ShieldAlert,
  UserCheck,
  UserPlus,
  UserX,
  Users,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import {
  api,
  formatNumber,
  formatTimestamp,
  type CpseOption,
  type User,
  type UserRole,
} from '../../lib/api'

function formatRoleLabel(role: string): string {
  switch (role) {
    case 'admin':
      return 'Administrator'
    case 'data_steward':
      return 'Data Steward'
    case 'reviewer':
      return 'Reviewer'
    case 'auditor':
      return 'Auditor'
    default:
      return role
  }
}

function roleBadgeClass(role: string): string {
  switch (role) {
    case 'admin':
      return 'role-admin'
    case 'data_steward':
      return 'role-data_steward'
    case 'reviewer':
      return 'role-reviewer'
    case 'auditor':
      return 'role-auditor'
    default:
      return 'role-neutral'
  }
}

export default function UserManagement() {
  const { user: currentUser } = useAuth()

  const [users, setUsers] = useState<User[]>([])
  const [cpses, setCpses] = useState<CpseOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // Filters
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')

  // Modals state
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editUser, setEditUser] = useState<User | null>(null)
  const [deactivateUserTarget, setDeactivateUserTarget] = useState<User | null>(null)

  // Create Form State
  const [createEmail, setCreateEmail] = useState('')
  const [createFullName, setCreateFullName] = useState('')
  const [createPassword, setCreatePassword] = useState('')
  const [createRole, setCreateRole] = useState<UserRole>('reviewer')
  const [createCpseId, setCreateCpseId] = useState<string>('')
  const [createSubmitting, setCreateSubmitting] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Edit Form State
  const [editFullName, setEditFullName] = useState('')
  const [editRole, setEditRole] = useState<UserRole>('reviewer')
  const [editCpseId, setEditCpseId] = useState<string>('')
  const [editIsActive, setEditIsActive] = useState(true)
  const [editPassword, setEditPassword] = useState('')
  const [editSubmitting, setEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Deactivate Form State
  const [deactivateSubmitting, setDeactivateSubmitting] = useState(false)
  const [deactivateError, setDeactivateError] = useState<string | null>(null)

  const loadData = async () => {
    try {
      setLoading(true)
      setError(null)
      const [usersResponse, cpsesResponse] = await Promise.all([
        api.listUsers(1, 100),
        api.listCpses().catch(() => [] as CpseOption[]),
      ])
      setUsers(usersResponse.items)
      setCpses(cpsesResponse)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load user directory')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Auto-dismiss success message
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [successMessage])

  // Filtered list
  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase()
    return users.filter((u) => {
      const matchesSearch =
        !q ||
        u.email.toLowerCase().includes(q) ||
        (u.full_name && u.full_name.toLowerCase().includes(q)) ||
        (u.cpse_short_code && u.cpse_short_code.toLowerCase().includes(q))

      const matchesRole = roleFilter === 'all' || u.role === roleFilter

      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'active' && u.is_active) ||
        (statusFilter === 'inactive' && !u.is_active)

      return matchesSearch && matchesRole && matchesStatus
    })
  }, [users, search, roleFilter, statusFilter])

  // Summary Metrics
  const stats = useMemo(() => {
    const total = users.length
    const active = users.filter((u) => u.is_active).length
    const admins = users.filter((u) => u.role === 'admin').length
    const stewards = users.filter((u) => u.role === 'data_steward').length
    const reviewers = users.filter((u) => u.role === 'reviewer').length
    const auditors = users.filter((u) => u.role === 'auditor').length
    return { total, active, admins, stewards, reviewers, auditors }
  }, [users])

  // Handle Create Submit
  const handleCreateSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!createEmail.trim() || !createPassword.trim()) {
      setCreateError('Please provide an email and initial password.')
      return
    }

    try {
      setCreateSubmitting(true)
      setCreateError(null)

      const parsedCpseId = createCpseId ? parseInt(createCpseId, 10) : null

      const created = await api.createUser({
        email: createEmail.trim(),
        password: createPassword,
        full_name: createFullName.trim() || undefined,
        role: createRole,
        cpse_id: parsedCpseId,
      })

      setSuccessMessage(`User ${created.email} created successfully with role ${formatRoleLabel(created.role)}.`)
      setIsCreateOpen(false)
      // Reset form
      setCreateEmail('')
      setCreateFullName('')
      setCreatePassword('')
      setCreateRole('reviewer')
      setCreateCpseId('')
      await loadData()
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create user')
    } finally {
      setCreateSubmitting(false)
    }
  }

  // Handle Open Edit Modal
  const openEditModal = (u: User) => {
    setEditUser(u)
    setEditFullName(u.full_name || '')
    setEditRole(u.role)
    setEditCpseId(u.cpse_id ? String(u.cpse_id) : '')
    setEditIsActive(u.is_active)
    setEditPassword('')
    setEditError(null)
  }

  // Handle Edit Submit
  const handleEditSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editUser) return

    try {
      setEditSubmitting(true)
      setEditError(null)

      const parsedCpseId = editCpseId ? parseInt(editCpseId, 10) : null

      const updated = await api.updateUser(editUser.id, {
        full_name: editFullName.trim() || undefined,
        role: editRole,
        cpse_id: parsedCpseId,
        is_active: editIsActive,
        password: editPassword ? editPassword : undefined,
      })

      setSuccessMessage(`User ${updated.email} updated successfully.`)
      setEditUser(null)
      await loadData()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update user')
    } finally {
      setEditSubmitting(false)
    }
  }

  // Handle Deactivate Submit
  const handleDeactivateSubmit = async () => {
    if (!deactivateUserTarget) return

    try {
      setDeactivateSubmitting(true)
      setDeactivateError(null)
      await api.deactivateUser(deactivateUserTarget.id)
      setSuccessMessage(`User ${deactivateUserTarget.email} has been deactivated.`)
      setDeactivateUserTarget(null)
      await loadData()
    } catch (err) {
      setDeactivateError(err instanceof Error ? err.message : 'Failed to deactivate user')
    } finally {
      setDeactivateSubmitting(false)
    }
  }

  return (
    <div className="page user-management-page">
      {/* Header */}
      <div className="page-header">
        <div>
          <div className="eyebrow">SYSTEM GOVERNANCE</div>
          <h1>User Management</h1>
          <p>Provision, configure, and manage role-based access for CPSE and Ministry personnel.</p>
        </div>
        <div className="dashboard-status">
          <span className="dashboard-status-dot" />
          <span>RBAC Directory Active</span>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="user-alert-banner user-alert-success" role="alert">
          <CheckCircle2 size={16} />
          <span>{successMessage}</span>
        </div>
      )}

      {error && (
        <div className="user-alert-banner user-alert-error" role="alert">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Summary KPI Cards */}
      <section className="user-summary-grid">
        <div className="user-summary-card">
          <div className="user-summary-icon-box">
            <Users size={18} />
          </div>
          <div>
            <span className="user-summary-label">Total Users</span>
            <strong className="user-summary-val">{loading ? '—' : formatNumber(stats.total)}</strong>
            <small className="user-summary-sub">{stats.active} Active accounts</small>
          </div>
        </div>

        <div className="user-summary-card">
          <div className="user-summary-icon-box box-steward">
            <UserCheck size={18} />
          </div>
          <div>
            <span className="user-summary-label">Data Stewards</span>
            <strong className="user-summary-val">{loading ? '—' : formatNumber(stats.stewards)}</strong>
            <small className="user-summary-sub">CPSE Ingestion & Normalization</small>
          </div>
        </div>

        <div className="user-summary-card">
          <div className="user-summary-icon-box box-reviewer">
            <Shield size={18} />
          </div>
          <div>
            <span className="user-summary-label">Reviewers</span>
            <strong className="user-summary-val">{loading ? '—' : formatNumber(stats.reviewers)}</strong>
            <small className="user-summary-sub">Candidate Gate Approval</small>
          </div>
        </div>

        <div className="user-summary-card">
          <div className="user-summary-icon-box box-auditor">
            <ShieldAlert size={18} />
          </div>
          <div>
            <span className="user-summary-label">Auditors & Admins</span>
            <strong className="user-summary-val">
              {loading ? '—' : `${stats.auditors} / ${stats.admins}`}
            </strong>
            <small className="user-summary-sub">Governance & System Oversight</small>
          </div>
        </div>
      </section>

      {/* Main Table Card */}
      <section className="user-table-card">
        {/* Toolbar */}
        <div className="user-toolbar">
          <div className="user-search-box">
            <Search size={15} className="user-search-icon" />
            <input
              type="text"
              placeholder="Search by name, email, or CPSE code…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="user-search-input"
            />
          </div>

          <div className="user-filter-group">
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="user-select-filter"
            >
              <option value="all">All Roles</option>
              <option value="admin">Administrators</option>
              <option value="data_steward">Data Stewards</option>
              <option value="reviewer">Reviewers</option>
              <option value="auditor">Auditors</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="user-select-filter"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active Only</option>
              <option value="inactive">Deactivated Only</option>
            </select>

            <button
              type="button"
              className="user-refresh-btn"
              onClick={loadData}
              title="Refresh directory"
            >
              <RefreshCw size={14} />
            </button>

            <button
              type="button"
              className="user-create-btn"
              onClick={() => {
                setCreateError(null)
                setIsCreateOpen(true)
              }}
            >
              <Plus size={15} />
              <span>Provision User</span>
            </button>
          </div>
        </div>

        {/* Directory Table */}
        <div className="user-table-wrapper">
          <table className="user-table">
            <thead>
              <tr>
                <th style={{ width: '260px' }}>User Identity</th>
                <th style={{ width: '150px' }}>Access Role</th>
                <th style={{ width: '180px' }}>Assigned CPSE</th>
                <th style={{ width: '120px' }}>Status</th>
                <th style={{ width: '160px' }}>Created Date</th>
                <th style={{ width: '140px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="user-table-empty">
                    <span className="status-dot" />
                    <span>Loading user directory…</span>
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={6} className="user-table-empty">
                    No users match the specified criteria.
                  </td>
                </tr>
              ) : (
                filteredUsers.map((u) => {
                  const isSelf = currentUser?.id === u.id
                  return (
                    <tr key={u.id}>
                      <td>
                        <div className="user-identity-cell">
                          <strong className="user-identity-name">
                            {u.full_name || 'Designated Operator'}
                            {isSelf && <span className="user-self-pill">You</span>}
                          </strong>
                          <span className="user-identity-email">{u.email}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`login-role-badge ${roleBadgeClass(u.role)}`}>
                          {formatRoleLabel(u.role)}
                        </span>
                      </td>
                      <td>
                        {u.cpse_short_code ? (
                          <span className="user-cpse-pill">{u.cpse_short_code}</span>
                        ) : (
                          <span className="user-cpse-national">National (All CPSEs)</span>
                        )}
                      </td>
                      <td>
                        <span className={`user-status-pill ${u.is_active ? 'active' : 'inactive'}`}>
                          <span className="user-status-dot" />
                          <span>{u.is_active ? 'Active' : 'Deactivated'}</span>
                        </span>
                      </td>
                      <td>
                        <span className="user-date-cell">
                          {u.created_at ? formatTimestamp(u.created_at) : '—'}
                        </span>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="user-actions-cell">
                          <button
                            type="button"
                            className="user-action-btn edit-btn"
                            onClick={() => openEditModal(u)}
                            title="Edit user profile"
                          >
                            <Edit2 size={13} />
                            <span>Edit</span>
                          </button>

                          {u.is_active && (
                            <button
                              type="button"
                              className="user-action-btn deactivate-btn"
                              disabled={isSelf}
                              onClick={() => {
                                setDeactivateError(null)
                                setDeactivateUserTarget(u)
                              }}
                              title={
                                isSelf
                                  ? 'Cannot deactivate your own administrator account'
                                  : 'Deactivate user access'
                              }
                            >
                              <UserX size={13} />
                              <span>Deactivate</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Table Footer */}
        <div className="user-table-footer">
          <span>
            Showing {filteredUsers.length} of {formatNumber(users.length)} registered users
          </span>
        </div>
      </section>

      {/* CREATE USER MODAL */}
      {isCreateOpen && (
        <div className="common-detail-overlay" onClick={() => setIsCreateOpen(false)}>
          <div
            className="common-detail-modal"
            style={{ maxWidth: '540px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="common-detail-header">
              <div>
                <div className="eyebrow">USER PROVISIONING</div>
                <h2>Provision New User</h2>
                <p>Register a new CPSE official or governance auditor in the MIRA registry.</p>
              </div>
              <button
                type="button"
                className="common-close-button"
                onClick={() => setIsCreateOpen(false)}
                title="Close modal"
              >
                ×
              </button>
            </div>

            <div className="common-detail-body">
              {createError && (
                <div className="user-modal-alert-error" role="alert">
                  <AlertCircle size={15} />
                  <span>{createError}</span>
                </div>
              )}

              <form onSubmit={handleCreateSubmit} className="user-modal-form">
                <div className="user-modal-field">
                  <label htmlFor="create-email">Official Email Address *</label>
                  <div className="user-modal-input-box">
                    <Mail size={15} className="user-modal-icon" />
                    <input
                      id="create-email"
                      type="email"
                      required
                      placeholder="e.g. officer@iocl.co.in"
                      value={createEmail}
                      onChange={(e) => setCreateEmail(e.target.value)}
                    />
                  </div>
                </div>

                <div className="user-modal-field">
                  <label htmlFor="create-fullname">Full Name / Designation</label>
                  <div className="user-modal-input-box">
                    <UserPlus size={15} className="user-modal-icon" />
                    <input
                      id="create-fullname"
                      type="text"
                      placeholder="e.g. Senior Piping Engineer"
                      value={createFullName}
                      onChange={(e) => setCreateFullName(e.target.value)}
                    />
                  </div>
                </div>

                <div className="user-modal-field">
                  <div className="user-modal-label-row">
                    <label htmlFor="create-password">Initial Password *</label>
                    <span className="user-modal-hint">Min 6 characters</span>
                  </div>
                  <div className="user-modal-input-box">
                    <Lock size={15} className="user-modal-icon" />
                    <input
                      id="create-password"
                      type="password"
                      required
                      placeholder="Enter temporary password"
                      value={createPassword}
                      onChange={(e) => setCreatePassword(e.target.value)}
                    />
                  </div>
                </div>

                <div className="user-modal-field-grid">
                  <div className="user-modal-field">
                    <label htmlFor="create-role">Access Role *</label>
                    <select
                      id="create-role"
                      value={createRole}
                      onChange={(e) => setCreateRole(e.target.value as UserRole)}
                      className="user-modal-select"
                    >
                      <option value="reviewer">Reviewer (Specification Gate)</option>
                      <option value="data_steward">Data Steward (Ingestion & Harmonization)</option>
                      <option value="auditor">Auditor (Governance Trail)</option>
                      <option value="admin">Administrator (Full System Oversight)</option>
                    </select>
                  </div>

                  <div className="user-modal-field">
                    <label htmlFor="create-cpse">CPSE Organization</label>
                    <select
                      id="create-cpse"
                      value={createCpseId}
                      onChange={(e) => setCreateCpseId(e.target.value)}
                      className="user-modal-select"
                    >
                      <option value="">National / All CPSEs (None)</option>
                      {cpses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.short_code} — {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="user-modal-actions">
                  <button
                    type="button"
                    className="user-btn-secondary"
                    onClick={() => setIsCreateOpen(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="user-btn-primary"
                    disabled={createSubmitting}
                  >
                    {createSubmitting ? 'Creating Account…' : 'Create User Account'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* EDIT USER MODAL */}
      {editUser && (
        <div className="common-detail-overlay" onClick={() => setEditUser(null)}>
          <div
            className="common-detail-modal"
            style={{ maxWidth: '540px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="common-detail-header">
              <div>
                <div className="eyebrow">UPDATE USER</div>
                <h2>Edit User Profile</h2>
                <p>{editUser.email}</p>
              </div>
              <button
                type="button"
                className="common-close-button"
                onClick={() => setEditUser(null)}
                title="Close modal"
              >
                ×
              </button>
            </div>

            <div className="common-detail-body">
              {editError && (
                <div className="user-modal-alert-error" role="alert">
                  <AlertCircle size={15} />
                  <span>{editError}</span>
                </div>
              )}

              <form onSubmit={handleEditSubmit} className="user-modal-form">
                <div className="user-modal-field">
                  <label>Official Email</label>
                  <input
                    type="email"
                    value={editUser.email}
                    disabled
                    className="user-modal-input-disabled"
                  />
                </div>

                <div className="user-modal-field">
                  <label htmlFor="edit-fullname">Full Name / Designation</label>
                  <input
                    id="edit-fullname"
                    type="text"
                    value={editFullName}
                    onChange={(e) => setEditFullName(e.target.value)}
                    placeholder="e.g. Lead Process Engineer"
                    className="user-modal-input-text"
                  />
                </div>

                <div className="user-modal-field-grid">
                  <div className="user-modal-field">
                    <label htmlFor="edit-role">Access Role</label>
                    <select
                      id="edit-role"
                      value={editRole}
                      onChange={(e) => setEditRole(e.target.value as UserRole)}
                      className="user-modal-select"
                    >
                      <option value="reviewer">Reviewer</option>
                      <option value="data_steward">Data Steward</option>
                      <option value="auditor">Auditor</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </div>

                  <div className="user-modal-field">
                    <label htmlFor="edit-cpse">CPSE Organization</label>
                    <select
                      id="edit-cpse"
                      value={editCpseId}
                      onChange={(e) => setEditCpseId(e.target.value)}
                      className="user-modal-select"
                    >
                      <option value="">National / All CPSEs</option>
                      {cpses.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.short_code} — {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="user-modal-field">
                  <label htmlFor="edit-status">Account Authorization Status</label>
                  <select
                    id="edit-status"
                    value={editIsActive ? 'active' : 'inactive'}
                    onChange={(e) => setEditIsActive(e.target.value === 'active')}
                    className="user-modal-select"
                  >
                    <option value="active">Active & Authorized</option>
                    <option value="inactive">Suspended / Deactivated</option>
                  </select>
                </div>

                <div className="user-modal-field">
                  <div className="user-modal-label-row">
                    <label htmlFor="edit-password">Reset Password</label>
                    <span className="user-modal-hint">Leave blank to retain current password</span>
                  </div>
                  <div className="user-modal-input-box">
                    <Lock size={15} className="user-modal-icon" />
                    <input
                      id="edit-password"
                      type="password"
                      placeholder="New password (optional)"
                      value={editPassword}
                      onChange={(e) => setEditPassword(e.target.value)}
                    />
                  </div>
                </div>

                <div className="user-modal-actions">
                  <button
                    type="button"
                    className="user-btn-secondary"
                    onClick={() => setEditUser(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="user-btn-primary"
                    disabled={editSubmitting}
                  >
                    {editSubmitting ? 'Saving Changes…' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* DEACTIVATE CONFIRMATION MODAL */}
      {deactivateUserTarget && (
        <div className="common-detail-overlay" onClick={() => setDeactivateUserTarget(null)}>
          <div
            className="common-detail-modal"
            style={{ maxWidth: '480px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="common-detail-header">
              <div>
                <div className="eyebrow" style={{ color: 'var(--danger)' }}>
                  ACCOUNT DEACTIVATION
                </div>
                <h2>Deactivate Account</h2>
                <p>{deactivateUserTarget.email}</p>
              </div>
              <button
                type="button"
                className="common-close-button"
                onClick={() => setDeactivateUserTarget(null)}
                title="Close modal"
              >
                ×
              </button>
            </div>

            <div className="common-detail-body">
              {deactivateError && (
                <div className="user-modal-alert-error" role="alert">
                  <AlertCircle size={15} />
                  <span>{deactivateError}</span>
                </div>
              )}

              <div className="user-deactivate-notice">
                <AlertCircle size={20} className="notice-icon" />
                <div>
                  <strong>Are you sure you want to deactivate this user?</strong>
                  <p>
                    <strong>{deactivateUserTarget.full_name || deactivateUserTarget.email}</strong>{' '}
                    will be immediately blocked from signing into the MIRA portal and running workflow actions.
                  </p>
                </div>
              </div>

              <div className="user-modal-actions">
                <button
                  type="button"
                  className="user-btn-secondary"
                  onClick={() => setDeactivateUserTarget(null)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="user-btn-danger"
                  onClick={handleDeactivateSubmit}
                  disabled={deactivateSubmitting}
                >
                  {deactivateSubmitting ? 'Deactivating…' : 'Deactivate User Account'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
